import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx

from backend import yunhe_api as y


class YunheTests(unittest.TestCase):
    def test_rebo_units_date_and_exact_title(self):
        rows = y.parse_payload('rebo', [
            {'name': '其他剧', 'marketShare': 99, 'reboRank': 1, 'date': '2026-11-07'},
            {'name': y.TITLE, 'marketShare': 6.2, 'reboRank': 8, 'date': '2026-11-07'},
        ])
        self.assertEqual([(r['metric'], r['value'], r['unit']) for r in rows],
                         [('market_share', 6.2, '%'), ('daily_rank', 8, '名')])
        self.assertEqual({r['source_time'] for r in rows}, {'2026-11-07'})
        self.assertEqual(y.parse_payload('rebo', [{'name': y.TITLE, 'marketShare': None,
                         'reboRank': True, 'date': '2026-11-07'}]), [])

    def test_heat_rank_is_its_own_validated_list_position(self):
        payload = {'date': 1794067200000, 'content': [
            {'name': y.TITLE, 'allHot': 9164}, {'name': '其他剧', 'allHot': 8133}]}
        rows = {r['metric']: r for r in y.parse_payload('heat', payload)}
        self.assertEqual(rows['yunhe_heat_rank']['value'], 1)
        self.assertEqual(rows['yunhe_all_heat']['source_time'], '2026-11-08')
        payload['content'].reverse()
        self.assertEqual([r['metric'] for r in y.parse_payload('heat', payload)], ['yunhe_all_heat'])
        self.assertIsNone(y.valid_date('2026-02-30'))

    def test_capture_connects_request_only_and_hides_session(self):
        capture = ('POST https://www.enlightent.cn/research/top/getHeatTop.do HTTP/1.1\n'
                   'Host: www.enlightent.cn\nUser-Agent: capture-client\n\n'
                   'channelType=tv&sort=allHot&day=1&accessToken=test-secret&date=h2 200\n'
                   '{"content":[{"allHot":999999}]}')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'capture.txt'
            file.write_text(capture, encoding='utf-8')
            with patch.object(y, 'CONFIG', root / 'local' / 'config.json'):
                self.assertEqual(y.import_capture(file), 'heat')
                config = json.loads(y.CONFIG.read_text(encoding='utf-8'))
                self.assertEqual(config['requests']['heat']['form']['date'], '')
                self.assertNotIn('999999', y.CONFIG.read_text(encoding='utf-8'))
                self.assertNotIn('test-secret', json.dumps(y.connection_info()))


class YunheRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_post_falls_back_to_public_get(self):
        calls = []

        def handle(request):
            calls.append(request)
            if request.method == 'POST':
                self.assertEqual(parse_qs(request.content.decode())['accessToken'], ['test-secret'])
                return httpx.Response(500, text='accessToken expired')
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.params.get('channelType'), 'tv')
            self.assertEqual(request.url.params.get('date'), '')
            if 'getReboTop' in request.url.path:
                return httpx.Response(200, json=[{'name': y.TITLE, 'marketShare': 6.2, 'reboRank': 8, 'date': '2026-11-07'}])
            return httpx.Response(200, json={'date': 1794067200000,
                'content': [{'name': y.TITLE, 'allHot': 9164}]})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'requests': {kind: {'path': path, 'form': {'channelType': 'tv',
                'day': '1', 'date': ''}, 'accessToken': 'test-secret'} for path, kind in y.ENDPOINTS.items()}}
            file = root / 'config.json'
            file.write_text(json.dumps(config), encoding='utf-8')
            client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
            with patch.object(y, 'CONFIG', file), patch.object(y, 'EVIDENCE', root / 'evidence'), \
                    patch.object(y.httpx, 'AsyncClient', return_value=client):
                result = await y.collect_yunhe_api()
                self.assertEqual(len(calls), 4)
                self.assertEqual(result['state'], 'ok')
                self.assertEqual(len(result['readings']), 4)
                for evidence in y.EVIDENCE.glob('*.json'):
                    text = evidence.read_text(encoding='utf-8')
                    self.assertNotIn('test-secret', text)
                    self.assertNotIn('accessToken', text)
                    self.assertIn(json.loads(text)['request']['method'], ('GET','POST'))

    async def test_expired_session_retains_no_fabricated_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'config.json'
            file.write_text(json.dumps({'requests': {'heat': {'path': '/research/top/getHeatTop.do',
                'form': {}, 'accessToken': 'expired'}}}), encoding='utf-8')
            client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(403)))
            with patch.object(y, 'CONFIG', file), patch.object(y.httpx, 'AsyncClient', return_value=client):
                result = await y.collect_yunhe_api()
            self.assertEqual(result['state'], 'session_expired')
            self.assertEqual(result['readings'], [])


if __name__ == '__main__':
    unittest.main()
