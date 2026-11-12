from datetime import datetime, timedelta, timezone
import sqlite3
import unittest

from backend import main as m
from backend.comparison import pair
from backend.dramas import PRIMARY, COMPARISON
from backend.social_sources import parse_weibo, parse_douban
from backend.yunhe_api import parse_payload
from backend import test_storage as storage


class PairTests(unittest.TestCase):
    def setUp(self):
        self.current = datetime(2026, 11, 9, 16, tzinfo=timezone(timedelta(hours=8)))

    def row(self, value, unit='次', source_time=None):
        return {'value': value, 'unit': unit, 'source_time': source_time,
                'collected_at': self.current.isoformat()}

    def test_missing_and_zero_denominator_are_not_zero_filled(self):
        self.assertFalse(pair(self.row(10), None, 'topic_reads', 15, self.current)['comparable'])
        self.assertFalse(pair(self.row(None), self.row(10), 'rating', 15, self.current)['comparable'])
        result = pair(self.row(10), self.row(0), 'topic_reads', 15, self.current)
        self.assertTrue(result['comparable'])
        self.assertEqual(result['delta'], 10)
        self.assertIsNone(result['relative_percent'])

    def test_date_and_unit_mismatches_pause_comparison(self):
        self.assertFalse(pair(self.row(9164, source_time='2026-11-08'),
            self.row(7043, source_time='2026-11-07'), 'yunhe_all_heat', 30, self.current)['comparable'])
        self.assertFalse(pair(self.row(7.2, '%'), self.row(.043, '比率'), 'market_share', 30, self.current)['comparable'])

    def test_stale_snapshots_do_not_calculate_gap(self):
        old = self.row(2)
        old['collected_at'] = (self.current - timedelta(hours=2)).isoformat()
        self.assertFalse(pair(old, self.row(9), 'rank', 15, self.current)['comparable'])

    def test_rank_direction_and_percentage_points_are_explicit(self):
        result = pair(self.row(1, '名', '2026-11-08'), self.row(5, '名', '2026-11-08'), 'yunhe_heat_rank', 30, self.current)
        self.assertTrue(result['lower_is_better'])
        self.assertEqual(result['delta'], -4)
        self.assertIsNone(result['relative_percent'])
        result = pair(self.row(7.2, '%', '2026-11-08'), self.row(4.3, '%', '2026-11-08'), 'market_share', 30, self.current)
        self.assertAlmostEqual(result['delta'], 2.9)
        self.assertIsNone(result['relative_percent'])

    def test_unknown_meanings_and_distinct_video_samples_not_compared(self):
        for metric in ('page_displayed_metric', 'video_like:123'):
            self.assertFalse(pair(self.row(10), self.row(20), metric, 15, self.current)['comparable'])


class DramaParsingTests(unittest.TestCase):
    def test_yunhe_titles_are_separate_in_same_response(self):
        payload = {'date': 1794067200000, 'content': [
            {'name': PRIMARY, 'allHot': 9164}, {'name': COMPARISON, 'allHot': 7043}]}
        left = {r['metric']: r['value'] for r in parse_payload('heat', payload, PRIMARY)}
        right = {r['metric']: r['value'] for r in parse_payload('heat', payload, COMPARISON)}
        self.assertEqual(left['yunhe_all_heat'], 9164)
        self.assertEqual(right['yunhe_all_heat'], 7043)
        self.assertEqual(right['yunhe_heat_rank'], 2)

    def test_official_weibo_topics_can_have_distinct_names_and_empty_header_cards(self):
        packet = {'url': 'https://m.weibo.cn/api/container/getIndex', 'data': {'ok': 1, 'data': {
            'cardlistInfo': {'cardlist_head_cards': [[], {'head_data': {
                'title': '#剧集折月亮#', 'midtext': '阅读量2.7亿 讨论量903.8万'}}]}}}}
        self.assertEqual(parse_weibo([packet], PRIMARY), [])
        rows = {r['metric']: r for r in parse_weibo([packet], COMPARISON)}
        self.assertEqual(rows['topic_reads']['value'], 270000000)
        self.assertIn('剧集折月亮', rows['topic_reads']['metadata']['scope'])

    def test_douban_url_and_entity_match_the_selected_title(self):
        html = '<h1><span property="v:itemreviewed">折月亮</span></h1><div id="interest_sectl">暂无评分</div>'
        self.assertEqual(parse_douban(html, PRIMARY), [])
        self.assertIn('/36809913/', parse_douban(html, COMPARISON)[0]['source_url'])


class DramaStorageTests(unittest.TestCase):
    setUp = storage.StorageTests.setUp
    tearDown = storage.StorageTests.tearDown

    def test_title_specific_daily_deduplication_status_and_series(self):
        for title, value in [(PRIMARY, 9164), (COMPARISON, 7043)]:
            m.save_observation('yunhe', 'yunhe_all_heat', value, '热度指数', 'https://example.com/',
                               m.now().date().isoformat(), drama=title)
        self.assertEqual(m.get_latest('yunhe', PRIMARY)[0]['value'], 9164)
        self.assertEqual(m.get_latest('yunhe', COMPARISON)[0]['value'], 7043)
        m.set_status('yunhe', 'ok', success=True, drama=PRIMARY)
        m.set_status('yunhe', 'error', drama=COMPARISON)
        self.assertEqual(next(s for s in m.sources(PRIMARY) if s['id']=='yunhe')['state'], 'ok')
        self.assertEqual(next(s for s in m.sources(COMPARISON) if s['id']=='yunhe')['state'], 'error')
        self.assertEqual(m.series('yunhe', hours=168, title=COMPARISON)[0]['value'], 7043)

    def test_old_database_migration_preserves_original_drama_history(self):
        # Recreate the previous observations schema and migrate without data loss.
        conn = m.db()
        conn.execute('DROP TABLE observations')
        conn.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY,source TEXT,metric TEXT,value REAL,unit TEXT,collected_at TEXT,source_time TEXT,source_url TEXT,metadata_json TEXT)')
        conn.execute("INSERT INTO observations VALUES(1,'yunhe','yunhe_all_heat',9164,'热度指数',?,NULL,'https://example.com/','{}')", (m.now().isoformat(),))
        conn.commit(); conn.close()
        m.init_db()
        self.assertEqual(m.get_latest('yunhe', PRIMARY)[0]['value'], 9164)
        self.assertEqual(m.get_latest('yunhe', COMPARISON), [])


if __name__ == '__main__':
    unittest.main()
