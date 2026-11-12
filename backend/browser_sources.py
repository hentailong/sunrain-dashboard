"""Read official pages through an ordinary local browser, preserving login sessions.

The collectors consume responses produced by normal page navigation and clicks.
They do not synthesize request signatures or treat protected font glyphs as numbers.
"""
from __future__ import annotations

import asyncio
import math
import sys
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Error as BrowserError
from backend.dramas import source_url, weibo_search, baidu_index, DOUYIN_RANK_URL
from backend.social_sources import (
    DOUBAN_URL, WEIBO_SEARCH, WEIBO_TOPIC, BAIDU_URL,
    parse_douban, parse_weibo, parse_baidu_charts, access_state,
)

TITLE = '今天是太阳雨'
PROFILES = Path(__file__).resolve().parent / 'browser-profiles'
PAGES = {
    'maoyan': 'https://piaofang.maoyan.com/dashboard/web-heat',
    'dengta': 'https://dengta.taopiaopiao.com/pro',
    'yunhe': 'https://www.enlightent.cn/program.html',
    'douban': DOUBAN_URL,
    'weibo': WEIBO_TOPIC,
    'douyin': DOUYIN_RANK_URL,
    'baidu_index': BAIDU_URL,
}
MOBILE_ONLY = {'dengta','yunhe'}
DOMAINS = {
    'maoyan':('maoyan.com',), 'dengta':('taopiaopiao.com','alipictures.com'),
    'yunhe':('enlightent.cn','enlightent.com'), 'douban':('douban.com',),
    'weibo':('weibo.cn','weibo.com'), 'douyin':('douyin.com','snssdk.com','zijieapi.com'),
    'baidu_index':('index.baidu.com',),
}
LABELS = {
    'heat': ('web_heat', '热度指数'),
    'currHeat': ('web_heat', '热度指数'),
    'hotValue': ('web_heat', '热度指数'),
    'effectivePlay': ('effective_play', '次'),
    'effectivePlayCount': ('effective_play', '次'),
    'marketShare': ('market_share', '%'),
    'rank': ('rank', '名'),
}


def numeric(value: Any) -> float | None:
    # Do not mistake text, booleans, private-use font glyphs or NaN for readings.
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.replace(',', ''))
        except ValueError:
            return None
    if isinstance(value, (float, int)) and math.isfinite(value):
        return float(value)
    return None


def matching_record(payload: Any, title_name: str = TITLE):
    """Only exact-title records; parent and child values cannot cross entities."""
    if isinstance(payload, dict):
        names = [payload.get(k) for k in ('name', 'title', 'seriesName', 'dramaName')]
        info = payload.get('seriesInfo') or payload.get('programInfo')
        if isinstance(info, dict):
            names.append(info.get('name'))
        if title_name in names:
            yield payload
        for value in payload.values():
            yield from matching_record(value,title_name)
    elif isinstance(payload, list):
        for value in payload:
            yield from matching_record(value,title_name)


def parse_packets(source: str, packets: list[dict], title_name: str = TITLE) -> list[dict]:
    readings: dict[str, dict] = {}
    for packet in packets:
        payload = packet['data']
        if source == 'maoyan':
            listing = payload.get('dataList', {}).get('list', []) if isinstance(payload, dict) else []
            for index, row in enumerate(listing):
                if row.get('seriesInfo', {}).get('name') == title_name:
                    readings['rank'] = {'metric': 'rank', 'value': index + 1, 'unit': '名', 'source_time': None,
                        'metadata': {'scope': '电视剧+网络剧公开榜单', 'series_id': row['seriesInfo'].get('seriesId')}}
            detail = payload.get('webHeatDetail', payload) if isinstance(payload, dict) else {}
            detail = detail.get('data', {}) if isinstance(detail, dict) else {}
            if detail.get('seriesInfo', {}).get('name') != title_name:
                continue
            # Public detail JSON exposes a numeric trend separately from font-encoded real-time heat.
            trends = detail.get('heatTrends', [])
            for trend in trends:
                value = numeric(trend.get('heat'))
                stamp = str(trend.get('date', ''))
                if value is None or len(stamp) != 8 or not stamp.isdigit():
                    continue
                source_time = f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}'
                readings[f'daily_heat:{source_time}'] = {'metric':'daily_heat', 'value':value, 'unit':'热度指数',
                    'source_time':source_time, 'metadata':{'scope':'猫眼详情页近日热度趋势', 'series_id':detail['seriesInfo'].get('seriesId'), 'frequency':'daily'}}
                if source_time == datetime.now(timezone(timedelta(hours=8))).date().isoformat():
                    readings['maoyan_heat_snapshot'] = {'metric':'maoyan_heat_snapshot','value':value,'unit':'热度指数',
                        'source_time':None,'metadata':{'scope':'猫眼当日趋势值 · 采集快照（非实时热度）',
                        'series_id':detail['seriesInfo'].get('seriesId'),'frequency':'snapshot',
                        'statistical_date':source_time,'field':'heatTrends.heat',
                        'meaning':'每15分钟记录官网当日趋势展示值；官网未更新时可重复，不代表每15分钟产生新热度'}}
        else:
            for record in matching_record(payload,title_name):
                for field, (metric, unit) in LABELS.items():
                    value = numeric(record.get(field))
                    if value is not None:
                        readings[metric] = {'metric':metric, 'value':value, 'unit':unit, 'source_time':None,
                            'metadata':{'field':field, 'scope':'官方页面中与剧名精确匹配的记录'}}
    return list(readings.values())


