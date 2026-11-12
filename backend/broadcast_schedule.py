"""Verified upcoming Hunan TV slots from the programme's TVMao timetable."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import re
import sqlite3

import httpx
from bs4 import BeautifulSoup

URL='https://www.tvmao.com/kanju/YGsmXGVe/playingtime'
TZ=timezone(timedelta(hours=8))
TITLE='今天是太阳雨'


def initialize(path):
    with closing(sqlite3.connect(path)) as conn,conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS broadcast_schedule (
            at TEXT PRIMARY KEY,episodes TEXT NOT NULL,programme TEXT NOT NULL,verified_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS broadcast_schedule_status (id INTEGER PRIMARY KEY,last_attempt TEXT);''')


def parse(html,current):
    soup=BeautifulSoup(html,'html.parser')
    if not soup.title or TITLE not in soup.title.get_text():raise ValueError('Wrong programme')
    slots=[]
    for tab in soup.select('.pro-menu dd[show]'):
        date=tab.select_one('.pro-menu-date');table=soup.find(id=tab['show'])
        if date is None or table is None:continue
        month,day=map(int,date.get_text(strip=True).split('-'))
        dates=[]
        for year in (current.year-1,current.year,current.year+1):
            try:dates.append(datetime(year,month,day,tzinfo=TZ))
            except ValueError:pass
        date=min(dates,key=lambda d:abs((d-current).total_seconds()))
        if not -8 <= (date.date()-current.date()).days <= 14:continue
        for row in table.select('tr:not(.pro-tr-header)'):
            cells=[c.get_text(strip=True) for c in row.select('td')]
            if len(cells)!=3 or cells[0]!='湖南卫视':continue
            match=re.fullmatch(r'(?:金鹰独播剧场[:：])?'+TITLE+r'[（(](\d+)[)）]',cells[2])
            if not match:continue
            hour,minute=map(int,cells[1].split(':'))
            at=date.replace(hour=hour,minute=minute)
            slots.append({'at':at.isoformat(),'episodes':match[1],'programme':cells[2],'estimated':False})
    if not slots:raise ValueError('No verified programme slots')
    return sorted(slots,key=lambda s:s['at'])


def save(path,slots,verified_at):
    initialize(path)
    with closing(sqlite3.connect(path)) as conn,conn:
        conn.execute('DELETE FROM broadcast_schedule')
        for slot in slots:
            conn.execute('INSERT OR REPLACE INTO broadcast_schedule VALUES(?,?,?,?)',
                (slot['at'],slot['episodes'],slot.get('programme',TITLE),verified_at))


def load(path):
    initialize(path)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory=sqlite3.Row
        return [dict(r,estimated=False) for r in conn.execute('SELECT * FROM broadcast_schedule ORDER BY at')]


async def refresh(path):
    initialize(path);current=datetime.now(TZ)
    with closing(sqlite3.connect(path)) as conn,conn:
        previous=conn.execute('SELECT last_attempt FROM broadcast_schedule_status WHERE id=1').fetchone()
        if previous and current-datetime.fromisoformat(previous[0])<timedelta(minutes=15):return
        conn.execute('INSERT OR REPLACE INTO broadcast_schedule_status VALUES(1,?)',(current.isoformat(),))
    try:
        async with httpx.AsyncClient(timeout=10,follow_redirects=True,headers={'User-Agent':'Mozilla/5.0'}) as client:
            response=await client.get(URL);response.raise_for_status()
        save(path,parse(response.content,current),current.isoformat())
    except (httpx.HTTPError,ValueError,TypeError):
        # Keep the last verified timetable when the source is unavailable.
        return
