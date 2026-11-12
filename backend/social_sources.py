"""Platform-specific public readings; missing values are never converted to zero."""
from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urljoin
from datetime import datetime

from bs4 import BeautifulSoup
from backend.dramas import DOUBAN_SUBJECTS, WEIBO_TOPICS, weibo_topic

TITLE = '今天是太阳雨'
DOUBAN_URL = 'https://movie.douban.com/subject/36689621/'
WEIBO_SEARCH = 'https://m.weibo.cn/search?containerid=100103type%3D1%26q%3D' + TITLE
WEIBO_TOPIC = 'https://m.weibo.cn/search?containerid=231522type%3D1%26t%3D10%26q%3D%23' + TITLE + '%23'
BAIDU_URL = 'https://index.baidu.com/v2/main/index.html#/trend/' + TITLE + '?words=' + TITLE


def count(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*([万亿]?)\s*', str(value).replace(',', ''))
    if not match:
        return None
    result = float(match[1]) * {'': 1, '万': 10000, '亿': 100000000}[match[2]]
    return result if math.isfinite(result) else None


def reading(metric, value, unit, url, **metadata):
    return {'metric': metric, 'value': value, 'unit': unit, 'source_url': url,
            'source_time': None, 'metadata': metadata}


def parse_douban(html: str, title_name: str = TITLE) -> list[dict]:
    subject_url = DOUBAN_SUBJECTS[title_name]
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.select_one('h1 [property="v:itemreviewed"]')
    if not title or title.get_text(strip=True) != title_name:
        return []
    result = []
    rating = soup.select_one('#interest_sectl [property="v:average"]')
    value = count(rating.get_text(strip=True)) if rating else None
    if value is not None and 0 <= value <= 10:
        result.append(reading('rating', value, '分', subject_url, scope='豆瓣公开评分'))
    else:
        result.append(reading('rating', None, '分', subject_url, missing_reason='官网暂无评分'))
    for metric, selector in [('rating_count','#interest_sectl [property="v:votes"]'),
                             ('short_comments','#comments-section h2 a'),
                             ('reviews','.reviews.mod > header h2 a')]:
        node = soup.select_one(selector)
        if not node and metric == 'reviews':
            node = soup.select_one('.reviews.mod h2 .pl a')
        match = re.search(r'[\d,]+', node.get_text()) if node else None
        if match:
            result.append(reading(metric, count(match[0]), '人' if metric=='rating_count' else '条',
                                  urljoin(subject_url, node.get('href','')), scope='豆瓣公开剧集页'))
    # Only parse the subject's interests block, not recommendation titles or comments.
    interests = soup.select_one('#subject-others-interests')
    if interests:
        text = interests.get_text(' ', strip=True)
        for label, metric in [('在看','watching'),('看过','watched'),('想看','wish')]:
            match = re.search(r'([\d,]+)\s*人' + label, text)
            if match:
                result.append(reading(metric, count(match[1]), '人', subject_url, scope='豆瓣公开标记人数'))
    discussion = soup.select_one('a[href*="discussion/"]')
    if discussion:
        match = re.search(r'全部\s*([\d,]+)\s*条', discussion.get_text())
        if match:
            result.append(reading('discussion_count', count(match[1]), '条', urljoin(subject_url,discussion['href']), scope='豆瓣小组讨论条数'))
    return result


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def parse_weibo(packets: list[dict], title_name: str = TITLE) -> list[dict]:
    result = {}
    for packet in packets:
        if '/api/container/getIndex' not in packet.get('url',''):
            continue
        payload = packet.get('data',{})
        if payload.get('ok') != 1:
            continue
        data = payload.get('data',{})
        headers = data.get('cardlistInfo',{}).get('cardlist_head_cards',[])
        for header in walk(headers):
            head = header.get('head_data') or {}
            if not isinstance(head, dict):
                continue
            if head.get('title') != f'#{WEIBO_TOPICS.get(title_name,title_name)}#':
                continue
            for label, metric in [('阅读量','topic_reads'),('讨论量','topic_discussions')]:
                match = re.search(label + r'\s*(\d+(?:\.\d+)?[万亿]?)', head.get('midtext',''))
                if match and (value := count(match[1])) is not None:
                    result[metric] = reading(metric,value,'次',weibo_topic(title_name),scope=f'#{WEIBO_TOPICS.get(title_name,title_name)}# 主话题累计值',raw=match[1],precision='官网展示值，可能四舍五入')
        for node in walk(data.get('cards',[])):
            user = node.get('user',{})
            if not isinstance(user,dict) or user.get('screen_name') != title_name+'官微' or user.get('verified_reason') != f'《{title_name}》官方微博':
                continue
            url = f"https://m.weibo.cn/u/{user['id']}"
            for field, metric, unit in [('followers_count','official_followers','人'),('statuses_count','official_posts','条')]:
                value = count(user.get(field))
                if value is not None:
                    result[metric] = reading(metric,value,unit,url,scope='本剧认证官方微博',raw=user[field],precision='官网展示值')
    return list(result.values())


def parse_baidu_charts(charts: list[dict], url: str, title_name: str = TITLE) -> list[dict]:
    """Read numeric points already rendered by the official chart, without decoding API ciphertext."""
    result={}
    for chart in charts:
        for series in chart.get('series',[]):
            if series.get('name') != title_name:
                continue
            dates=chart.get('dates',[])
            for stamp,value in zip(dates,series.get('data',[])):
                if not isinstance(stamp,str) or not re.fullmatch(r'20\d{2}[-/.]\d{2}[-/.]\d{2}',stamp):
                    continue
                try:
                    date=datetime.strptime(re.sub(r'[/\.]','-',stamp),'%Y-%m-%d').date().isoformat()
                except ValueError:
                    continue
                if isinstance(value,dict):
                    value=value.get('value')
                number=count(value)
                if number is None:
                    continue
                row=reading('search_index',number,'指数',url,scope='百度指数官网趋势图',method='official_rendered_chart',frequency='daily')
                row['source_time']=date;result[date]=row
    return list(result.values())


def access_state(source: str, url: str, text: str, html: str, packets: list[dict]) -> tuple[str,str]:
    """Identify actual blockers, rather than classifying every failure as login."""
    if source == 'douyin' and ('验证码' in text or '安全验证' in text or 'captcha' in html.lower()):
        return 'verification_required', '抖音返回访问验证；请打开官方验证窗口处理，完成后后台下一轮自动重试'
    if source == 'baidu_index':
        for packet in packets:
            if '/Interface/api/pcPass' in packet.get('url',''):
                login = packet.get('data',{}).get('data',{}).get('result',{}).get('isLogin')
                if login == 0:
                    return 'login_required', '百度指数查询要求登录百度账号；可打开官方窗口登录，会话在本机保存'
        if '扫码登录' in text or '手机号/用户名/邮箱' in html:
            return 'login_required', '百度指数查询要求登录百度账号；可打开官方窗口登录'
        if '未收录' in text or '未被收录' in text:
            return 'no_data', '官网显示关键词未收录；没有可采集的百度指数'
        return 'adapter_pending', '百度页面已打开；登录后的指数读取尚未验证，不将搜索结果数当作百度指数'
    if '/login' in url or '/signin' in url or '扫描二维码登录' in text:
        return 'login_required', '官方页面要求登录；登录会话保存在本机，后台定时复用'
    if '安全验证' in text or '异常请求' in text or 'sec.douban.com' in url:
        return 'verification_required', '官网要求访问验证；可打开官方验证窗口处理后重试'
    return 'no_data', '已访问官方页面，但没有读到可确认的本剧指标；保留上次成功值'