class BrowserWorker:
    def __init__(self):
        self.engine = None
        self.visible: dict[str, Any] = {}
        self.locks = {key: asyncio.Lock() for key in PAGES}

    async def start(self):
        self.engine = await async_playwright().start()

    async def close(self):
        for context in list(self.visible.values()):
            try:
                await context.close()
            except Exception:
                pass
        self.visible.clear()
        if self.engine:
            await self.engine.stop()
            self.engine = None

    async def context(self, source: str, visible: bool):
        if self.engine is None:
            await self.start()
        directory = PROFILES / source
        directory.mkdir(parents=True, exist_ok=True)
        return await self.engine.chromium.launch_persistent_context(
            user_data_dir=str(directory), headless=not visible,
            viewport={'width':1600, 'height':1000}, locale='zh-CN', timezone_id='Asia/Shanghai',
        )

    async def login(self, source: str, title_name: str = TITLE) -> dict:
        async with self.locks[source], asyncio.timeout(45):
            if source not in self.visible:
                context = await self.context(source, visible=True)
                self.visible[source] = context
                context.on('close', lambda: self.visible.pop(source, None))
            context = self.visible[source]
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto('https://www.douyin.com/' if source=='douyin' else source_url(source,title_name,PAGES[source]), wait_until='domcontentloaded', timeout=30000)
            if source=='douyin':
                await page.wait_for_timeout(2000)
                button=page.get_by_role('button',name='登录',exact=True)
                if await button.count() and await button.first.is_visible():
                    await button.first.click(timeout=5000)
            await page.bring_to_front()
            return {'ok':True, 'message':'已打开官方窗口。需要时请完成登录或访问验证；后台将在下一轮自动重试，也可点击“立即采集”。'}

    async def background_session(self, source: str, refresh: bool = False) -> dict:
        """Read a local browser session without creating a visible window/tab."""
        async with self.locks[source], asyncio.timeout(45):
            visible = self.visible.get(source)
            context = visible or await self.context(source, visible=False)
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                if refresh and not visible:
                    await page.goto(PAGES[source],wait_until='domcontentloaded',timeout=30000)
                    await page.wait_for_timeout(4500)
                return {'cookies': await context.cookies('https://m.weibo.cn/'),
                        'user_agent': await page.evaluate('navigator.userAgent')}
            finally:
                if not visible:
                    await asyncio.wait_for(context.close(),timeout=10)

    async def baidu_chart(self, title_name: str = TITLE) -> dict:
        """Use only the project profile; never attach to the user's browser."""
        from backend.baidu_api import CHART_SCRIPT
        async with self.locks['baidu_index'], asyncio.timeout(75):
            # Persist a user-completed login before returning to headless collection.
            visible=self.visible.get('baidu_index')
            if visible:
                await visible.close()
                self.visible.pop('baidu_index',None)
            context=await self.context('baidu_index',visible=False)
            try:
                page=await context.new_page()
                await page.goto(baidu_index(title_name),wait_until='domcontentloaded',timeout=30000)
                redirected=False;captured={'ready':False}
                for attempt in range(12):
                    try:
                        captured=await page.evaluate(CHART_SCRIPT)
                    except BrowserError as exc:
                        if 'Execution context was destroyed' not in str(exc):raise
                        await page.wait_for_timeout(1000)
                        continue
                    if captured.get('ready') and captured.get('dates'):
                        return captured
                    text=await page.locator('body').inner_text()
                    if '安全验证' in text or '验证码' in text:
                        return {'ready':False,'verificationRequired':True}
                    if captured.get('loginRequired'):
                        return captured
                    if '/v2/index.html' in page.url and not redirected and attempt>=3:
                        await page.goto(baidu_index(title_name),wait_until='domcontentloaded',timeout=30000)
                        redirected=True
                    if attempt<11:await page.wait_for_timeout(1000)
                return {'ready':False,'loginRequired':True} if '/v2/index.html' in page.url else captured
            finally:
                await asyncio.wait_for(context.close(),timeout=10)

    async def collect(self, source: str, title_name: str = TITLE) -> dict:
        if source == 'baidu_index':
            from backend.baidu_api import collect_baidu_api
            return await collect_baidu_api(title_name)
        if source == 'douyin':
            from backend.douyin_api import collect_douyin_api
            return (await collect_douyin_api())[title_name]
        async with self.locks[source], asyncio.timeout(75):
            visible = self.visible.get(source)
            background_browser = None
            if visible:
                # Login is the only foreground window. Collection reuses its
                # current session in a separate headless browser, never new tabs.
                state = await visible.storage_state()
                background_browser = await self.engine.chromium.launch(headless=True)
                context = await background_browser.new_context(storage_state=state,
                    viewport={'width':1600,'height':1000},locale='zh-CN',timezone_id='Asia/Shanghai')
            else:
                context = await self.context(source, visible=False)
            packets: list[dict] = []
            tasks: set = set()
            page = await context.new_page()
            async def record(response):
                from urllib.parse import urlsplit
                host = urlsplit(response.url).hostname or ''
                allowed = DOMAINS[source]
                if not any(host == domain or host.endswith('.'+domain) for domain in allowed):
                    return
                if response.request.resource_type not in ('xhr','fetch') or response.status != 200:
                    return
                try:
                    payload = await asyncio.wait_for(response.json(), timeout=5)
                    if isinstance(payload, (dict,list)):
                        packets.append({'url':response.url, 'data':payload})
                except Exception:
                    pass
            def on_response(response):
                task = asyncio.create_task(record(response))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            context.on('response', on_response)
            try:
                try:
                    await page.goto(source_url(source,title_name,PAGES[source]), wait_until='domcontentloaded', timeout=30000)
                except Exception:
                    # A loaded verification page may keep background requests pending.
                    if page.url == 'about:blank':
                        raise
                if source == 'maoyan':
                    await page.get_by_text(title_name, exact=True).first.wait_for(timeout=15000)
                    await page.get_by_text(title_name, exact=True).first.click()
                    await page.wait_for_timeout(2500)
                elif source == 'douban':
                    try:
                        await page.locator('h1 [property="v:itemreviewed"]').wait_for(timeout=15000)
                    except Exception:
                        pass
                else:
                    await page.wait_for_timeout(5000)
                if source == 'weibo':
                    # The topic header and verified account card are separate public pages.
                    await page.goto(weibo_search(title_name),wait_until='domcontentloaded',timeout=30000)
                    await page.wait_for_timeout(3500)
                if tasks:
                    await asyncio.wait_for(asyncio.gather(*list(tasks), return_exceptions=True), timeout=8)
                body = await page.locator('body').inner_text()
                html = await page.content()
                actual_url = page.url
                if source in MOBILE_ONLY:
                    label = '灯塔专业版 App' if source=='dengta' else '云合工具箱小程序'
                    if label.split()[0] not in body:
                        return {'state':'error','message':'免费产品入口页面未正常加载，稍后重试','readings':[]}
                    return {'state':'mobile_required','message':f'已核实{label}免费入口；当前网页是产品介绍，没有本剧榜单数值。App／小程序自动采集尚未完成，企业站登录不能替代', 'readings':[]}
                if source == 'douban':
                    readings = parse_douban(html,title_name)
                elif source == 'weibo':
                    readings = parse_weibo(packets,title_name)
                else:
                    readings = parse_packets(source, packets,title_name)
                if readings:
                    return {'state':'ok','message':f'已从官方页面自动采集 {len(readings)} 条指标（浏览器会话）', 'readings':readings, 'page_url':actual_url}
                state,message = access_state(source, actual_url, body, html, packets)
                return {'state':state,'message':message,'readings':[]}
            finally:
                context.remove_listener('response', on_response)
                if tasks:
                    for task in list(tasks):
                        task.cancel()
                    await asyncio.gather(*list(tasks), return_exceptions=True)
                await asyncio.wait_for(page.close(), timeout=10)
                try:
                    await asyncio.wait_for(context.close(), timeout=10)
                finally:
                    if background_browser:
                        await asyncio.wait_for(background_browser.close(),timeout=10)


