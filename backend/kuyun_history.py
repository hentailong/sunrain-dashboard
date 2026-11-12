"""Official programme daily means and yesterday's published minute curve."""
import asyncio
from datetime import datetime, timedelta, timezone
import math

import httpx

TZ = timezone(timedelta(hours=8))
ENDPOINT = 'https://www.ky.live/api/epgrate'
PARAMS = {'caid': 1585487, 'tvid': 24, 'area': -1}
FIRST_DAY = '20261111'
_checked = None
_complete = False


def rate(raw):
    if isinstance(raw, bool) or raw is None:
        raise ValueError('Missing rate')
    value = float(raw)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Invalid rate')
    return value * 100


def reading(metric, at, value, **meta):
    return {'metric': metric, 'value': value, 'unit': '%', 'source_time': at,
            'source_url': ENDPOINT, 'metadata': {
                'scope': '酷云官方节目收视 · 湖南卫视 · 全国', 'method': 'official_api',
                'caid': 1585487, 'channel': '湖南卫视', 'statistical_date': at[:10],
                'history_origin': 'official_history', **meta}}


def parse_daily(payload, today):
    if not isinstance(payload, dict) or payload.get('status') is not True:
        raise ValueError('Daily history unavailable')
    result = []
    for row in payload['data']['i']:
        day = datetime.strptime(row['t'], '%Y%m%d').date()
        if not datetime.strptime(FIRST_DAY, '%Y%m%d').date() <= day < today:
            raise ValueError('Wrong daily date')
        result.append(reading('kuyun_daily_rating', day.isoformat(), rate(row['r']), frequency='daily', programme_id=row.get('id')))
    return sorted(result, key=lambda row: row['source_time'])


def parse_minutes(payload, day):
    if not isinstance(payload, dict) or payload.get('status') is not True:
        raise ValueError('Minute history unavailable')
    data = payload['data']
    start = datetime.fromisoformat(data['s']).replace(tzinfo=TZ)
    end = datetime.fromisoformat(data['e']).replace(tzinfo=TZ)
    if start.date() != day or end.date() != day or start > end:
        raise ValueError('Wrong programme date')
    result = []
    for row in data['i']:
        at = datetime.strptime(row['t'], '%Y%m%d%H%M').replace(tzinfo=TZ)
        if not start <= at <= end:
            raise ValueError('Minute outside programme')
        result.append(reading('kuyun_history_rating', at.isoformat(), rate(row['r']), frequency='minute',
                              broadcast_id=f'24:{start.isoformat()}', broadcast_start=start.isoformat(), broadcast_end=end.isoformat()))
    return result


async def collect_history():
    global _checked, _complete
    current = datetime.now(TZ)
    # Refresh finalized history once each day; retry later if yesterday is unpublished.
    if _checked and _checked.date() == current.date() and (_complete or current-_checked < timedelta(minutes=15)):
        return []
    _checked = current; _complete = False
    yesterday = current.date()-timedelta(days=1)
    if yesterday.strftime('%Y%m%d') < FIRST_DAY:
        return []
    daily_params = dict(PARAMS, t=1, begin=FIRST_DAY, end=yesterday.strftime('%Y%m%d'))
    minute_params = dict(PARAMS, t=2, sd=yesterday.strftime('%Y%m%d'), is_his=1)
    async with httpx.AsyncClient(timeout=20) as client:
        responses = await asyncio.gather(client.get(ENDPOINT, params=daily_params),
                                         client.get(ENDPOINT, params=minute_params), return_exceptions=True)
    result = []; successful = []
    for response, parser, date in zip(responses, (parse_daily, parse_minutes), (current.date(), yesterday)):
        try:
            if isinstance(response, Exception): raise ValueError('Request failed')
            response.raise_for_status()
            rows = parser(response.json(), date)
            result.extend(rows)
            successful.append(bool(rows) and (parser != parse_daily or rows[-1]['source_time'] == yesterday.isoformat()))
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            successful.append(False)
    _complete = all(successful)
    return result
