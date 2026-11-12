import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from backend import dengta_api as d, main as m, test_storage as storage
from backend.dramas import PRIMARY, COMPARISON

NOW = datetime(2026, 11, 11, 10, 10, tzinfo=d.TZ)
# Reduced official v3.0 response. mediaRank is explicitly zero-based; the
# second title's rank is not its position in this reduced fixture.
PAYLOAD = {'ret': ['SUCCESS::调用成功'], 'data': {'code': '200', 'data': {
    'calendarMap': {'showDate': '20261111', 'endDate': '20261111'},
    'rankMap': {'titleInfo': {'columnName1': '实时正片播放量'}, 'rankList': [
        {'mediaName': PRIMARY, 'mediaId': 1514343, 'mediaRank': 2, 'vvCnt': 3618447,
         'cnt': '0.08589713590754412', 'columnValue1': '8.59', 'modifiedTime': '2026-11-11 09:54:58'},
        {'mediaName': COMPARISON, 'mediaId': 1550594, 'mediaRank': 8, 'vvCnt': 1453778,
         'cnt': '0.03451076288954839', 'columnValue1': '3.45', 'modifiedTime': '2026-11-11 09:54:58'}]}}}}


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz)


class DengtaParsingTests(unittest.TestCase):
    def test_units_rank_and_actual_source_time(self):
        rows = {r['metric']: r for r in d.parse_payload(PAYLOAD, current=NOW)}
        self.assertEqual(rows['dengta_play_count']['value'], 3618447)
        self.assertAlmostEqual(rows['dengta_play_share']['value'], 8.589713590754412)
        self.assertEqual(rows['dengta_play_rank']['value'], 3)
        self.assertEqual(rows['dengta_play_count']['source_time'], '2026-11-11T09:54:58+08:00')
        other = {r['metric']: r for r in d.parse_payload(PAYLOAD, COMPARISON, current=NOW)}
        self.assertEqual(other['dengta_play_rank']['value'], 9)
        self.assertEqual(d.parse_payload(PAYLOAD, '太阳雨', current=NOW), [])

    def test_old_board_wrong_metric_and_bad_values_are_rejected(self):
        for field, value in [('vvCnt', True), ('vvCnt', -1), ('vvCnt', 1.5), ('cnt', 'NaN'),
                             ('cnt', '8.59'), ('columnValue1', '50'), ('mediaRank', 0.5),
                             ('modifiedTime', '2021-11-12 15:26:24'),
                             ('modifiedTime', '2026-11-11 06:00:00'),
                             ('modifiedTime', '2026-11-11 12:00:00')]:
            payload = copy.deepcopy(PAYLOAD)
            payload['data']['data']['rankMap']['rankList'][0][field] = value
            self.assertEqual(d.parse_payload(payload, current=NOW), [], (field, value))
        for section, key, value in [('calendarMap', 'showDate', '20211112'),
                                    ('rankMap', 'titleInfo', {'columnName1': '当日热度'})]:
            payload = copy.deepcopy(PAYLOAD)
            payload['data']['data'][section][key] = value
            self.assertEqual(d.parse_payload(payload, current=NOW), [])
        payload = copy.deepcopy(PAYLOAD)
        payload['data']['data']['rankMap']['rankList'].append(payload['data']['data']['rankMap']['rankList'][0])
        self.assertEqual(d.parse_payload(payload, current=NOW), [])


class DengtaRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_anonymous_handshake_and_redacted_evidence(self):
        requests = []
        def handle(request):
            requests.append(request)
            p = request.url.params
            params = json.loads(p['data'])
            self.assertEqual(params['showDate'], '20261111')
            self.assertEqual(params['platformCode'], 'beaconmarketshare_play_vv')
            self.assertNotIn('token', params)
            if len(requests) == 1:
                return httpx.Response(200, json={'ret': ['FAIL_SYS_TOKEN_EMPTY::令牌为空'], 'data': {}},
                    headers={'set-cookie': '_m_h5_tk=anonymous-secret_123; Domain=.taopiaopiao.com; Path=/'})
            expected = hashlib.md5(f'anonymous-secret&{p["t"]}&{d.APP_KEY}&{p["data"]}'.encode()).hexdigest()
            self.assertEqual(p['sign'], expected)
            return httpx.Response(200, json=PAYLOAD)
        original = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as directory, patch.object(d, 'datetime', FixedDatetime), \
             patch.object(d, 'EVIDENCE', Path(directory)), patch.object(d.httpx, 'AsyncClient',
                 side_effect=lambda **kw: original(**kw, transport=httpx.MockTransport(handle))):
            results = await d.collect_dengta_api()
            self.assertTrue(all(r['state'] == 'ok' and len(r['readings']) == 3 for r in results.values()))
            files = list(Path(directory).glob('*.json'))
            self.assertEqual(len(files), 1)
            content = files[0].read_text(encoding='utf8')
            self.assertNotIn('anonymous-secret', content)
            self.assertNotIn('"sign"', content)
            self.assertEqual(len(requests), 2)

    async def test_rate_limit_does_not_retry_or_produce_readings(self):
        original = httpx.AsyncClient
        with patch.object(d.httpx, 'AsyncClient', side_effect=lambda **kw: original(**kw,
                transport=httpx.MockTransport(lambda request: httpx.Response(429)))):
            results = await d.collect_dengta_api()
        self.assertTrue(all(r['state'] == 'restricted' and not r['readings'] for r in results.values()))


class DengtaStorageTests(unittest.IsolatedAsyncioTestCase):
    setUp = storage.StorageTests.setUp
    tearDown = storage.StorageTests.tearDown

    @patch.object(m, 'refresh_hourly', new_callable=AsyncMock)
    @patch.object(m, 'refresh_daily', new_callable=AsyncMock)
    async def test_shared_board_scheduler_and_failure_preserves_previous_values(self, daily, hourly):
        results = {title: {'state': 'ok', 'message': '已更新',
            'readings': d.parse_payload(PAYLOAD, title, current=NOW)} for title in d.DRAMAS}
        with patch.object(m, 'collect_dengta_api', new_callable=AsyncMock, return_value=results) as request, \
             patch.object(m.browsers, 'collect', new_callable=AsyncMock) as browser:
            await m.collect_one('dengta')
            request.assert_awaited_once()
            browser.assert_not_awaited()
        failed = {title: {'state': 'restricted', 'message': '受限', 'readings': []} for title in d.DRAMAS}
        with patch.object(m, 'collect_dengta_api', new_callable=AsyncMock, return_value=failed):
            await m.collect_one('dengta')
        for title in d.DRAMAS:
            source = next(s for s in m.sources(title) if s['id'] == 'dengta')
            self.assertEqual(len(source['metrics']), 3)
            self.assertEqual(source['collection_interval_minutes'], 1)
            self.assertEqual(source['method'], 'official_api')
            self.assertTrue(source['automatic'])
            self.assertEqual(source['state'], 'restricted')
            self.assertFalse(m.calculate_forecast('dengta', 'dengta_play_count', 24, title)['available'])


if __name__ == '__main__':
    unittest.main()
