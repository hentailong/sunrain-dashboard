"""Official mini-program requests learned from user-supplied network captures."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

BASE = Path(__file__).resolve().parent
CONFIG = BASE / 'local-secrets' / 'yunhe.json'
EVIDENCE = BASE / 'evidence'
ENTRY = 'https://www.enlightent.cn/program.html'
ORIGIN = 'https://www.enlightent.cn'
TITLE = '今天是太阳雨'
ENDPOINTS = {'/research/top/getReboTop.do':'rebo', '/research/top/getHeatTop.do':'heat'}
PUBLIC_PARAMS = {'channelType': 'tv', 'day': '1', 'date': ''}
TZ = timezone(timedelta(hours=8))


def import_capture(path: Path) -> str:
    """Store request credentials locally, never copy or log the captured response as live data."""
    text=path.read_text(encoding='utf-8-sig').replace('\r\n','\n')
    headers,rest=text.split('\n\n',1)
    first,*headerlines=headers.splitlines()
    method,target,*_=first.split()
    url=urlsplit(target)
    request_headers={k.strip().lower():v.strip() for line in headerlines if ':' in line for k,v in [line.split(':',1)]}
    if method!='POST' or request_headers.get('host')!='www.enlightent.cn' or url.path not in ENDPOINTS:
        raise ValueError('文件不是受支持的云合小程序榜单请求')
    body=re.split(r'(?:HTTP/\S+|h2)\s+\d{3}',rest,maxsplit=1)[0].strip()
    form={k:v[0] for k,v in parse_qs(body,keep_blank_values=True).items()}
    token=form.pop('accessToken',None)
    if not token:
        raise ValueError('抓包请求中缺少小程序会话')
    if form.get('channelType')!='tv' or form.get('day')!='1':
        raise ValueError('当前适配仅支持长剧日榜，未匹配请求不会自动套用')
    config=json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {'requests':{}}
    # An empty date asks the official endpoint for its latest published daily table.
    form['date']=''
    config['requests'][ENDPOINTS[url.path]]={
        'path':url.path,'form':form,'accessToken':token,
        'headers':{k:request_headers[k] for k in ('user-agent','referer') if k in request_headers},
    }
    config['updated_at']=datetime.now(TZ).isoformat()
    CONFIG.parent.mkdir(exist_ok=True)
    temporary=CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
    temporary.replace(CONFIG)
    return ENDPOINTS[url.path]


def connection_info():
    if not CONFIG.exists():
        return {'connected':False,'endpoints':[]}
    try:
        config=json.loads(CONFIG.read_text(encoding='utf-8'))
        expiries=[]
        for recipe in config['requests'].values():
            token=recipe.get('accessToken','')
            if token.count('.')==2:
                try:
                    part=token.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(part+'='*((-len(part))%4)))
                    if isinstance(claims.get('exp'),(int,float)):
                        expiries.append(datetime.fromtimestamp(claims['exp'],TZ).isoformat())
                except (ValueError,TypeError):
                    pass
        return {'connected':True,'endpoints':list(config['requests']), 'updated_at':config.get('updated_at'),
                'session_expires_at':min(expiries) if expiries else None}
    except (OSError,ValueError,KeyError):
        return {'connected':False,'endpoints':[]}


def number(value):
    if isinstance(value,bool) or value is None:
        return None
    try:
        result=float(value)
    except (TypeError,ValueError):
        return None
    return result if math.isfinite(result) else None


def valid_date(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 946684800000<=value<=4102444800000:
        return datetime.fromtimestamp(value/1000,TZ).date().isoformat()
    if not isinstance(value,str) or not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',value):
        return None
    try:
        return datetime.strptime(value,'%Y-%m-%d').date().isoformat()
    except ValueError:
        return None


def parse_payload(kind,payload,title_name=TITLE):
    if kind=='rebo':
        rows=payload if isinstance(payload,list) else []
        result=[]
        for row in rows:
            if row.get('name')!=title_name:
                continue
            date=valid_date(row.get('date'))
            if not date:
                continue
            for field,metric,unit in [('marketShare','market_share','%'),('reboRank','daily_rank','名')]:
                value=number(row.get(field))
                if value is None or (metric=='market_share' and not 0<=value<=100) or (metric=='daily_rank' and (value<1 or value!=int(value))):
                    continue
                result.append({'metric':metric,'value':value,'unit':unit,'source_time':date,
                    'metadata':{'scope':'云合工具箱 · 长剧热播日榜','frequency':'daily','field':field,'program_id':row.get('nameID')}})
        return result
    if kind=='heat':
        if not isinstance(payload,dict) or not valid_date(payload.get('date')):
            return []
        rows=payload.get('content',[])
        if not isinstance(rows,list):
            return []
        result=[]
        heat_values=[number(row.get('allHot')) for row in rows]
        ordered=all(value is not None for value in heat_values) and all(a>=b for a,b in zip(heat_values,heat_values[1:]))
        for index,row in enumerate(rows):
            if row.get('name')!=title_name:
                continue
            value=number(row.get('allHot'))
            if value is not None and value>=0:
                result.append({'metric':'yunhe_all_heat','value':value,'unit':'热度指数','source_time':valid_date(payload['date']),
                    'metadata':{'scope':'云合工具箱 · 全舆情热度日榜','frequency':'daily','field':'allHot','program_id':row.get('nameId')}})
                if ordered:
                    result.append({'metric':'yunhe_heat_rank','value':index+1,'unit':'名','source_time':valid_date(payload['date']),
                        'metadata':{'scope':'云合工具箱 · 全舆情热度日榜','frequency':'daily','field':'content排行榜序位（已验证热度降序）','program_id':row.get('nameId')}})
        return result
    return []


async def collect_yunhe_api(title_name=TITLE):
    try:
        config=json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {'requests':{kind:{'path':path} for path,kind in ENDPOINTS.items()}}
    except (OSError,ValueError):
        return {'state':'session_required','message':'本机云合会话配置不可读取，请重新连接小程序会话','readings':[]}
    readings=[];errors=[];expired=False;public_fallback_used=False
    # Use the OS trust store, including the user's existing corporate/capture CA.
    # Certificate and hostname verification remain enabled.
    async with httpx.AsyncClient(follow_redirects=False,timeout=20,verify=ssl.create_default_context()) as client:
        for kind,recipe in config.get('requests',{}).items():
            path=recipe.get('path')
            if path not in ENDPOINTS or ENDPOINTS[path]!=kind:
                continue
            try:
                used_public_fallback = False
                response=await client.post(ORIGIN+path,data={**recipe['form'],'date':'','accessToken':recipe['accessToken']},
                    headers={**recipe.get('headers',{}),'Accept':'application/json','xweb_xhr':'1'}) if recipe.get('accessToken') else None
                # The public website exposes the current daily tables through
                # GET. If the mini-program JWT expires (or the legacy POST
                # adapter is rejected with 5xx), retry without the token.
                if response is None or response.status_code in (401,403) or response.status_code >= 500:
                    used_public_fallback = True
                    public_fallback_used = True
                    public_headers = {k:v for k,v in recipe.get('headers',{}).items() if k.lower() in ('user-agent','referer')}
                    response = await client.get(ORIGIN+path,params=PUBLIC_PARAMS,
                        headers={**public_headers,'Accept':'application/json'})
                    if response.status_code in (401,403):
                        expired=True;errors.append(f'{kind}：会话失效，公开榜单接口也拒绝访问');continue
                response.raise_for_status()
                payload=response.json()
                current=parse_payload(kind,payload,title_name)
                if not current:
                    message=json.dumps(payload,ensure_ascii=False)[:300] if isinstance(payload,dict) else ''
                    if re.search(r'登录|令牌|token|失效|过期|未授权',message,re.I):
                        expired=True;errors.append(f'{kind}：小程序会话失效')
                    else:
                        errors.append(f'{kind}：未返回本剧有效日榜数据')
                    continue
                # Persist the actual fresh response; credentials are excluded from evidence.
                evidence={'source':'云合工具箱公开榜单' if used_public_fallback else '云合工具箱小程序','collected_at':datetime.now(TZ).isoformat(),
                    'request':{'method':'GET' if used_public_fallback else 'POST','url':ORIGIN+path,
                               'parameters':PUBLIC_PARAMS if used_public_fallback else recipe['form']},
                    'official_entry':ENTRY,'response':payload}
                content=json.dumps(evidence,ensure_ascii=False,indent=2).encode('utf-8')
                ident=hashlib.sha256(content).hexdigest();EVIDENCE.mkdir(exist_ok=True)
                (EVIDENCE/f'{ident}.json').write_bytes(content)
                for row in current:
                    row['source_url']=f'http://127.0.0.1:8000/api/evidence/{ident}.json'
                    row['metadata'].update({'method':'official_public_http' if used_public_fallback else 'official_api','official_entry':ENTRY,'endpoint':ORIGIN+path,
                                            'evidence_id':ident,'evidence_type':'官方接口原始响应'})
                readings.extend(current)
            except httpx.HTTPStatusError as exc:
                errors.append(f'{kind}：HTTP {exc.response.status_code}')
            except (httpx.HTTPError,ValueError,KeyError):
                errors.append(f'{kind}：网络或响应格式错误')
    if readings:
        dates='、'.join(sorted({r['source_time'] for r in readings}))
        detail='；部分接口未成功：'+'，'.join(errors) if errors else ''
        route='云合公开榜单接口' if public_fallback_used else '云合小程序接口'
        return {'state':'ok','message':f'已自动直连{route}，取得{len(readings)}项真实指标；统计日期{dates}{detail}', 'readings':readings,'page_url':ENTRY}
    return {'state':'session_expired' if expired else 'error','message':'；'.join(errors) or '云合接口配置为空', 'readings':[]}
