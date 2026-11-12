"""Read Weibo's official mobile endpoint in the backend using a cached local session."""
import asyncio
import json
from pathlib import Path
import ssl
from urllib.parse import parse_qs, urlsplit

import httpx

from backend.browser_sources import browsers
from backend.dramas import PRIMARY, weibo_topic, weibo_search
from backend.social_sources import parse_weibo

CONFIG = Path(__file__).resolve().parent / 'local-secrets' / 'weibo.json'
ENDPOINT = 'https://m.weibo.cn/api/container/getIndex'
session_lock = asyncio.Lock()


def read_session():
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
        return data if isinstance(data.get('cookies'),list) and data.get('user_agent') else None
    except (OSError, ValueError, AttributeError):
        return None


async def initialize_session(refresh=False):
    # Only initialization uses headless Chromium; it never opens a visible tab.
    session = await browsers.background_session('weibo',refresh=refresh)
    CONFIG.parent.mkdir(parents=True,exist_ok=True)
    temporary = CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps(session,ensure_ascii=False),encoding='utf-8')
    temporary.replace(CONFIG)
    return session


async def request_readings(title,session):
    packets=[];blocked=False;errors=[]
    jar=httpx.Cookies()
    for cookie in session['cookies']:
        jar.set(cookie['name'],cookie['value'],domain=cookie.get('domain','m.weibo.cn'),path=cookie.get('path','/'))
    async with httpx.AsyncClient(verify=ssl.create_default_context(),timeout=20,follow_redirects=False,
            cookies=jar,headers={'User-Agent':session['user_agent'],'Referer':'https://m.weibo.cn/',
            'X-Requested-With':'XMLHttpRequest','Accept':'application/json, text/plain, */*'}) as client:
        for page_url in (weibo_topic(title),weibo_search(title)):
            container=parse_qs(urlsplit(page_url).query)['containerid'][0]
            try:
                response=await client.get(ENDPOINT,params={'containerid':container})
                if response.status_code in (301,302,303,307,308,401,403,418,432):
                    blocked=True;continue
                response.raise_for_status()
                payload=response.json()
                if not isinstance(payload,dict):
                    errors.append('响应格式变化');continue
                if payload.get('ok')!=1:
                    blocked=True;continue
                packets.append({'url':str(response.url),'data':payload})
            except httpx.HTTPStatusError as exc:
                errors.append(f'HTTP {exc.response.status_code}')
            except (httpx.HTTPError,ValueError):
                errors.append('网络或响应格式异常')
    return parse_weibo(packets,title),blocked,errors


async def collect_weibo_api(title=PRIMARY):
    async with session_lock:
        try:
            session=read_session() or await initialize_session()
            readings,blocked,errors=await request_readings(title,session)
            if blocked:
                # Refresh at most once per collection, with no visible fallback.
                session=await initialize_session(refresh=True)
                newer,blocked,errors=await request_readings(title,session)
                readings=list({r['metric']:r for r in readings+newer}.values())
            for row in readings:
                row['metadata'].update({'method':'official_http','endpoint':ENDPOINT})
            if readings:
                suffix='；部分请求受限，上次其他指标已保留' if blocked or errors else ''
                return {'state':'ok','readings':readings,'page_url':weibo_topic(title),
                        'message':f'后台自动请求微博官方移动接口，取得{len(readings)}项真实指标，无可见标签{suffix}'}
            return {'state':'verification_required' if blocked else 'error','readings':[],
                    'message':'微博后台会话受限，已尝试无界面更新；上次成功数据已保留' if blocked else '微博后台请求未取得有效指标；'+('、'.join(errors) or '官网未提供数据')}
        except Exception as exc:
            # Never expose cookies, session URLs or response bodies to the UI/log.
            return {'state':'error','readings':[],'message':f'微博后台会话或请求失败（{type(exc).__name__}）；上次成功数据已保留'}
