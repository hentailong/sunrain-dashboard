import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from backend import main as m, test_storage as storage
from backend.dengta_minutes import nearest_minute, normalize_history


class MinuteTests(unittest.IsolatedAsyncioTestCase):
    setUp = storage.StorageTests.setUp
    tearDown = storage.StorageTests.tearDown

    def test_half_up_and_daily_boundary(self):
        for raw, expected in [('10:12:29.999', '10:12:00'), ('10:12:30', '10:13:00'),
                              ('10:59:59', '11:00:00'), ('23:59:50', '23:59:00')]:
            self.assertEqual(nearest_minute('2026-11-11T'+raw+'+08:00'), '2026-11-11T'+expected+'+08:00')
        self.assertEqual(nearest_minute('2026-11-11T02:12:30+00:00'), '2026-11-11T10:13:00+08:00')

    def test_history_migration_preserves_raw_times_and_latest_duplicate(self):
        conn = m.db()
        for clock, value in [('10:12:30', 1), ('10:13:20', 2), ('10:15:10', 3)]:
            conn.execute("INSERT INTO observations(source,metric,value,unit,collected_at,source_time,source_url,metadata_json,drama) VALUES('dengta','dengta_play_count',?,'次',?,'2026-11-11T10:00:01+08:00','test',?,?)",
                         (value, '2026-11-11T'+clock+'+08:00', json.dumps({'statistical_date': '2026-11-11'}), m.TITLE))
        raw = [tuple(r) for r in conn.execute('SELECT id,value,collected_at,source_time FROM observations')]
        self.assertEqual(normalize_history(conn), 3)
        self.assertEqual(normalize_history(conn), 0)
        self.assertEqual(raw, [tuple(r) for r in conn.execute('SELECT id,value,collected_at,source_time FROM observations')])
        conn.commit(); conn.close()
        rows = m.series('dengta', hours=48, all_history=True)
        self.assertEqual([(r['time'][11:19], r['value']) for r in rows], [('10:13:00', 2), ('10:15:00', 3)])
        self.assertEqual(rows[0]['collected_at'], '2026-11-11T10:13:20+08:00')
        self.assertEqual(rows[0]['source_time'], '2026-11-11T10:00:01+08:00')

    def test_unchanged_official_value_is_still_a_real_minute_sample(self):
        at = datetime(2026,11,11,10,13,tzinfo=m.TZ)
        for minute in range(2):
            with patch.object(m, 'now', return_value=at+timedelta(minutes=minute,seconds=2)):
                m.save_observation('dengta','dengta_play_count',100,'次','test','2026-11-11T10:00:01+08:00')
        rows = m.series('dengta', hours=48, all_history=True)
        self.assertEqual([r['time'][11:19] for r in rows], ['10:13:00','10:14:00'])

    async def test_scheduler_fires_on_zero_seconds_without_startup_sample(self):
        with patch.object(m,'collect_all',new_callable=AsyncMock) as initial, patch.object(m.browsers,'close',new_callable=AsyncMock):
            async with m.lifespan(m.app):
                job = m.scheduler.get_job('collect:dengta')
                fire = job.next_run_time
                self.assertEqual((fire.second,fire.microsecond), (0,0))
                self.assertEqual(job.trigger.get_next_fire_time(fire,fire)-fire,timedelta(minutes=1))
                import asyncio
                await asyncio.sleep(0)
                initial.assert_awaited_once_with(scheduled_startup=True)


if __name__ == '__main__':
    unittest.main()
