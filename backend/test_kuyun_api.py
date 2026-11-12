from datetime import datetime
import unittest
from unittest.mock import AsyncMock, patch

from backend import kuyun_api as k, main as m
from backend import test_storage as storage

NOW = datetime(2026, 11, 11, 20, 20, tzinfo=k.TZ)
ROW = {'tvid': 24, 'tvn': '湖南卫视', 'epg': '今天是太阳雨 1',
       'rt_time': '2026-11-11 20:19:55', 'start_time': '2026-11-11 20:10',
       'end_time': '2026-11-11 20:58', 'r': .003456, 'mr': .05678}


class KuyunParserTests(unittest.TestCase):
    def parse(self, **changes):
        return k.parse_payload({'status': True, 'data': [ROW | changes]}, NOW)

    def test_only_current_matching_programme_and_percent_units(self):
        result = self.parse()
        self.assertEqual(result['state'], 'ok')
        self.assertAlmostEqual(result['readings'][0]['value'], .3456)
        self.assertAlmostEqual(result['readings'][1]['value'], 5.678)
        self.assertEqual(result['readings'][0]['source_time'], '2026-11-11T20:19:55+08:00')
        self.assertIn('broadcast_id', result['readings'][0]['metadata'])

    def test_other_programme_does_not_become_drama_rating(self):
        for name in ['最好的安排 7', '今天是太阳雨预告', '今天是太阳雨特别节目']:
            result = self.parse(epg=name)
            self.assertEqual(result['state'], 'off_air')
            self.assertEqual(result['readings'], [])

    def test_stale_future_wrong_slot_and_invalid_rates_rejected(self):
        for changes in [dict(rt_time='2026-11-11 19:00:00'), dict(rt_time='2026-11-11 20:25:00'),
                        dict(end_time='2026-11-11 20:19'), dict(start_time='2026-11-11 20:21'),
                        dict(r=-1), dict(r=2), dict(r=True), dict(r='nan'), dict(mr=None),
                        dict(tvn='其他频道')]:
            with self.subTest(changes=changes):
                result = self.parse(**changes)
                self.assertEqual(result['state'], 'error')
                self.assertEqual(result['readings'], [])

    def test_missing_channel_duplicate_channel_and_bad_payload(self):
        for payload in [{'status': True, 'data': []}, {'status': True, 'data': [ROW, ROW]},
                        {'status': False, 'data': [ROW]}, None]:
            self.assertFalse(k.parse_payload(payload, NOW)['readings'])


class KuyunStorageTests(unittest.IsolatedAsyncioTestCase):
    setUp = storage.StorageTests.setUp
    tearDown = storage.StorageTests.tearDown

    async def test_off_air_preserves_history_without_fabricated_zero(self):
        for result in [k.parse_payload({'status': True, 'data': [ROW]}, NOW),
                       k.parse_payload({'status': True, 'data': [ROW | {'epg': '新闻联播'}]}, NOW)]:
            with patch.object(m, 'collect_kuyun_api', new_callable=AsyncMock, return_value=result) as request:
                await m.collect_one('kuyun')
                request.assert_awaited_once()
        source = next(s for s in m.sources() if s['id']=='kuyun')
        self.assertEqual(source['state'], 'off_air')
        self.assertEqual(len(source['metrics']), 2)
        self.assertEqual(source['collection_interval_minutes'], 1)
        self.assertTrue(source['automatic'])
        self.assertEqual(source['broadcast']['channel'], '湖南卫视')
        self.assertFalse(m.calculate_forecast('kuyun','kuyun_live_rating',24)['available'])


if __name__ == '__main__':
    unittest.main()
