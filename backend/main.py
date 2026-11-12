from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import ssl
import os
from contextlib import asynccontextmanager
from functools import partial
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from backend.browser_sources import browsers, PAGES, MOBILE_ONLY
from backend.yunhe_api import EVIDENCE, collect_yunhe_api, connection_info
from backend.forecasting import forecast_rows
from backend.dramas import DRAMAS, COMPARISON, MANGO_PAGES, source_url, DOUYIN_RANK_URL
from backend.comparison import build_comparison
from backend.weibo_api import collect_weibo_api
from backend.baidu_api import collect_baidu_api
from backend.douyin_api import collect_douyin_api
from backend.dengta_api import collect_dengta_api, PAGE as DENGTA_PAGE
from backend.dengta_daily import refresh_daily, daily_data
from backend.dengta_hourly import refresh_hourly, hourly_data
from backend.dengta_minutes import nearest_minute, normalize_history, minute_rows
from backend.mango_metrics import parse_play_count
from backend.kuyun_api import collect_kuyun_api, PAGE as KUYUN_PAGE, BROADCAST

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data.db"
TZ = timezone(timedelta(hours=8))
TITLE = "今天是太阳雨"
MANGO_URL = "https://www.mgtv.com/h/817372.html"
logger = logging.getLogger("sunrain")

SOURCES = {
    "mango": {"name": "芒果TV", "kind": "播出平台", "url": MANGO_URL, "color": "#f59e0b"},
    "weibo": {"name": "微博", "kind": "话题与官微", "url": PAGES['weibo'], "color": "#e6162d"},
    "douban": {"name": "豆瓣", "kind": "口碑平台", "url": "https://movie.douban.com/subject/36689621/", "color": "#2e963d"},
    "douyin": {"name": "抖音", "kind": "官方剧集榜", "url": DOUYIN_RANK_URL, "color": "#111827"},
    "baidu_index": {"name": "百度指数", "kind": "搜索指数", "url": PAGES['baidu_index'], "color": "#3059e8"},
    "maoyan": {"name": "猫眼", "kind": "行业榜单", "url": "https://piaofang.maoyan.com/dashboard/web-heat", "color": "#ffb400"},
    "dengta": {"name": "灯塔", "kind": "网播正片播放榜", "url": DENGTA_PAGE, "color": "#5b6cff"},
    "kuyun": {"name": "酷云", "kind": "电视直播收视", "url": KUYUN_PAGE, "color": "#6bbad2"},
    "yunhe": {"name": "云合数据", "kind": "微信免费小程序", "url": PAGES['yunhe'], "color": "#8358ff"},
}
SOURCE_INTERVALS = {key:15 for key in SOURCES}
SOURCE_INTERVALS['dengta'] = 1
SOURCE_INTERVALS['kuyun'] = 1
scheduler: AsyncIOScheduler | None = None


def validate_title(title):
    if title not in DRAMAS:
        raise HTTPException(404,'未知剧集')


