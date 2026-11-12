"""Collect the official live TV board, attributing only verified programme slots."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re

import httpx

from backend.dramas import PRIMARY
from backend.yunhe_api import EVIDENCE
from backend.kuyun_history import collect_history

TZ = timezone(timedelta(hours=8))
PAGE = 'https://www.ky.live/'
ENDPOINT = 'https://www.ky.live/api/rtepg'
PARAMS = {'tv_type': 0, 'ca_type': 0, 'area': -1, 'end': 0, 'rt': 1}
SUMMARY_ENDPOINT = 'https://www.ky.live/api/epg_summary/lb_rating'
SUMMARY_PARAMS = {'caid': 1585487, 'tvid': 24, 'area': -1}
_summary_cache = None
_summary_checked = None


def parse_summary(payload):
    if not isinstance(payload, dict) or payload.get('status') is not True:
        return []
    rows = [r for r in payload.get('data', []) if isinstance(r, dict)
            and r.get('basic', {}).get('tvid') == 24 and r.get('basic', {}).get('epg') == PRIMARY
            and r.get('basic', {}).get('tvn') == '湖南卫视']
    if len(rows) != 1:
        return []
    row = rows[0]; h = row.get('his', {}); result = []
    fields = [('avg_rate','kuyun_daily_rating','avg_date'),
              ('his_top_avg_rate','kuyun_highest_daily_rating','his_top_avg_date'),
              ('his_top_rate','kuyun_peak_rating','his_top_time'),
              ('avg_tv_rk','kuyun_provincial_rank','avg_date')]
    for field, metric, date_field in fields:
        value = h.get(field); date = h.get(date_field)
        try:
            if isinstance(value, bool) or value is None or not date: continue
            value = float(value); at = timestamp(date)
            if not math.isfinite(value) or at > datetime.now(TZ): continue
            rank = metric.endswith('_rank')
            if rank and (value < 1 or value != int(value)): continue
            if not rank and not 0 <= value <= 1: continue
            if rank and row['basic'].get('tv_type') != '省级卫视': continue
            result.append({'metric':metric,'value':value if rank else value*100,'unit':'名' if rank else '%',
                'source_time':at.isoformat() if field=='his_top_rate' else at.date().isoformat(),
                'source_url':SUMMARY_ENDPOINT,'metadata':{'scope':'酷云官方节目历史收视 · 湖南卫视 · 全国',
                    'field':field,'frequency':'daily','method':'official_api','statistical_date':at.date().isoformat(),
                    'programme':PRIMARY,'episodes':h.get('avg_episode'),
                    'rank_scope':'省级卫视' if rank else None,'peak_resolution':h.get('his_top_type') if field=='his_top_rate' else None}})
        except (ValueError, TypeError): continue
    return result


async def collect_summary():
    global _summary_cache, _summary_checked
    current = datetime.now(TZ)
    if _summary_checked and (current-_summary_checked).total_seconds()<900:
        return _summary_cache or []
    _summary_checked = current
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.get(SUMMARY_ENDPOINT,params=SUMMARY_PARAMS)
            response.raise_for_status(); payload=response.json()
        readings=parse_summary(payload)
        if readings:
            content=json.dumps({'source':SUMMARY_ENDPOINT,'parameters':SUMMARY_PARAMS,'captured_at':current.isoformat(),'response':payload},ensure_ascii=False)
            name=hashlib.sha256(content.encode()).hexdigest()+'.json'; EVIDENCE.mkdir(exist_ok=True)
            (EVIDENCE/name).write_text(content,encoding='utf-8')
            for r in readings:r['metadata']['evidence_id']=name[:-5]
            _summary_cache=readings
    except (httpx.HTTPError, ValueError, TypeError): pass
    return _summary_cache or []
BROADCAST = {
    'channel': '湖南卫视', 'channel_id': 24,
    'premiere_at': '2026-11-11T20:10:00+08:00',
    'announcement_url': 'https://mbd.baidu.com/newspage/data/dtlandingsuper?nid=dt_3879848374076411388',
    # Verified against Hunan TV's second-week drama calendar. Do not extrapolate
    # unannounced dates: Friday/Saturday are explicitly blank for television.
    'schedule': [
        {'at': '2026-11-11T20:10:00+08:00', 'episodes': '1–2', 'estimated': True},
        {'at': '2026-11-12T20:10:00+08:00', 'episodes': '3–4', 'estimated': True},
        {'at': '2026-11-15T20:10:00+08:00', 'episodes': '5–6', 'estimated': True},
    ],
}


def timestamp(value):
    parsed = datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)


def parse_payload(payload, current=None):
    current = current or datetime.now(TZ)
    def result(state, message, readings=None):
        return {'state': state, 'message': message, 'page_url': PAGE, 'readings': readings or []}
    if not isinstance(payload, dict) or payload.get('status') is not True or not isinstance(payload.get('data'), list):
        return result('error', '酷云未返回有效实时榜，稍后重试')
    rows = [r for r in payload['data'] if isinstance(r, dict) and r.get('tvid') == BROADCAST['channel_id']]
    if len(rows) != 1:
        return result('no_data', '酷云实时榜未能唯一匹配湖南卫视频道，未更新收视率')
    row = rows[0]
    try:
        when, start, end = (timestamp(row[k]) for k in ('rt_time', 'start_time', 'end_time'))
        if not (timedelta(seconds=-30) <= current - when <= timedelta(minutes=3)) or not (start <= when < end and start <= current < end):
            raise ValueError('stale or wrong programme slot')
        if row.get('tvn') != BROADCAST['channel']:
            raise ValueError('channel changed')
    except (ValueError, KeyError, TypeError):
        return result('error', '酷云频道或数据时间异常，未将旧收视率当作直播数据')
    programme = str(row.get('epg', '')).strip()
    if not re.fullmatch(re.escape(PRIMARY) + r'(?:\s*(?:第\s*)?\d+\s*(?:集)?)?', programme):
        return result('off_air', f'湖南卫视当前节目为《{programme}》，本剧未在播；每分钟检查节目单')
    readings = []
    try:
        for field, metric in (('r', 'kuyun_live_rating'), ('mr', 'kuyun_live_share')):
            raw = row[field]
            if isinstance(raw, bool):
                raise ValueError('boolean rate')
            value = float(raw)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('invalid rate')
            readings.append({'metric': metric, 'value': value * 100, 'unit': '%',
                'source_time': when.isoformat(), 'source_url': PAGE,
                'metadata': {'scope': '酷云实时收视 · 湖南卫视 · 本剧播出时段',
                    'method': 'official_api', 'channel': row['tvn'], 'programme': programme,
                    'broadcast_id': f'{row["tvid"]}:{start.isoformat()}',
                    'broadcast_start': start.isoformat(), 'broadcast_end': end.isoformat(),
                    'statistical_date': when.date().isoformat(), 'field': field, 'official_url': ENDPOINT}})
    except (ValueError, TypeError, KeyError):
        return result('error', '酷云本剧收视字段异常，本轮未写入数值')
    return result('ok', f'正在播出《{programme}》 · 湖南卫视 · 酷云收视每分钟检查', readings)


async def collect_kuyun_api():
    summary = await collect_summary()
    history = await collect_history()
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers={'Referer': PAGE, 'User-Agent': 'Mozilla/5.0'}) as client:
            response = await client.get(ENDPOINT, params=PARAMS)
            response.raise_for_status()
            payload = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        return {'state': 'error', 'message': '酷云实时接口暂不可用，保留历史并稍后重试', 'page_url': PAGE, 'readings': history + summary}
    result = parse_payload(payload)
    if result['readings']:
        content = json.dumps({'source': ENDPOINT, 'parameters': PARAMS, 'captured_at': datetime.now(TZ).isoformat(),
            'data': [r for r in payload['data'] if r.get('tvid') == BROADCAST['channel_id']]}, ensure_ascii=False, indent=2)
        name = hashlib.sha256(content.encode()).hexdigest() + '.json'
        EVIDENCE.mkdir(exist_ok=True)
        (EVIDENCE / name).write_text(content, encoding='utf-8')
        for reading in result['readings']:
            reading['source_url'] = 'http://127.0.0.1:8000/api/evidence/' + name
    result['readings'].extend(history + summary)
    return result
