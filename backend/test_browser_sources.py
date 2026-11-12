import unittest
from datetime import datetime, timedelta

from backend.browser_sources import TITLE, numeric, parse_packets


class PublicSourceTests(unittest.TestCase):
    def test_only_requested_drama_is_stored(self):
        data={'status':True,'dataList':{'list':[
            {'seriesInfo':{'name':'其他剧'},'barValue':9000},
            {'seriesInfo':{'name':TITLE,'seriesId':1515813},'currHeat':'\uecdc\ue8d7','barValue':4840.1},
        ]},'webHeatDetail':{'data':{'seriesInfo':{'name':TITLE,'seriesId':1515813},
            'heatTrends':[{'date':20261108,'heat':9447.16},{'date':20261109,'heat':5069.47}]}}}
        result=parse_packets('maoyan',[{'data':data}])
        self.assertEqual(result[0]['value'],2)
        self.assertEqual([r['value'] for r in result if r['metric']=='daily_heat'],[9447.16,5069.47])
        self.assertFalse(any(r['metric']=='web_heat' for r in result))
        self.assertEqual(result[-1]['source_time'],'2026-11-09')

    def test_no_values_from_other_drama_details(self):
        result=parse_packets('maoyan',[{'data':{'data':{'seriesInfo':{'name':'其他剧'},'heatTrends':[{'date':20261108,'heat':123}]}}}])
        self.assertEqual(result,[])

    def test_current_day_trend_has_separate_snapshot_without_date_timestamp(self):
        from backend.main import now
        today=now().date()
        yesterday=today-timedelta(days=1)
        packet={'data':{'data':{'seriesInfo':{'name':TITLE,'seriesId':1515813},'heatTrends':[
            {'date':int(yesterday.strftime('%Y%m%d')),'heat':9603.01},
            {'date':int(today.strftime('%Y%m%d')),'heat':2753.87}]}}}
        rows=parse_packets('maoyan',[packet])
        snapshots=[r for r in rows if r['metric']=='maoyan_heat_snapshot']
        self.assertEqual(len(snapshots),1)
        self.assertEqual(snapshots[0]['value'],2753.87)
        self.assertIsNone(snapshots[0]['source_time'])
        self.assertEqual(snapshots[0]['metadata']['statistical_date'],today.isoformat())

    def test_encoded_glyphs_and_nonfinite_values_rejected(self):
        for value in ('\uecdc\ue8d7', '暂无数据', float('nan'), float('inf'), True, None):
            self.assertIsNone(numeric(value))

    def test_login_payload_does_not_count_as_success(self):
        self.assertEqual(parse_packets('yunhe',[{'data':{'status':200,'message':'需要登录'}}]),[])

    def test_nested_title_records(self):
        values=parse_packets('yunhe',[{'data':{'rows':[{'name':TITLE,'effectivePlayCount':12000},{'name':'其他剧','effectivePlayCount':99999}]}}])
        self.assertEqual(values[0]['value'],12000)

if __name__=='__main__':
    unittest.main()
