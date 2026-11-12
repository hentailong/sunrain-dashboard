from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from backend import dengta_daily as d

NOW=datetime(2026,11,11,12,tzinfo=d.TZ)
ROW={'mediaId':1514343,'dateType':'DAY','showDate':'20261110','vvCnt':13573620,'totalVv':58438648,'marketShare':'5.26%'}

def payload(rows):
    return {'ret':['SUCCESS::ok'],'data':{'code':'200','dataList':rows,'ts':int(NOW.timestamp()*1000)}}

class DailyParserTests(unittest.TestCase):
    def test_daily_plays_not_cumulative_total_and_zero_is_valid(self):
        self.assertEqual(d.parse_payload(payload([ROW]),NOW),[{'day':'2026-11-10','plays':13573620,'share':5.26}])
        self.assertEqual(d.parse_payload(payload([ROW|{'vvCnt':0,'marketShare':'0%'}]),NOW)[0]['plays'],0)

    def test_invalid_stale_and_duplicate_rows_are_rejected(self):
        for changes in [{'mediaId':1},{'dateType':'HOUR'},{'showDate':'20261112'},
                        {'vvCnt':True},{'vvCnt':-1},{'vvCnt':1.5},{'vvCnt':'NaN'},
                        {'marketShare':'5.26'},{'marketShare':'101%'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                d.parse_payload(payload([ROW|changes]),NOW)
        stale=payload([ROW]);stale['data']['ts']-=3*3600000
        for invalid in [stale,payload([ROW,ROW]),payload([]),payload([None]),{'ret':['SUCCESS::ok'],'data':None}]:
            with self.assertRaises(ValueError):d.parse_payload(invalid,NOW)

class DailyArchiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_revisions_and_failures_preserve_all_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.db'
            with patch.object(d,'datetime') as clock,patch.object(d,'EVIDENCE',Path(folder)),patch.object(d,'request_board',new_callable=AsyncMock) as request:
                clock.now.return_value=NOW;clock.strptime.side_effect=datetime.strptime
                request.return_value=payload([ROW]);await d.refresh_daily(path)
                request.return_value=payload([ROW|{'showDate':'20261111','vvCnt':4191178}]);await d.refresh_daily(path)
                request.return_value=payload([ROW|{'vvCnt':13574000}]);await d.refresh_daily(path)
                before=d.daily_data(path)
                self.assertEqual([p['value'] for p in before['points'] if p['metric']=='dengta_play_count'],[13574000,4191178])
                self.assertEqual(request.call_args.kwargs,{'api':d.API,'version':'1.0'})
                request.return_value={'ret':['FAIL']};await d.refresh_daily(path)
                after=d.daily_data(path)
                self.assertEqual(before['points'],after['points'])
                self.assertEqual(before['status']['last_success'],after['status']['last_success'])
                self.assertEqual(after['status']['state'],'error')

if __name__=='__main__':unittest.main()
