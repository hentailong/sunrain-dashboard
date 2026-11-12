"""Official drama leaderboard, discovered from the PC rank card's own entry.

The official rank template maps tvSeries to entertainment_teleplay_v2,
billboard_type=2 to the real-time board, and score to its heat display.
This public GET requires neither browser cookies nor request signatures.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx

from backend.dramas import DRAMAS, PRIMARY, DOUYIN_RANK_URL

ENDPOINT = 'https://api.amemv.com/web/api/ent/billboard/info/'
PARAMS = {'chart_key':'entertainment_teleplay_v2','count':10,'version':0,'billboard_type':2,'movie_type':0}
DATA_URL = ENDPOINT + '?' + urlencode(PARAMS)
EVIDENCE = Path(__file__).resolve().parent / 'evidence'
TZ = timezone(timedelta(hours=8))


def number(value):
    if value is None or isinstance(value,bool):
        return None
    try:
        value = float(value)
    except (TypeError,ValueError):
        return None
    return value if math.isfinite(value) else None


def parse_payload(payload, title_name=PRIMARY):
    if not isinstance(payload,dict) or payload.get('status_code') != 0:
        return []
    stamp = number(payload.get('active_time'))
    rows = payload.get('data')
    if stamp is None or not 946684800 <= stamp <= 4102444800 or not isinstance(rows,list):
        return []
    matches = [r for r in rows if isinstance(r,dict) and isinstance(r.get('item_info'),dict)
               and r['item_info'].get('nickname') == title_name]
    if len(matches) != 1:
        return []
    row = matches[0]
    heat = number(row.get('score'))
    rank = number(row['item_info'].get('rank'))
    if heat is None or heat < 0 or rank is None or rank < 1 or rank != int(rank):
        return []
    stamp = datetime.fromtimestamp(stamp,TZ).isoformat()
    meta = {'scope':'抖音剧集榜 · 实时榜','method':'official_api','frequency':'hourly',
            'chart_key':PARAMS['chart_key'],'billboard_type':2,'item_id':row.get('item_id'),
            'title':title_name,'sample_size':len(rows),'rank_page_url':DOUYIN_RANK_URL,
            'official_url':DATA_URL,'precision':'官方接口原始数值；PC卡片会按万／亿四舍五入'}
    return [{'metric':metric,'value':value,'unit':unit,'source_time':stamp,'source_url':DATA_URL,
             'metadata':dict(meta,field=field)}
            for metric,value,unit,field in [('douyin_drama_heat',heat,'热度','score'),
                                          ('douyin_drama_rank',rank,'名','item_info.rank')]]


def save_evidence(payload):
    # Save only leaderboard fields; no cookies, headers, avatars or app links.
    data = {'active_time':payload.get('active_time'),'status_code':payload.get('status_code'),
            'has_more':payload.get('has_more'),'data':[
                {'item_id':row.get('item_id'),'item_info':{
                    'nickname':row.get('item_info',{}).get('nickname'),
                    'rank':row.get('item_info',{}).get('rank')},'score':row.get('score')}
                for row in payload.get('data',[]) if isinstance(row,dict) and isinstance(row.get('item_info'),dict)]}
    content = json.dumps({'official_url':DATA_URL,'official_page':DOUYIN_RANK_URL,
        'parameters':PARAMS,'note':'官方剧集实时榜响应字段摘录，仅保留剧名、ID、热度、排名、榜单时间；不是视频互动样本',
        'response':data},ensure_ascii=False,indent=2)
    filename = hashlib.sha256(content.encode()).hexdigest()+'.json'
    EVIDENCE.mkdir(exist_ok=True)
    path = EVIDENCE/filename
    if not path.exists():
        path.write_text(content,encoding='utf-8')
    return 'http://127.0.0.1:8000/api/evidence/'+filename


async def collect_douyin_api():
    """Read both dramas from one board snapshot; one failure affects no other source."""
    def failure(state,message):
        return {title:{'state':state,'message':message,'readings':[]} for title in DRAMAS}
    async with httpx.AsyncClient(timeout=20,follow_redirects=False,verify=ssl.create_default_context()) as client:
        for attempt in range(2):
            try:
                response = await client.get(ENDPOINT,params=PARAMS,headers={'Accept':'application/json'})
                if response.status_code in (401,403,429):
                    return failure('restricted',f'抖音剧集榜接口返回 HTTP {response.status_code}，保留上次榜单；稍后自动重试')
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError:
                    return failure('verification_required','抖音剧集榜接口未返回JSON，可能遇到访问校验；未更新数值')
                if not isinstance(payload,dict) or payload.get('status_code') != 0:
                    return failure('restricted','抖音剧集榜接口未返回成功状态，未更新数值')
                if not isinstance(payload.get('data'),list) or number(payload.get('active_time')) is None:
                    return failure('adapter_pending','抖音剧集榜响应结构发生变化，暂停更新以免误读')
                readings = {title:parse_payload(payload,title) for title in DRAMAS}
                evidence = save_evidence(payload) if any(readings.values()) else None
                result = {}
                for title,rows in readings.items():
                    for row in rows:
                        row['source_url']=evidence
                    present = any(isinstance(r,dict) and isinstance(r.get('item_info'),dict) and r['item_info'].get('nickname')==title
                                  for r in payload['data'])
                    result[title] = {'state':'ok' if rows else 'adapter_pending' if present else 'no_data',
                        'message':'已从官方剧集实时榜接口自动更新热度、排名；双剧使用同一榜单快照' if rows else
                                  '本剧榜单字段不完整或格式变化，未更新数值' if present else
                                  f'官方剧集实时榜本次返回{len(payload["data"])}条，未包含本剧；不推算排名或热度',
                        'readings':rows}
                return result
            except (httpx.TimeoutException,httpx.NetworkError):
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return failure('error','抖音剧集榜接口连接超时或网络异常，保留上次成功榜单')
            except httpx.HTTPStatusError:
                return failure('error','抖音剧集榜接口响应异常，保留上次成功榜单')
