from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from backend import baidu_api as b
from backend import main as m
from backend import test_storage as storage

TITLE='今天是太阳雨'
NOW=datetime(2026,11,11,12,tzinfo=b.TZ)
PAYLOAD={'ready':True,'url':b.baidu_index(TITLE),'title':TITLE,'area':'0','device':'all',
         'dates':['2026-11-08','2026-11-09'],'series':[{'name':TITLE,'data':['44560','35380']}]}

class ParserTests(unittest.TestCase):
    def test_exact_keyword_scope_and_dated_values(self):
        rows=b.parse_payload(PAYLOAD,TITLE,NOW)
        self.assertEqual([r['source_time'] for r in rows],['2026-11-08','2026-11-09'])
        self.assertEqual(rows[-1]['value'],35380)
        self.assertEqual(rows[-1]['metadata']['series_kind'],'keyword_search')
        self.assertEqual(b.parse_payload(PAYLOAD|{'series':[{'name':TITLE,'data':['0',None]}]},TITLE,NOW)[0]['value'],0)

    def test_brand_news_wrong_keyword_region_device_and_bad_values_rejected(self):
        for changes in [{'url':'https://index.baidu.com/v2/main/index.html#/brand/100679178'},
                        {'title':'今天也是太阳雨'},{'area':'1'},{'device':'wise'},
                        {'series':[{'name':'资讯指数','data':[1,2]}]},
                        {'series':PAYLOAD['series']*2},{'dates':['2026-11-08','2026-11-12']},
                        {'dates':['2026-11-08','2026-11-08']},
                        *[{'series':[{'name':TITLE,'data':[1,x]}]} for x in [True,-1,'NaN','1.5']]]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):b.parse_payload(PAYLOAD|changes,TITLE,NOW)

class RequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_browser_chart_and_evidence(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(b,'EVIDENCE',Path(folder)),patch.object(m.browsers,'baidu_chart',new_callable=AsyncMock,return_value=PAYLOAD) as chart:
            result=await b.collect_baidu_api()
            chart.assert_awaited_once_with(TITLE)
            self.assertEqual(result['state'],'ok')
            self.assertEqual(result['readings'][-1]['value'],35380)
            self.assertEqual(len(list(Path(folder).glob('*.json'))),1)

    async def test_login_failure_never_falls_back_to_personal_browser(self):
        with patch.object(m.browsers,'baidu_chart',new_callable=AsyncMock,return_value={'ready':False,'loginRequired':True}):
            result=await b.collect_baidu_api()
        self.assertEqual(result['state'],'login_required')
        self.assertEqual(result['readings'],[])

    async def test_dedicated_context_is_headless_and_closed_on_failure(self):
        from backend.browser_sources import BrowserWorker
        worker=BrowserWorker()
        context=AsyncMock();page=AsyncMock()
        context.new_page.return_value=page
        page.goto.side_effect=RuntimeError('navigation failed')
        with patch.object(worker,'context',new_callable=AsyncMock,return_value=context) as create:
            with self.assertRaises(RuntimeError):await worker.baidu_chart(TITLE)
            create.assert_awaited_once_with('baidu_index',visible=False)
            context.close.assert_awaited_once()

    async def test_navigation_transition_retries_in_dedicated_browser(self):
        from backend.browser_sources import BrowserWorker, BrowserError
        worker=BrowserWorker();context=AsyncMock();page=AsyncMock()
        context.new_page.return_value=page
        page.evaluate.side_effect=[BrowserError('Execution context was destroyed'),PAYLOAD]
        with patch.object(worker,'context',new_callable=AsyncMock,return_value=context) as create:
            result=await worker.baidu_chart(TITLE)
            self.assertEqual(result,PAYLOAD)
            create.assert_awaited_once_with('baidu_index',visible=False)
            context.close.assert_awaited_once()

class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    setUp=storage.StorageTests.setUp
    tearDown=storage.StorageTests.tearDown

    async def test_corrected_scope_and_failure_preserve_only_keyword_values(self):
        m.save_observation('baidu_index','search_index',82826,'指数','https://index.baidu.com/',
                           '2026-11-09',{'entity_id':'100679178','endpoint':'/insight/brand/queryBrandSearchIndex'})
        m.init_db();m.init_db()
        self.assertEqual(m.get_latest('baidu_index'),[])
        self.assertEqual(m.series('baidu_index',hours=720,all_history=True),[])
        conn=m.db()
        self.assertEqual(conn.execute("SELECT value FROM observations WHERE metric='baidu_brand_search_index_legacy'").fetchone()[0],82826)
        conn.close()
        readings=b.parse_payload(PAYLOAD,TITLE,NOW)
        with patch.object(m,'collect_baidu_api',new_callable=AsyncMock,return_value={'state':'ok','message':'ok','readings':readings}):await m.collect_one('baidu_index')
        with patch.object(m,'collect_baidu_api',new_callable=AsyncMock,return_value={'state':'error','message':'unavailable','readings':[]}):await m.collect_one('baidu_index')
        source=next(s for s in m.sources() if s['id']=='baidu_index')
        self.assertEqual(source['method'],'official_browser')
        self.assertEqual(source['metrics'][0]['value'],35380)
        self.assertEqual(source['state'],'error')
        self.assertEqual([p['value'] for p in m.series('baidu_index',hours=1,all_history=True)],[44560,35380])

if __name__=='__main__':unittest.main()
