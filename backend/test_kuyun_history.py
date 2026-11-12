import copy
from datetime import date, datetime
import unittest
from unittest.mock import patch

import httpx
from backend import kuyun_history as h, kuyun_api as k, main as m, test_storage as storage

DAILY={'status':True,'data':{'i':[{'t':'20261111','r':.003846,'id':88173632}]}}
MINUTES={'status':True,'data':{'s':'2026-11-11 20:08','e':'2026-11-11 21:57','i':[
    {'t':'202611112008','r':.002532},{'t':'202611112157','r':.003197}]}}
SUMMARY={'status':True,'data':[{'basic':{'tvid':24,'tvn':'湖南卫视','epg':m.TITLE,'tv_type':'省级卫视'},
    'his':{'avg_rate':.003846,'avg_date':'2026-11-11','his_top_avg_rate':.003846,'his_top_avg_date':'2026-11-11',
           'his_top_rate':.004504,'his_top_time':'2026-11-11 20:28:26','his_top_type':'sec','avg_tv_rk':1}}]}


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    setUp=storage.StorageTests.setUp
    tearDown=storage.StorageTests.tearDown

    def test_official_daily_mean_and_minute_times(self):
        daily=h.parse_daily(DAILY,date(2026,11,12))
        self.assertEqual(daily[0]['value'],.3846)
        self.assertEqual(daily[0]['source_time'],'2026-11-11')
        minutes=h.parse_minutes(MINUTES,date(2026,11,11))
        self.assertEqual(len(minutes),2)
        self.assertEqual(minutes[0]['source_time'],'2026-11-11T20:08:00+08:00')
        self.assertEqual(minutes[0]['value'],.2532)
        # Official samples are retained; we do not fill the intervening minutes.

    def test_wrong_dates_nonfinite_and_outside_broadcast_rejected(self):
        with self.assertRaises(ValueError):h.parse_daily(DAILY,date(2026,11,11))
        with self.assertRaises(ValueError):h.parse_minutes(MINUTES,date(2026,11,12))
        for value in (None,True,-1,2,'nan'):
            payload=copy.deepcopy(DAILY);payload['data']['i'][0]['r']=value
            with self.assertRaises(ValueError):h.parse_daily(payload,date(2026,11,12))
        payload=copy.deepcopy(MINUTES);payload['data']['i'][0]['t']='202611112007'
        with self.assertRaises(ValueError):h.parse_minutes(payload,date(2026,11,11))

    def test_backfill_cannot_replace_latest_daily_card_or_live_rating(self):
        m.save_observation('kuyun','kuyun_daily_rating',.4,'%','test','2026-11-12')
        m.save_observation('kuyun','kuyun_daily_rating',.3846,'%','test','2026-11-11')
        m.save_observation('kuyun','kuyun_live_rating',.5,'%','test','2026-11-12T20:10:00+08:00')
        m.save_observation('kuyun','kuyun_history_rating',.25,'%','test','2026-11-11T20:08:00+08:00')
        readings={r['metric']:r['value'] for r in m.get_latest('kuyun')}
        self.assertEqual(readings,{'kuyun_daily_rating':.4,'kuyun_live_rating':.5})

    def test_official_rank_scope_and_second_peak(self):
        readings={r['metric']:r for r in k.parse_summary(SUMMARY)}
        self.assertEqual(readings['kuyun_peak_rating']['value'],.4504)
        self.assertEqual(readings['kuyun_provincial_rank']['value'],1)
        self.assertEqual(readings['kuyun_provincial_rank']['metadata']['rank_scope'],'省级卫视')
        payload=copy.deepcopy(SUMMARY);payload['data'][0]['basic']['tv_type']='全部频道'
        self.assertNotIn('kuyun_provincial_rank',[r['metric'] for r in k.parse_summary(payload)])

    async def test_daily_sync_once_and_retry_unpublished(self):
        real=httpx.AsyncClient;requests=[]
        def handle(request):
            requests.append(request)
            return httpx.Response(200,json=DAILY if request.url.params['t']=='1' else MINUTES)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,11,12,10,tzinfo=h.TZ)
        with patch.object(h,'_checked',None),patch.object(h,'_complete',False),patch.object(h,'datetime',Clock),patch.object(h.httpx,'AsyncClient',side_effect=lambda **kw:real(**kw,transport=httpx.MockTransport(handle))):
            self.assertEqual(len(await h.collect_history()),3)
            self.assertEqual(await h.collect_history(),[])
            self.assertEqual(len(requests),2)


if __name__=='__main__':unittest.main()
