"""Archive official completed-hour data; never derive hours from live totals."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import httpx

from backend.dengta_api import EVIDENCE, PAGE, TZ, number, request_board

API = 'mtop.alipictures.gravitywave.media.vv.detail.list'
PARAMS = {'mediaId': 1514343, 'platform': 'ALL', 'dateType': 'HOUR'}


def initialize(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS dengta_hourly (
                day TEXT NOT NULL, hour INTEGER NOT NULL, plays INTEGER NOT NULL,
                share REAL, collected_at TEXT NOT NULL, source_url TEXT NOT NULL,
                PRIMARY KEY(day,hour));
            CREATE TABLE IF NOT EXISTS dengta_hourly_status (
                id INTEGER PRIMARY KEY CHECK(id=1), state TEXT, message TEXT,
                last_attempt TEXT, last_success TEXT);
        ''')


def parse_payload(payload, current):
    if not isinstance(payload, dict) or not any(str(r).startswith('SUCCESS::') for r in payload.get('ret', [])):
        raise ValueError('接口未返回成功状态')
    data = payload.get('data', {})
    if str(data.get('code')) != '200' or not isinstance(data.get('dataList'), list):
        raise ValueError('分时数据结构异常')
    source_ms = number(data.get('ts'))
    if source_ms is None or not -300 <= current.timestamp()-source_ms/1000 <= 7200:
        raise ValueError('分时响应时间异常')
    rows = []
    seen = set()
    for item in data['dataList']:
        if not isinstance(item, dict) or item.get('mediaId') != PARAMS['mediaId'] or item.get('dateType') != 'HOUR':
            raise ValueError('剧集或分时口径不符')
        day = datetime.strptime(str(item.get('showDate')), '%Y%m%d').replace(tzinfo=TZ)
        match = re.fullmatch(r'(\d{1,2})点-(\d{1,2})点', str(item.get('hh', '')))
        if not match:
            raise ValueError('未知小时格式')
        hour, end = map(int, match.groups())
        if not 0 <= hour < 24 or end not in ((hour+1)%24, hour+1):
            raise ValueError('小时范围异常')
        if day.date() > current.date() or day+timedelta(hours=hour+1) > current:
            raise ValueError('未闭合时段不能进入分时图')
        key = (day.date().isoformat(), hour)
        if key in seen:
            raise ValueError('重复小时')
        seen.add(key)
        plays = number(item.get('vvCnt'))
        raw_share = item.get('marketShare')
        if raw_share in (None, '', '--', '-'):
            share = None
        elif isinstance(raw_share, str) and raw_share.endswith('%'):
            share = number(raw_share[:-1])
            if share is None or not 0 <= share <= 100:
                raise ValueError('市占率异常')
        else:
            raise ValueError('市占率单位异常')
        if plays is None or plays < 0 or plays != int(plays):
            raise ValueError('分时播放量异常')
        rows.append({'day': key[0], 'hour': hour, 'plays': int(plays), 'share': share})
    return rows


async def refresh_hourly(path):
    current = datetime.now(TZ)
    initialize(path)
    try:
        async with httpx.AsyncClient(timeout=20, headers={'Referer': PAGE, 'User-Agent': 'Mozilla/5.0'}) as client:
            payload = await request_board(client, PARAMS, api=API, version='1.0')
        rows = parse_payload(payload, current)
        if rows and max(r['day'] for r in rows) != current.date().isoformat():
            raise ValueError('接口仅返回旧日期，保留档案')
        content = json.dumps({'api': API, 'parameters': PARAMS, 'captured_at': current.isoformat(),
                              'response': payload}, ensure_ascii=False, indent=2)
        name = hashlib.sha256(content.encode()).hexdigest()+'.json'
        EVIDENCE.mkdir(exist_ok=True)
        (EVIDENCE/name).write_text(content, encoding='utf-8')
        url = 'http://127.0.0.1:8000/api/evidence/'+name
        with closing(sqlite3.connect(path)) as conn, conn:
            for row in rows:
                conn.execute('INSERT INTO dengta_hourly VALUES(?,?,?,?,?,?) ON CONFLICT(day,hour) DO UPDATE SET plays=excluded.plays,share=excluded.share,collected_at=excluded.collected_at,source_url=excluded.source_url',
                             (row['day'],row['hour'],row['plays'],row['share'],current.isoformat(),url))
            conn.execute("INSERT INTO dengta_hourly_status VALUES(1,'ok','已更新官方完整小时数据',?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,message=excluded.message,last_attempt=excluded.last_attempt,last_success=excluded.last_success",(current.isoformat(),current.isoformat()))
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("INSERT INTO dengta_hourly_status VALUES(1,'error',?,?,NULL) ON CONFLICT(id) DO UPDATE SET state=excluded.state,message=excluded.message,last_attempt=excluded.last_attempt",
                         ('分时更新失败，保留此前记录：'+type(exc).__name__,current.isoformat()))


def complete_last_hour(path, current=None):
    """Close one missing 23:00 slot from a finished official daily total.

    Keep provenance in storage; an actual hourly response always takes priority.
    """
    current = current or datetime.now(TZ)
    initialize(path)
    marker = 'daily-total-remainder:'
    with closing(sqlite3.connect(path)) as conn, conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dengta_daily'").fetchone():return
        for day, total, captured, url in conn.execute('SELECT day,plays,collected_at,source_url FROM dengta_daily WHERE day<?',(current.date().isoformat(),)).fetchall():
            rows=conn.execute('SELECT hour,plays,source_url FROM dengta_hourly WHERE day=? ORDER BY hour',(day,)).fetchall()
            known=[r for r in rows if r[0]<23]
            last=next((r for r in rows if r[0]==23),None)
            if [r[0] for r in known]!=list(range(23)) or (last and not last[2].startswith(marker)):continue
            remainder=total-sum(r[1] for r in known)
            if remainder<0:continue
            conn.execute('INSERT INTO dengta_hourly VALUES(?,?,?,?,?,?) ON CONFLICT(day,hour) DO UPDATE SET plays=excluded.plays,collected_at=excluded.collected_at,source_url=excluded.source_url',
                         (day,23,remainder,None,captured,marker+url))


def hourly_data(path, current=None):
    current = current or datetime.now(TZ)
    today = current.date().isoformat()
    yesterday = (current-timedelta(days=1)).date().isoformat()
    initialize(path)
    complete_last_hour(path,current)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute('SELECT * FROM dengta_hourly WHERE day IN (?,?) ORDER BY day,hour',(today,yesterday))]
        for row in rows:
            if row['source_url'].startswith('daily-total-remainder:'):row['calculation']='daily_total_minus_hours_0_22'
        status = conn.execute('SELECT * FROM dengta_hourly_status WHERE id=1').fetchone()
    return {'today': today, 'yesterday': yesterday, 'rows': rows, 'status': dict(status) if status else {'state':'pending'},
            'collection_interval_minutes':1, 'timezone':'Asia/Shanghai'}