def now() -> datetime:
    return datetime.now(TZ)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS observations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source TEXT NOT NULL,
          metric TEXT NOT NULL,
          value REAL,
          unit TEXT,
          collected_at TEXT NOT NULL,
          source_time TEXT,
          source_url TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          UNIQUE(source, metric, collected_at)
        );
        CREATE TABLE IF NOT EXISTS source_status (
          source TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          last_success TEXT,
          last_attempt TEXT,
          error TEXT,
          next_run TEXT,
          message TEXT
        );
        CREATE TABLE IF NOT EXISTS source_configs (
          source TEXT PRIMARY KEY,
          api_url TEXT,
          token TEXT,
          cookie TEXT,
          enabled INTEGER NOT NULL DEFAULT 1,
          updated_at TEXT NOT NULL
        );
        """
    )
    columns={row[1] for row in conn.execute('PRAGMA table_info(observations)')}
    if 'drama' not in columns:
        conn.execute("ALTER TABLE observations ADD COLUMN drama TEXT NOT NULL DEFAULT '今天是太阳雨'")
    conn.execute('CREATE INDEX IF NOT EXISTS ix_drama_series ON observations(drama,source,metric,collected_at)')
    conn.execute('CREATE TABLE IF NOT EXISTS collection_status (source TEXT NOT NULL, drama TEXT NOT NULL, state TEXT NOT NULL, last_success TEXT, last_attempt TEXT, error TEXT, next_run TEXT, message TEXT, PRIMARY KEY(source,drama))')
    conn.execute('INSERT OR IGNORE INTO collection_status(source,drama,state,last_success,last_attempt,error,next_run,message) SELECT source,?,state,last_success,last_attempt,error,next_run,message FROM source_status',(TITLE,))
    for title_name in DRAMAS:
        for key in SOURCES:
            conn.execute("INSERT OR IGNORE INTO collection_status(source,drama,state,message) VALUES(?,?,?,?)", (key,title_name,"pending","等待首次采集"))
    # Preserve the old brand series for audit, but never mix it with keyword search.
    for title_name in DRAMAS:
        archived=conn.execute("""UPDATE observations SET metric='baidu_brand_search_index_legacy'
            WHERE source='baidu_index' AND drama=? AND metric='search_index'
            AND (json_extract(metadata_json,'$.entity_id') IS NOT NULL
                 OR json_extract(metadata_json,'$.endpoint') LIKE '%queryBrandSearchIndex')""",(title_name,)).rowcount
        if archived:
            conn.execute("UPDATE collection_status SET state='pending',last_success=NULL,message='正在切换为官网关键词搜索指数，旧品牌口径已归档' WHERE source='baidu_index' AND drama=?",(title_name,))
    # Recover only snapshots actually observed during their statistical day.
    # A next-day correction is a revised daily reading, never an intraday point.
    for title_name in DRAMAS:
        if not conn.execute("SELECT 1 FROM observations WHERE source='maoyan' AND metric='maoyan_heat_snapshot' AND drama=? LIMIT 1",(title_name,)).fetchone():
            old = conn.execute("SELECT * FROM observations WHERE source='maoyan' AND metric='daily_heat' AND drama=? AND source_time=substr(collected_at,1,10)", (title_name,)).fetchall()
            for row in old:
                meta = json.loads(row['metadata_json'] or '{}') | {
                    'scope':'猫眼当日趋势值 · 采集快照（非实时热度）','frequency':'snapshot',
                    'statistical_date':row['source_time'],'recovered_from_observation':row['id'],
                    'meaning':'保留原始实际采集时间；旧版相同数值曾去重，缺失时段不补造'}
                conn.execute("INSERT OR IGNORE INTO observations(source,metric,value,unit,collected_at,source_time,source_url,metadata_json,drama) VALUES('maoyan','maoyan_heat_snapshot',?,?,?,NULL,?,?,?)",
                             (row['value'],row['unit'],row['collected_at'],row['source_url'],json.dumps(meta,ensure_ascii=False),title_name))
    normalize_history(conn)
    conn.commit(); conn.close()


def set_status(source: str, state: str, *, error: str | None = None, success: bool = False, message: str = "", drama: str = TITLE) -> None:
    timestamp = now().isoformat()
    conn = db()
    conn.execute(
        """UPDATE collection_status SET state=?, last_attempt=?, last_success=CASE WHEN ? THEN ? ELSE last_success END,
        error=?, next_run=?, message=? WHERE source=? AND drama=?""",
        (state, timestamp, int(success), timestamp, error, (now() + timedelta(minutes=SOURCE_INTERVALS[source])).isoformat(), message, source, drama),
    )
    conn.commit(); conn.close()


def save_observation(source: str, metric: str, value: float | None, unit: str, url: str, source_time: str | None = None, metadata: dict[str, Any] | None = None, drama: str = TITLE) -> None:
    conn = db()
    captured_at = now().isoformat()
    metadata = dict(metadata or {})
    if source == 'dengta':
        metadata.setdefault('sample_minute', nearest_minute(captured_at, metadata.get('statistical_date')))
    if source_time and source != 'dengta':
        previous = conn.execute('SELECT value FROM observations WHERE drama=? AND source=? AND metric=? AND source_time=? ORDER BY collected_at DESC LIMIT 1', (drama,source,metric,source_time)).fetchone()
        if previous and previous['value'] == value:
            conn.close()
            return
    conn.execute(
        "INSERT OR IGNORE INTO observations(source,metric,value,unit,collected_at,source_time,source_url,metadata_json,drama) VALUES(?,?,?,?,?,?,?,?,?)",
        (source, metric, value, unit, captured_at, source_time, url, json.dumps(metadata, ensure_ascii=False), drama),
    )
    conn.commit(); conn.close()


def parse_count(value: Any) -> float | None:
    if value is None: return None
    text = re.sub(r"<[^>]+>", "", str(value)).replace(",", "").strip().lower()
    match = re.search(r"([\d.]+)\s*([万亿kKmM]?)", text)
    if not match: return None
    number = float(match.group(1)); suffix = match.group(2)
    return number * {"万": 1e4, "亿": 1e8, "k": 1e3, "m": 1e6, "万": 1e4}.get(suffix, 1)


async def collect_mango(client: httpx.AsyncClient, drama: str = TITLE) -> None:
    status=partial(set_status,drama=drama);save=partial(save_observation,drama=drama)
    source = 'mango';url=MANGO_PAGES.get(drama)
    if not url:
        status(source,'no_data',message='未找到该剧芒果TV正片页面，不能与其他平台的播放口径混比')
        return
    status(source, "running", message="正在读取公开剧集页")
    try:
        response = await client.get(url, timeout=20)
        response.raise_for_status()
        text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        episode = re.search(r"共\s*(\d+)\s*集，更新至\s*(\d+)\s*集", text)
        if episode:
            save(source, "updated_episodes", float(episode.group(2)), "集", url, metadata={"total_episodes": int(episode.group(1))})
        play = parse_play_count(response.text, drama)
        if play:
            save(source, "mango_play_count", play['value'], "次", url,
                 metadata={key:value for key,value in play.items() if key!='value'})
        save(source, "availability", 1, "可访问", url, metadata={"episodes": episode.group(0) if episode else None})
        status(source, "ok", success=True, message="已读取剧集页公开信息")
    except Exception as exc:
        logger.exception("mango collection failed")
        status(source, "error", error=str(exc), message="公开页面读取失败")


async def collect_restricted(source: str, drama: str = TITLE) -> None:
    set_status(source, 'not_connected', drama=drama, message='尚未完成该平台自动适配，当前仅提供官方入口')


async def collect_official(source: str, drama: str = TITLE) -> None:
    status=partial(set_status,drama=drama)
    status(source, "running", message="正在后台请求官方接口" if source in ('weibo','yunhe','baidu_index') else "正在后台读取官方页面")
    try:
        result = await collect_yunhe_api(drama) if source=='yunhe' else await collect_weibo_api(drama) if source=='weibo' else await collect_baidu_api(drama) if source=='baidu_index' else await browsers.collect(source,drama)
        store_official_result(source,drama,result)
    except Exception as exc:
        # Never expose session URLs, credentials or browser internals to the UI.
        logger.warning('Official page collection failed: %s %s', source, type(exc).__name__)
        status(source, 'error', error=type(exc).__name__, message='官方页面采集失败，可点击重试；上次成功数据已保留')


def store_official_result(source, drama, result):
    for reading in result.get('readings', []):
        save_observation(source,reading['metric'],reading['value'],reading['unit'],
            reading.get('source_url',result.get('page_url',SOURCES[source]['url'])),reading.get('source_time'),
            {'automatic':True,**reading.get('metadata',{})},drama=drama)
    set_status(source,result['state'],success=result['state']=='ok',message=result['message'],drama=drama)


collection_lock = asyncio.Lock()
source_locks = {key:asyncio.Lock() for key in SOURCES}
browser_limit = asyncio.Semaphore(1)


async def collect_one(source: str) -> bool:
    if source not in SOURCES:
        return False
    if source_locks[source].locked():
        return False
    async with source_locks[source]:
        if source == 'kuyun':
            result = await collect_kuyun_api()
            store_official_result(source,TITLE,result)
            return True
        if source in ('douyin', 'dengta'):
            for drama in DRAMAS:
                set_status(source,'running',message='正在后台请求官方剧集实时榜',drama=drama)
            try:
                results = await (collect_dengta_api() if source == 'dengta' else collect_douyin_api())
                for drama in DRAMAS:
                    store_official_result(source,drama,results[drama])
            except Exception as exc:
                for drama in DRAMAS:
                    set_status(source,'error',error=type(exc).__name__,
                               message=f'{SOURCES[source]["name"]}剧集榜采集失败，保留上次成功数据；稍后自动重试',drama=drama)
            if source == 'dengta':
                await refresh_hourly(DB_PATH)
                await refresh_daily(DB_PATH)
            return True
        for drama in DRAMAS:
            if source == 'mango':
                async with httpx.AsyncClient(follow_redirects=True,verify=ssl.create_default_context()) as client:
                    await collect_mango(client,drama)
            elif source in ('yunhe','weibo','baidu_index'):
                await collect_official(source,drama)
            elif source in PAGES:
                async with browser_limit:
                    await collect_official(source,drama)
            else:
                await collect_restricted(source,drama)
    return True

async def collect_all(*, scheduled_startup: bool = False) -> None:
    if collection_lock.locked():
        return
    async with collection_lock:
        await asyncio.gather(*(collect_one(source) for source in ('mango','yunhe','weibo','douyin','dengta','kuyun') if not (scheduled_startup and source == 'dengta')))
        for source in PAGES:
            if source not in ('yunhe','weibo','douyin','dengta'):
                await collect_one(source)
        for source in SOURCES:
            if source not in PAGES and source not in ('mango','kuyun','douyin','dengta'):
                await collect_one(source)


def get_latest(source: str | None = None, drama: str = TITLE) -> list[dict[str, Any]]:
    conn=db()
    where='WHERE drama=?';params=[drama]
    if source:
        where+=' AND source=?';params.append(source)
    rows=conn.execute(f"SELECT o.* FROM observations o JOIN (SELECT source,metric,MAX(collected_at) latest FROM observations {where} GROUP BY source,metric) x ON o.source=x.source AND o.metric=x.metric AND o.collected_at=x.latest WHERE o.drama=? ORDER BY o.source,o.metric",[*params,drama]).fetchall()
    if source in (None,'kuyun'):
        rows=[r for r in rows if r['source']!='kuyun']
        rows.extend(conn.execute("""SELECT * FROM observations WHERE id IN (
            SELECT id FROM (SELECT id,ROW_NUMBER() OVER (
                PARTITION BY metric ORDER BY source_time DESC,collected_at DESC,id DESC) AS revision
                FROM observations WHERE source='kuyun' AND metric!='kuyun_history_rating' AND drama=?) WHERE revision=1)""",(drama,)).fetchall())
    if source in (None,'yunhe'):
        # Backfilling an older daily value must not replace the latest day's card.
        rows=[r for r in rows if r['source']!='yunhe']
        rows.extend(conn.execute("""SELECT * FROM observations WHERE id IN (
            SELECT id FROM (SELECT id,ROW_NUMBER() OVER (
                PARTITION BY metric ORDER BY source_time DESC,collected_at DESC,id DESC) AS revision
                FROM observations WHERE source='yunhe' AND drama=?) WHERE revision=1)""",(drama,)).fetchall())
    if source in (None,'maoyan'):
        # The daily card and comparison must use the same finished-day scope
        # as the daily chart, while the snapshot card carries today's value.
        rows=[r for r in rows if not (r['source']=='maoyan' and r['metric']=='daily_heat')]
        daily=conn.execute("SELECT * FROM observations WHERE source='maoyan' AND metric='daily_heat' AND drama=? AND source_time<? ORDER BY source_time DESC,collected_at DESC,id DESC LIMIT 1",(drama,now().date().isoformat())).fetchone()
        if daily:
            rows.append(daily)
    conn.close()
    rows=[row for row in rows if row['source']!='baidu_index' or row['metric']=='search_index']
    return [dict(row) | {'metadata':json.loads(row['metadata_json'] or '{}')} for row in rows
            if row['source'] != 'douyin' or row['metric'] in ('douyin_drama_heat','douyin_drama_rank')]


def calculate_forecast(source: str, metric: str, hours: int, drama: str = TITLE) -> dict[str, Any]:
    if source == 'kuyun':
        return {'available':False,'metric':metric,'reason':'直播收视按节目播出时段记录，停播期间不补值，暂不跨时段预测。'}
    if source == 'dengta':
        return {'available':False,'metric':metric,'reason':'灯塔当前指标按日重新统计，保留日内实时走势；暂不跨日预测。'}
    if source == 'maoyan' and metric == 'maoyan_heat_snapshot':
        return {'available':False,'metric':metric,'reason':'这是当日趋势值的采集快照，跨日统计重新开始，不能作为连续实时热度预测；可查看已结束日期的日趋势。'}
    if source == 'douyin' and metric not in ('douyin_drama_heat','douyin_drama_rank'):
        return {'available':False, 'metric':metric, 'reason':'抖音仅统计官方剧集榜热度和排名，旧视频互动样本已归档。'}
    if metric in ('availability','rank','daily_rank','yunhe_heat_rank','douyin_drama_rank'):
        return {'available':False, 'metric':metric, 'reason':'排名与可访问状态不作为连续数值指标预测。'}
    conn=db()
    rows=conn.execute('SELECT collected_at,source_time,value FROM observations WHERE source=? AND metric=? AND drama=? ORDER BY COALESCE(source_time,collected_at),collected_at',(source,metric,drama)).fetchall()
    conn.close()
    rows = [dict(row) for row in rows]
    if source == 'maoyan' and metric == 'daily_heat':
        rows = maoyan_daily_points(rows,now())
    return {'metric':metric, **forecast_rows(rows,hours,now())}


def maoyan_daily_points(rows, current):
    """Latest known revision per finished statistical day, retaining raw history."""
    latest = {}
    today = current.date().isoformat()
    for row in rows:
        date = row.get('source_time')
        if not date or date >= today:
            continue
        previous = latest.get(date)
        if previous is None or row['collected_at'] >= previous['collected_at']:
            latest[date] = row
    return [latest[date] for date in sorted(latest)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    init_db(); scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    for source in SOURCES:
        if source in PAGES or source in ('mango','kuyun','dengta'):
            trigger = {'trigger': 'cron', 'minute': '*', 'second': 0} if source == 'dengta' else {'trigger': 'interval', 'minutes': SOURCE_INTERVALS[source]}
            scheduler.add_job(collect_one,**trigger,args=[source],
                              id=f'collect:{source}',replace_existing=True,coalesce=True,max_instances=1,misfire_grace_time=60)
    scheduler.start()
    initial = asyncio.create_task(collect_all(scheduled_startup=True))
    yield
    scheduler.shutdown(wait=False)
    scheduler = None
    initial.cancel()
    try:
        await initial
    except asyncio.CancelledError:
        pass
    await browsers.close()


app = FastAPI(title="今天是太阳雨 · 数据统计平台", lifespan=lifespan)
_cors_origins = [item.strip() for item in os.getenv('CORS_ORIGINS', '').split(',') if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", *_cors_origins], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/overview")
def overview(title: str = TITLE):
    validate_title(title)
    return {"title":title, "dramas":DRAMAS, "updated_at":now().isoformat(), "sources":sources(title)}


@app.get("/api/sources")
def sources(title: str = TITLE):
    validate_title(title)
    conn = db(); status = {row["source"]: dict(row) for row in conn.execute("SELECT * FROM collection_status WHERE drama=?",(title,))}; conn.close()
    latest = get_latest(drama=title)
    return [{"id": key, **meta, **status.get(key, {}), "url":source_url(key,title,meta["url"]), "metrics": [m for m in latest if m['source']==key],
             "automatic": key in ('yunhe','dengta','kuyun') or (key not in MOBILE_ONLY and (key in PAGES or key == 'mango')),
             "verified": bool(status.get(key,{}).get('last_success')) and (key!='douyin' or any(m['source']=='douyin' for m in latest)),
             "login_url": PAGES.get(key) if key not in MOBILE_ONLY else None,
             "method": 'official_browser' if key=='baidu_index' else 'official_http' if key=='weibo' else 'official_api' if key in ('yunhe','douyin','dengta','kuyun') else 'mobile_product' if key in MOBILE_ONLY else 'official_browser' if key in PAGES else 'public_http',
             "broadcast": BROADCAST if key=='kuyun' else None,
             "connection": connection_info() if key=='yunhe' else None,
             "collection_interval_minutes": SOURCE_INTERVALS[key] if key in PAGES or key in ('mango','kuyun') else None,
             "next_run": (scheduler.get_job(f'collect:{key}').next_run_time.isoformat() if scheduler and scheduler.get_job(f'collect:{key}') else None),
             "login_open": key in browsers.visible,
             "entry_label": {'dengta':'灯塔官方网播榜','yunhe':'云合工具箱小程序官网','weibo':'查看话题原页','douyin':'剧集榜（官方搜索卡片）'}.get(key,'查看官方来源')}
            for key, meta in SOURCES.items()]


@app.get('/api/dengta/daily')
def dengta_daily():
    return daily_data(DB_PATH)


@app.get('/api/dengta/hourly')
def dengta_hourly():
    return hourly_data(DB_PATH)


@app.get("/api/series")
def series(source: str, metric: str | None = None, hours: int = Query(168, ge=1, le=720), title: str = TITLE, all_history: bool = False):
    validate_title(title)
    if source not in SOURCES:
        raise HTTPException(404, '未知数据源')
    if source == 'douyin' and metric and metric not in ('douyin_drama_heat','douyin_drama_rank'):
        return []
    conn = db(); params: list[Any] = [source, title]
    query = "SELECT * FROM observations WHERE source=? AND drama=?"
    if not (all_history and source in ('yunhe','maoyan','dengta','kuyun','douyin','weibo','baidu_index')):
        query += " AND collected_at>=?" if source == 'dengta' else " AND COALESCE(source_time,collected_at)>=?"
        params.append((now() - timedelta(hours=hours)).isoformat())
    if metric: query += " AND metric=?"; params.append(metric)
    if source == 'douyin':
        query += " AND metric IN ('douyin_drama_heat','douyin_drama_rank')"
    if source == 'baidu_index':
        query += " AND metric='search_index'"
    query += " ORDER BY COALESCE(source_time,collected_at),collected_at"
    rows = conn.execute(query, params).fetchall(); conn.close()
    rows = [dict(row) for row in rows]
    if source == 'dengta':
        rows = minute_rows(rows)
    if source == 'maoyan':
        rows = [r for r in rows if r['metric']!='daily_heat'] + maoyan_daily_points([r for r in rows if r['metric']=='daily_heat'],now())
        rows.sort(key=lambda r:(r['source_time'] or r['collected_at'],r['collected_at']))
    return [{"id": row["id"], "metric": row["metric"], "value": row["value"], "unit": row["unit"], "time": row.get('chart_time') or row["source_time"] or row["collected_at"], "collected_at":row['collected_at'], "source_time": row["source_time"], "url": row["source_url"], "metadata": json.loads(row["metadata_json"] or "{}")} for row in rows]


@app.get('/api/compare')
def compare():
    return {'left_title': TITLE, 'right_title': COMPARISON, 'updated_at': now().isoformat(),
            'groups': build_comparison(sources(TITLE), sources(COMPARISON), now())}


@app.get("/api/forecast")
def forecast(source: str, metric: str, hours: int = Query(24, ge=1, le=168), title: str = TITLE):
    validate_title(title)
    if source not in SOURCES: raise HTTPException(404, "未知数据源")
    return calculate_forecast(source, metric, hours,title)


@app.post("/api/refresh")
async def refresh():
    await collect_all(); return {"ok": True, "updated_at": now().isoformat()}


@app.post("/api/import")
def import_rows(payload: Any = Body(...)):
    """Import manually exported rows from a licensed/source-authorized account.

    Accepted body: {source: "maoyan", rows: [{metric,value,unit,source_time,source_url}]}.
    This deliberately does not accept credentials; it only stores user-provided exports.
    """
    if not isinstance(payload, dict):
        raise HTTPException(400, "请求体必须是对象")
    source = str(payload.get("source", ""))
    if source not in SOURCES:
        raise HTTPException(400, "未知数据源")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "rows 不能为空")
    imported = 0
    for row in rows:
        if not isinstance(row, dict) or not row.get("metric"):
            continue
        raw_value = row.get("value")
        try:
            value = float(raw_value) if raw_value not in (None, "") else None
        except (TypeError, ValueError):
            value = parse_count(raw_value)
        save_observation(source, str(row["metric"]), value, str(row.get("unit") or ""), str(row.get("source_url") or SOURCES[source]["url"]), str(row.get("source_time") or "") or None, {"manual": True, "imported_at": now().isoformat()})
        imported += 1
    if not imported:
        raise HTTPException(400, "没有可导入的有效记录")
    set_status(source, "ok", success=True, message=f"已手动导入 {imported} 条记录")
    return {"ok": True, "source": source, "imported": imported, "updated_at": now().isoformat()}


@app.post('/api/sources/{source}/login')
async def open_source_login(source: str, title: str = TITLE):
    validate_title(title)
    if source not in PAGES or source in MOBILE_ONLY:
        raise HTTPException(400, '该来源没有内置浏览器连接')
    try:
        result = await browsers.login(source,title)
        return result
    except Exception as exc:
        raise HTTPException(503, f'无法打开本机浏览器（{type(exc).__name__}），请检查浏览器运行依赖')


@app.post('/api/sources/{source}/refresh')
async def refresh_source(source: str, title: str = TITLE):
    validate_title(title)
    if source not in PAGES and source not in ('mango','kuyun','douyin','dengta'):
        raise HTTPException(400, '该来源尚未实现自动采集')
    await collect_one(source)
    return next(item for item in sources(title) if item['id']==source)


@app.get("/api/health")
def health(): return {"ok": True, "time": now().isoformat(), "database": str(DB_PATH)}


@app.get('/api/evidence/{filename}')
def evidence(filename: str):
    if not re.fullmatch(r'[0-9a-f]{64}\.(png|json)',filename):
        raise HTTPException(404,'快照不存在')
    path=EVIDENCE/filename
    if not path.is_file():
        raise HTTPException(404,'快照不存在')
    return FileResponse(path,media_type='application/json' if filename.endswith('.json') else 'image/png',headers={'Cache-Control':'private, max-age=86400','X-Content-Type-Options':'nosniff'})
