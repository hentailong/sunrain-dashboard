import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

from fastapi import HTTPException
from backend import main as m


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patcher = patch.object(m, 'DB_PATH', Path(self.directory.name) / 'test.db')
        self.patcher.start()
        m.init_db()

    def tearDown(self):
        self.patcher.stop()
        self.directory.cleanup()

    def test_removed_source_has_no_api_or_schedule_configuration(self):
        self.assertNotIn('bilibili', m.SOURCES)
        self.assertNotIn('bilibili', m.SOURCE_INTERVALS)
        self.assertNotIn('bilibili', {s['id'] for s in m.sources()})
        with self.assertRaises(HTTPException):
            m.series('bilibili')
        self.assertEqual(m.SOURCE_INTERVALS['yunhe'], 15)
        for key in ('weibo', 'douban', 'douyin'):
            self.assertEqual(m.SOURCE_INTERVALS[key], 15)
            self.assertIn(key, m.PAGES)

    def test_repeat_daily_capture_is_deduplicated_and_survives_reinitialization(self):
        for _ in range(2):
            m.save_observation('yunhe', 'market_share', 6.2, '%', 'https://www.enlightent.cn/', '2026-11-07')
        m.init_db()
        conn = m.db()
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 1)
        conn.close()

    def test_yunhe_all_history_includes_days_older_than_window(self):
        old=(m.now().date()-timedelta(days=90)).isoformat()
        m.save_observation('yunhe','market_share',6.2,'%',m.SOURCES['yunhe']['url'],old)
        m.save_observation('douban','short_comments',100,'条',m.SOURCES['douban']['url'],old)
        self.assertEqual(m.series('yunhe',hours=720),[])
        self.assertEqual(m.series('yunhe',hours=1,all_history=True)[0]['time'],old)
        self.assertEqual(m.series('douban',hours=1,all_history=True),[])

    def test_failure_keeps_last_success_and_null_rating(self):
        m.save_observation('douban', 'rating', None, '分', m.SOURCES['douban']['url'])
        m.set_status('douban', 'ok', success=True)
        last = next(s for s in m.sources() if s['id'] == 'douban')['last_success']
        m.set_status('douban', 'error', error='timeout')
        source = next(s for s in m.sources() if s['id'] == 'douban')
        self.assertEqual(source['last_success'], last)
        self.assertIsNone(source['metrics'][0]['value'])
        self.assertEqual(source['state'], 'error')

    def test_backfill_keeps_latest_statistical_day_and_same_day_revision(self):
        m.save_observation('yunhe','market_share',7.1,'%',m.SOURCES['yunhe']['url'],'2026-11-09')
        m.save_observation('yunhe','market_share',4.0,'%',m.SOURCES['yunhe']['url'],'2026-11-06',{'manual':True})
        for source in ('yunhe',None):
            latest=next(r for r in m.get_latest(source) if r['source']=='yunhe' and r['metric']=='market_share')
            self.assertEqual((latest['source_time'],latest['value']),('2026-11-09',7.1))
        m.save_observation('yunhe','market_share',7.2,'%',m.SOURCES['yunhe']['url'],'2026-11-09')
        self.assertEqual(m.get_latest('yunhe')[0]['value'],7.2)
        self.assertIn(4.0,[r['value'] for r in m.series('yunhe',hours=1,all_history=True)])

    def test_all_history_includes_old_maoyan_and_kuyun_records(self):
        old=(m.now().date()-timedelta(days=90)).isoformat()
        for source,metric in [('maoyan','daily_heat'),('kuyun','kuyun_live_rating'),('douyin','douyin_drama_heat'),('weibo','topic_reads'),('baidu_index','search_index')]:
            m.save_observation(source,metric,1.2,'',m.SOURCES[source]['url'],old)
            self.assertEqual(m.series(source,hours=720),[])
            rows=m.series(source,hours=1,all_history=True)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['time'],old)

    def test_douyin_video_history_is_archived_outside_current_statistics(self):
        m.save_observation('douyin','video_like:123',100,'次','https://www.douyin.com/video/123')
        m.save_observation('douyin','douyin_drama_heat',190000000,'热度',m.SOURCES['douyin']['url'])
        m.save_observation('douyin','douyin_drama_rank',1,'名',m.SOURCES['douyin']['url'])
        self.assertEqual({r['metric'] for r in m.get_latest('douyin')},{'douyin_drama_heat','douyin_drama_rank'})
        self.assertEqual(m.series('douyin','video_like:123'),[])
        self.assertEqual({r['metric'] for r in m.series('douyin',hours=168)},{'douyin_drama_heat','douyin_drama_rank'})
        self.assertFalse(m.calculate_forecast('douyin','video_like:123',24)['available'])
        self.assertFalse(m.calculate_forecast('douyin','douyin_drama_rank',24)['available'])
        conn=m.db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations WHERE metric='video_like:123'").fetchone()[0],1)
        conn.close()

    def test_maoyan_daily_revisions_and_incomplete_today_do_not_stack(self):
        current=m.now()
        yesterday=(current.date()-timedelta(days=1)).isoformat()
        for value in (5069.47,5549.38,9603.01):
            m.save_observation('maoyan','daily_heat',value,'热度指数','https://piaofang.maoyan.com/',yesterday)
        m.save_observation('maoyan','daily_heat',2753.87,'热度指数','https://piaofang.maoyan.com/',current.date().isoformat())
        rows=m.series('maoyan','daily_heat',hours=168)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['value'],9603.01)
        self.assertEqual(rows[0]['time'],yesterday)
        self.assertTrue(rows[0]['url'])
        conn=m.db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0],4)
        conn.close()

    def test_maoyan_snapshot_keeps_unchanged_samples_and_recovers_only_real_times(self):
        current=m.now()
        today=current.date().isoformat()
        yesterday=(current.date()-timedelta(days=1)).isoformat()
        for day,value in [(today,3000),(yesterday,9603)]:
            m.save_observation('maoyan','daily_heat',value,'热度指数','https://piaofang.maoyan.com/',day)
        m.init_db()
        m.init_db()
        recovered=m.series('maoyan','maoyan_heat_snapshot',hours=168)
        self.assertEqual(len(recovered),1)
        self.assertEqual(recovered[0]['value'],3000)
        self.assertEqual(recovered[0]['time'],recovered[0]['collected_at'])
        for minute in (1,16):
            stamp=current.replace(hour=8,minute=minute,second=0,microsecond=0)
            with patch.object(m,'now',return_value=stamp):
                m.save_observation('maoyan','maoyan_heat_snapshot',3000,'热度指数','https://piaofang.maoyan.com/',metadata={'statistical_date':today})
        rows=m.series('maoyan','maoyan_heat_snapshot',hours=168)
        self.assertEqual(len(rows),3)
        self.assertEqual(len({r['time'] for r in rows}),3)
        self.assertFalse(m.calculate_forecast('maoyan','maoyan_heat_snapshot',24)['available'])


if __name__ == '__main__':
    unittest.main()
