from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from backend import broadcast_schedule as s

HTML='''<title>今天是太阳雨播出时间</title><dl class="pro-menu"><dd show="one"><p class="pro-menu-date">11-12</p></dd><dd show="two"><p class="pro-menu-date">11-15</p></dd></dl>
<div id="one"><table><tr><td>湖南卫视</td><td>20:10</td><td>金鹰独播剧场:今天是太阳雨(3)</td></tr><tr><td>湖南卫视</td><td>21:05</td><td>金鹰独播剧场:今天是太阳雨(4)</td></tr><tr><td>其他频道</td><td>21:05</td><td>今天是太阳雨(4)</td></tr></table></div>
<div id="two"><table><tr><td>湖南卫视</td><td>20:10</td><td>今天是太阳雨(5)</td></tr></table></div>'''

class ScheduleTests(unittest.TestCase):
    def test_episode_slots_and_no_invented_friday_broadcast(self):
        rows=s.parse(HTML,datetime(2026,11,12,tzinfo=s.TZ))
        self.assertEqual([r['episodes'] for r in rows],['3','4','5'])
        now=datetime(2026,11,12,22,tzinfo=s.TZ)
        self.assertEqual(next(r for r in rows if datetime.fromisoformat(r['at'])>now)['at'],'2026-11-15T20:10:00+08:00')
        with self.assertRaises(ValueError):s.parse('<title>访问验证</title>',now)

    def test_revision_removes_cancelled_future_slot(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.db';now=datetime(2026,11,12,tzinfo=s.TZ)
            rows=s.parse(HTML,now);s.save(path,rows,now.isoformat())
            s.save(path,rows[1:],now.isoformat())
            self.assertEqual([r['episodes'] for r in s.load(path)],['4','5'])

if __name__=='__main__':unittest.main()
