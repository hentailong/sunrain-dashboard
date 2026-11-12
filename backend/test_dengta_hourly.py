import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend import dengta_hourly as h

NOW = datetime(2026,11,11,10,40,tzinfo=h.TZ)
ROW = {'mediaId':1514343,'dateType':'HOUR','showDate':'20261111','hh':'9点-10点','vvCnt':483752,'marketShare':'6.84%'}


def payload(rows):
    return {'ret':['SUCCESS::ok'],'data':{'code':'200','dataList':rows,'ts':int(NOW.timestamp()*1000)}}


class ParseTests(unittest.TestCase):
    def test_raw_hourly_values_and_units(self):
        rows=h.parse_payload(payload([ROW]),NOW)
        self.assertEqual(rows,[{'day':'2026-11-11','hour':9,'plays':483752,'share':6.84}])

    def test_invalid_or_incomplete_hours_are_not_stored(self):
        for changes in [{'hh':'10点-11点'},{'hh':'9点-11点'},{'vvCnt':-1},{'vvCnt':True},
                        {'marketShare':'2.5'},{'marketShare':'101%'},{'mediaId':1577466},
                        {'showDate':'20261112'},{'dateType':'DAY'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                h.parse_payload(payload([ROW|changes]),NOW)
        with self.assertRaises(ValueError):
            h.parse_payload(payload([ROW,ROW]),NOW)
        stale=payload([ROW]);stale['data']['ts']-=3*3600000
        with self.assertRaises(ValueError):h.parse_payload(stale,NOW)


class ArchiveTests(unittest.IsolatedAsyncioTestCase):
    def test_complete_last_hour_revisions_and_official_override(self):
        from backend.dengta_daily import initialize as daily_init
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.db';h.initialize(path);daily_init(path)
            with closing(sqlite3.connect(path)) as conn,conn:
                conn.execute('INSERT INTO dengta_daily VALUES(?,?,?,?,?)',('2026-11-10',2400,5,NOW.isoformat(),'daily'))
                for hour in range(23):conn.execute('INSERT INTO dengta_hourly VALUES(?,?,?,?,?,?)',('2026-11-10',hour,100,5,NOW.isoformat(),'hourly'))
            rows=h.hourly_data(path,NOW)['rows']
            self.assertEqual(len(rows),24);self.assertEqual(rows[-1]['plays'],100)
            self.assertIsNone(rows[-1]['share'])
            self.assertEqual(rows[-1]['calculation'],'daily_total_minus_hours_0_22')
            with closing(sqlite3.connect(path)) as conn,conn:conn.execute('UPDATE dengta_daily SET plays=2450')
            self.assertEqual(h.hourly_data(path,NOW)['rows'][-1]['plays'],150)
            with closing(sqlite3.connect(path)) as conn,conn:conn.execute("UPDATE dengta_hourly SET plays=160,source_url='official-hour' WHERE hour=23")
            self.assertEqual(h.hourly_data(path,NOW)['rows'][-1]['plays'],160)

    def test_gaps_and_unfinished_days_are_not_completed(self):
        from backend.dengta_daily import initialize as daily_init
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.db';h.initialize(path);daily_init(path)
            with closing(sqlite3.connect(path)) as conn,conn:
                for day,count,total in [('2026-11-10',22,2400),('2026-11-11',23,2400),('2026-11-09',23,2000)]:
                    conn.execute('INSERT INTO dengta_daily VALUES(?,?,?,?,?)',(day,total,5,NOW.isoformat(),'daily'))
                    for hour in range(count):conn.execute('INSERT INTO dengta_hourly VALUES(?,?,?,?,?,?)',(day,hour,100,5,NOW.isoformat(),'hourly'))
            h.complete_last_hour(path,NOW)
            with closing(sqlite3.connect(path)) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM dengta_hourly WHERE hour=23').fetchone()[0],0)

    async def test_revisions_keep_yesterday_and_failure_keeps_last_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.db';h.initialize(path)
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute('INSERT INTO dengta_hourly VALUES(?,?,?,?,?,?)',('2026-11-10',9,500000,7,'2026-11-10T11:00:00+08:00','https://example.com'))
            with patch.object(h,'datetime') as clock,patch.object(h,'EVIDENCE',Path(directory)),patch.object(h,'request_board',new_callable=AsyncMock) as request:
                clock.now.return_value=NOW;clock.strptime.side_effect=datetime.strptime
                request.return_value=payload([ROW]);await h.refresh_hourly(path)
                request.return_value=payload([ROW|{'vvCnt':490000}]);await h.refresh_hourly(path)
                before=h.hourly_data(path,NOW)
                self.assertEqual(len(before['rows']),2)
                self.assertEqual(before['rows'][-1]['plays'],490000)
                request.return_value={'ret':['FAIL']};await h.refresh_hourly(path)
                after=h.hourly_data(path,NOW)
                self.assertEqual(after['rows'],before['rows'])
                self.assertEqual(after['status']['last_success'],before['status']['last_success'])
                self.assertEqual(after['status']['state'],'error')
                request.return_value=payload([]);await h.refresh_hourly(path)
                self.assertEqual(h.hourly_data(path,NOW)['rows'],before['rows'])


if __name__=='__main__':unittest.main()
