"""Official per-day Dengta archive, separate from live snapshots and hourly data."""
from contextlib import closing
from datetime import datetime
import hashlib
import json
import sqlite3

import httpx
from backend.dengta_api import PAGE, TZ, EVIDENCE, number, request_board

API='mtop.alipictures.gravitywave.media.vv.detail.list'
PARAMS={'mediaId':1514343,'platform':'ALL','dateType':'DAY'}


def initialize(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS dengta_daily (
          day TEXT PRIMARY KEY, plays INTEGER NOT NULL, share REAL NOT NULL,
          collected_at TEXT NOT NULL, source_url TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS dengta_daily_status (
          id INTEGER PRIMARY KEY CHECK(id=1),state TEXT,message TEXT,last_success TEXT);''')


def parse_payload(payload,current):
    if not isinstance(payload,dict) or not any(str(r).startswith('SUCCESS::') for r in payload.get('ret',[])):
        raise ValueError('请求未成功')
    data=payload.get('data',{})
    if not isinstance(data,dict):raise ValueError('数据结构异常')
    when=number(data.get('ts'))
    if str(data.get('code'))!='200' or not isinstance(data.get('dataList'),list) or when is None or not -300<=current.timestamp()-when/1000<=7200:
        raise ValueError('数据结构或时间异常')
    result=[];seen=set()
    for row in data['dataList']:
        if not isinstance(row,dict) or row.get('mediaId')!=1514343 or row.get('dateType')!='DAY':
            raise ValueError('剧集或周期不符')
        day=datetime.strptime(str(row.get('showDate')),'%Y%m%d').date()
        plays=number(row.get('vvCnt'))
        raw=row.get('marketShare')
        share=number(raw[:-1]) if isinstance(raw,str) and raw.endswith('%') else None
        if day>current.date() or day in seen or plays is None or plays<0 or plays!=int(plays) or share is None or not 0<=share<=100:
            raise ValueError('日期、播放量或市占异常')
        seen.add(day);result.append({'day':day.isoformat(),'plays':int(plays),'share':share})
    if not result:raise ValueError('未返回逐日数据')
    return result


async def refresh_daily(path):
    initialize(path);current=datetime.now(TZ)
    try:
        async with httpx.AsyncClient(timeout=20,headers={'Referer':PAGE,'User-Agent':'Mozilla/5.0'}) as client:
            payload=await request_board(client,PARAMS,api=API,version='1.0')
        rows=parse_payload(payload,current)
        content=json.dumps({'api':API,'parameters':PARAMS,'captured_at':current.isoformat(),'response':payload},ensure_ascii=False,indent=2)
        name=hashlib.sha256(content.encode()).hexdigest()+'.json';EVIDENCE.mkdir(exist_ok=True)
        (EVIDENCE/name).write_text(content,encoding='utf-8');url='http://127.0.0.1:8000/api/evidence/'+name
        with closing(sqlite3.connect(path)) as conn,conn:
            for row in rows:
                conn.execute('INSERT INTO dengta_daily VALUES(?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET plays=excluded.plays,share=excluded.share,collected_at=excluded.collected_at,source_url=excluded.source_url',
                             (row['day'],row['plays'],row['share'],current.isoformat(),url))
            conn.execute("INSERT INTO dengta_daily_status VALUES(1,'ok','已更新官方逐日数据',?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,message=excluded.message,last_success=excluded.last_success",(current.isoformat(),))
    except (httpx.HTTPError,ValueError,TypeError,KeyError) as exc:
        with closing(sqlite3.connect(path)) as conn,conn:
            conn.execute("INSERT INTO dengta_daily_status VALUES(1,'error',?,NULL) ON CONFLICT(id) DO UPDATE SET state=excluded.state,message=excluded.message",('官方逐日数据更新失败，保留此前历史：'+type(exc).__name__,))


def daily_data(path):
    initialize(path)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory=sqlite3.Row
        rows=[dict(row) for row in conn.execute('SELECT * FROM dengta_daily ORDER BY day')]
        status=conn.execute('SELECT * FROM dengta_daily_status WHERE id=1').fetchone()
    points=[]
    for row in rows:
        for metric,field,unit in [('dengta_play_count','plays','次'),('dengta_play_share','share','%')]:
            points.append({'metric':metric,'time':row['day'],'source_time':row['day'],'value':row[field],'unit':unit,
                           'collected_at':row['collected_at'],'url':row['source_url'],
                           'metadata':{'statistical_date':row['day'],'scope':'灯塔官方逐日正片播放','frequency':'daily'}})
    return {'points':points,'status':dict(status) if status else {'state':'pending'}}
