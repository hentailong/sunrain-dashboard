import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend import weibo_api as w, main as m
from backend.dramas import PRIMARY, COMPARISON, WEIBO_TOPICS


class WeiboBackgroundTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_session_collects_both_dramas_without_browser(self):
        calls=[]
        def handle(request):
            self.assertIn('test-session',request.headers['cookie'])
            calls.append(request)
            container=request.url.params['containerid']
            title=PRIMARY if PRIMARY in container else COMPARISON
            return httpx.Response(200,json={'ok':1,'data':{
                'cardlistInfo':{'cardlist_head_cards':[{'head_data':{'title':f'#{WEIBO_TOPICS[title]}#',
                    'midtext':'阅读量3.6亿 讨论量287万'}}]},'cards':[
                        {'user':{'id':123,'screen_name':title+'官微','verified_reason':f'《{title}》官方微博',
                                 'followers_count':100,'statuses_count':20}}]}})
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'weibo.json'
            config.write_text(json.dumps({'cookies':[{'name':'SUB','value':'test-session','domain':'.weibo.cn'}],
                                          'user_agent':'test-client'}),encoding='utf-8')
            original=httpx.AsyncClient
            def client(**kwargs):
                return original(**kwargs,transport=httpx.MockTransport(handle))
            with patch.object(w,'CONFIG',config),patch.object(w.httpx,'AsyncClient',side_effect=client), \
                 patch.object(w,'initialize_session',new_callable=AsyncMock) as initialize:
                for title in (PRIMARY,COMPARISON):
                    result=await w.collect_weibo_api(title)
                    self.assertEqual(result['state'],'ok')
                    self.assertEqual(len(result['readings']),4)
                    self.assertTrue(all(r['metadata']['method']=='official_http' for r in result['readings']))
                    self.assertNotIn('test-session',json.dumps(result))
                initialize.assert_not_awaited()
            self.assertEqual(len(calls),4)

    async def test_restricted_session_refreshes_once_without_visible_fallback(self):
        with patch.object(w,'read_session',return_value={'cookies':[],'user_agent':'test'}), \
             patch.object(w,'request_readings',new_callable=AsyncMock,return_value=([],True,[])) as request, \
             patch.object(w,'initialize_session',new_callable=AsyncMock,return_value={'cookies':[],'user_agent':'test'}) as initialize:
            result=await w.collect_weibo_api(PRIMARY)
            initialize.assert_awaited_once_with(refresh=True)
            self.assertEqual(request.await_count,2)
            self.assertEqual(result['state'],'verification_required')
            self.assertEqual(result['readings'],[])

    async def test_partial_values_survive_session_refresh_failure_to_return_fields(self):
        row={'metric':'topic_reads','value':360000000,'metadata':{}}
        with patch.object(w,'read_session',return_value={}), \
             patch.object(w,'initialize_session',new_callable=AsyncMock,return_value={}), \
             patch.object(w,'request_readings',new_callable=AsyncMock,side_effect=[([row],True,[]),([],True,[])]):
            result=await w.collect_weibo_api(PRIMARY)
            self.assertEqual(result['readings'][0]['value'],360000000)

    async def test_scheduled_weibo_does_not_call_browser_collector(self):
        result={'state':'ok','message':'后台采集','readings':[]}
        with patch.object(m,'collect_weibo_api',new_callable=AsyncMock,return_value=result) as collect, \
             patch.object(m.browsers,'collect',new_callable=AsyncMock) as browser, \
             patch.object(m,'set_status'):
            await m.collect_one('weibo')
            self.assertEqual(collect.await_count,2)
            browser.assert_not_awaited()


if __name__=='__main__':
    unittest.main()
