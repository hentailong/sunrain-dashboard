import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend import douyin_api as d, main as m
from backend.dramas import PRIMARY, COMPARISON
from backend import test_storage as storage


# Reduced official response captured on 2026-11-09. The second entity's
# explicit rank is 6, so a parser using this reduced list's index will fail.
PAYLOAD = {'status_code':0,'active_time':1794211200,'has_more':False,'data':[
    {'item_id':'7573604009374646830','item_info':{'nickname':PRIMARY,'rank':'1'},'score':185838957},
    {'item_id':'7534632326630736394','item_info':{'nickname':COMPARISON,'rank':'6'},'score':46482231}]}


class DouyinParsingTests(unittest.TestCase):
    def test_exact_titles_original_heat_and_explicit_rank(self):
        for title,heat,rank in [(PRIMARY,185838957,1),(COMPARISON,46482231,6)]:
            rows={r['metric']:r for r in d.parse_payload(PAYLOAD,title)}
            self.assertEqual(set(rows),{'douyin_drama_heat','douyin_drama_rank'})
            self.assertEqual(rows['douyin_drama_heat']['value'],heat)
            self.assertEqual(rows['douyin_drama_rank']['value'],rank)
            self.assertEqual(rows['douyin_drama_heat']['source_time'],'2026-11-09T16:00:00+08:00')
        self.assertEqual(d.parse_payload(PAYLOAD,'太阳雨'),[])

    def test_bad_fields_and_video_samples_never_become_rank(self):
        for field,value in [('score',None),('score',float('nan')),('score',True),('rank','未知'),('rank',-1),('rank',1.5)]:
            payload=copy.deepcopy(PAYLOAD)
            if field=='rank':payload['data'][0]['item_info'][field]=value
            else:payload['data'][0][field]=value
            self.assertEqual(d.parse_payload(payload),[])
        for payload in [{'status_code':0,'data':[]},dict(PAYLOAD,status_code=8),dict(PAYLOAD,active_time=0),
                        {'status_code':0,'active_time':1794211200,'data':[{'aweme_id':'123','desc':PRIMARY,'statistics':{'digg_count':90000}}]}]:
            self.assertEqual(d.parse_payload(payload),[])


class DouyinRequestTests(unittest.IsolatedAsyncioTestCase):
    async def run_response(self,response):
        original=httpx.AsyncClient
        calls=[]
        def handle(request):
            calls.append(request)
            self.assertEqual(request.url.params['chart_key'],'entertainment_teleplay_v2')
            self.assertEqual(request.url.params['billboard_type'],'2')
            self.assertNotIn('cookie',request.headers)
            return response
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(d,'EVIDENCE',Path(directory)),patch.object(d.httpx,'AsyncClient',
                    side_effect=lambda **kw:original(**kw,transport=httpx.MockTransport(handle))):
                result=await d.collect_douyin_api()
                if any(r['readings'] for r in result.values()):
                    files=list(Path(directory).glob('*.json'))
                    self.assertEqual(len(files),1)
                    evidence=json.loads(files[0].read_text(encoding='utf-8'))
                    self.assertEqual(evidence['response']['active_time'],PAYLOAD['active_time'])
                    self.assertIn('billboard_type=2',evidence['official_url'])
                    self.assertEqual(result[PRIMARY]['readings'][0]['source_url'],result[COMPARISON]['readings'][0]['source_url'])
        self.assertEqual(len(calls),1)
        return result

    async def test_one_background_request_collects_both_dramas(self):
        result=await self.run_response(httpx.Response(200,json=PAYLOAD))
        self.assertTrue(all(result[t]['state']=='ok' for t in (PRIMARY,COMPARISON)))

    async def test_rate_limit_validation_schema_and_empty_board_are_distinct(self):
        for response,state in [(httpx.Response(429), 'restricted'),
                               (httpx.Response(200,text='<html>访问验证</html>'),'verification_required'),
                               (httpx.Response(200,json={'status_code':0,'data':'changed'}),'adapter_pending'),
                               (httpx.Response(200,json=dict(PAYLOAD,data=[])),'no_data')]:
            result=await self.run_response(response)
            self.assertTrue(all(r['state']==state and not r['readings'] for r in result.values()))


class DouyinSchedulerTests(unittest.IsolatedAsyncioTestCase):
    setUp = storage.StorageTests.setUp
    tearDown = storage.StorageTests.tearDown

    async def test_scheduler_never_opens_browser_and_failure_keeps_snapshot(self):
        result={title:{'state':'ok','message':'真实榜单','readings':d.parse_payload(PAYLOAD,title)} for title in (PRIMARY,COMPARISON)}
        with patch.object(m,'collect_douyin_api',new_callable=AsyncMock,return_value=result) as request, \
             patch.object(m.browsers,'collect',new_callable=AsyncMock) as browser:
            await m.collect_one('douyin')
            request.assert_awaited_once()
            browser.assert_not_awaited()
        failed={title:{'state':'restricted','message':'限流','readings':[]} for title in (PRIMARY,COMPARISON)}
        with patch.object(m,'collect_douyin_api',new_callable=AsyncMock,return_value=failed):
            await m.collect_one('douyin')
        for title in (PRIMARY,COMPARISON):
            source=next(s for s in m.sources(title) if s['id']=='douyin')
            self.assertEqual(source['state'],'restricted')
            self.assertEqual(len(source['metrics']),2)
            self.assertEqual(source['method'],'official_api')


if __name__=='__main__':
    unittest.main()