class OfficialBrowsers:
    """Keep Playwright on a subprocess-capable loop even under Windows Uvicorn reload."""
    def __init__(self):
        self.worker = BrowserWorker()
        self.loop = None
        self.thread = None

    @property
    def visible(self):
        return self.worker.visible

    def _start_loop(self):
        ready = threading.Event()
        def run():
            self.loop = asyncio.ProactorEventLoop() if sys.platform == 'win32' else asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            ready.set()
            self.loop.run_forever()
            self.loop.close()
        self.thread = threading.Thread(target=run, daemon=True, name='official-browser')
        self.thread.start()
        ready.wait(5)

    async def _call(self, method, *args):
        if self.loop is None:
            self._start_loop()
        future = asyncio.run_coroutine_threadsafe(method(*args), self.loop)
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout=100)

    async def collect(self, source, title_name=TITLE):
        return await self._call(self.worker.collect, source,title_name)

    async def login(self, source, title_name=TITLE):
        return await self._call(self.worker.login, source,title_name)

    async def baidu_chart(self, title_name=TITLE):
        return await self._call(self.worker.baidu_chart,title_name)

    async def background_session(self, source, refresh=False):
        return await self._call(self.worker.background_session,source,refresh)

    async def close(self):
        if self.loop:
            await self._call(self.worker.close)
            self.loop.call_soon_threadsafe(self.loop.stop)
            if self.thread:
                await asyncio.to_thread(self.thread.join, 5)
            self.loop = None


browsers = OfficialBrowsers()
