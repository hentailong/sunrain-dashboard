"""Read the official keyword search chart in a dedicated headless project browser."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from urllib.parse import unquote, urlsplit

from backend.dramas import PRIMARY, baidu_index
from backend.yunhe_api import EVIDENCE

TZ=timezone(timedelta(hours=8))
SCOPE='百度关键词搜索指数 · 全国 · PC+移动'
# trendChart is search; trendChart2 is news, and the thumbnail charts are separate.
CHART_SCRIPT=r"""(() => {
 const v=document.querySelector('.index-trend-view')?.__vue__;
 if(!v)return {url:location.href,ready:false,loginRequired:/扫码登录|手机号\/用户名\/邮箱/.test(document.body.innerText)};
 const o=v.trendChart?.getOption();
 return {url:location.href,ready:!v.chartLoading&&!!o,title:v.wordKey,area:v.area,device:v.deviceSelect,
   dates:o?.xAxis?.[0]?.data,series:o?.series?.map(s=>({name:s.name,data:s.data}))};
})()"""


def parse_payload(payload,title=PRIMARY,current=None):
    current=current or datetime.now(TZ)
    if not isinstance(payload,dict) or not payload.get('ready'):
        raise ValueError('Chart not ready')
    url=urlsplit(payload.get('url',''))
    if url.scheme!='https' or url.hostname!='index.baidu.com' or unquote(url.fragment.split('?')[0])!='/trend/'+title:
        raise ValueError('Not the requested keyword trend page')
    if payload.get('title')!=title or str(payload.get('area'))!='0' or payload.get('device')!='all':
        raise ValueError('Keyword, region or device mismatch')
    dates=payload.get('dates');series=payload.get('series')
    if not isinstance(dates,list) or not isinstance(series,list):raise ValueError('Invalid chart')
    matches=[s for s in series if isinstance(s,dict) and s.get('name')==title]
    if len(matches)!=1 or not isinstance(matches[0].get('data'),list) or len(matches[0]['data'])!=len(dates):
        raise ValueError('Ambiguous or incomplete series')
    rows=[];seen=set()
    for raw_day,raw in zip(dates,matches[0]['data']):
        day=datetime.strptime(str(raw_day),'%Y-%m-%d').date()
        if day>=current.date() or day in seen:raise ValueError('Invalid or duplicate date')
        seen.add(day)
        if raw is None or raw=='-':continue
        if isinstance(raw,dict):raw=raw.get('value')
        if isinstance(raw,bool):raise ValueError('Invalid index')
        value=float(raw)
        if not math.isfinite(value) or value<0 or int(value)!=value:raise ValueError('Invalid index')
        rows.append({'metric':'search_index','value':int(value),'unit':'指数','source_time':day.isoformat(),'source_url':baidu_index(title),
                     'metadata':{'scope':SCOPE,'method':'official_rendered_chart','frequency':'daily','statistical_date':day.isoformat(),
                                 'keyword':title,'region_id':0,'device_source':'all','chart':'trendChart','series_kind':'keyword_search',
                                 'official_url':baidu_index(title)}})
    return sorted(rows,key=lambda r:r['source_time'])


async def collect_baidu_api(title=PRIMARY):
    from backend.browser_sources import browsers
    try:
        captured=await browsers.baidu_chart(title)
        if captured.get('verificationRequired'):
            return {'state':'verification_required','message':'百度要求访问验证，请在本项目独立采集窗口完成验证；不使用日常 Chrome','readings':[]}
        if captured.get('loginRequired'):
            return {'state':'login_required','message':'百度独立采集环境需要登录一次；请打开项目的官方登录窗口，完成后后台自动复用，不使用日常 Chrome','readings':[]}
        rows=parse_payload(captured,title)
        if not rows:return {'state':'no_data','message':'百度关键词搜索图暂未返回有效数据，保留此前历史','readings':[]}
        content=json.dumps({'source':baidu_index(title),'captured_at':datetime.now(TZ).isoformat(),'chart':captured},ensure_ascii=False,indent=2)
        name=hashlib.sha256(content.encode()).hexdigest()+'.json';EVIDENCE.mkdir(exist_ok=True)
        (EVIDENCE/name).write_text(content,encoding='utf-8')
        for row in rows:row['source_url']='http://127.0.0.1:8000/api/evidence/'+name
        return {'state':'ok','message':f"独立后台已采集关键词搜索指数 {len(rows)} 天，最新统计 {rows[-1]['source_time']}；全国 PC+移动，每15分钟检查",
                'readings':rows,'page_url':baidu_index(title)}
    except Exception:
        return {'state':'error','message':'百度独立后台采集失败，保留此前正确口径数据；不会调用日常 Chrome 或回退到其他指数','readings':[]}
