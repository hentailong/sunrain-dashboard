"""Validate the play counter on the drama's own Mango detail header."""
import math
import re
from bs4 import BeautifulSoup


def parse_play_count(html, title):
    soup=BeautifulSoup(html,'html.parser')
    headings=[h for h in soup.select('h1.title') if h.get_text(strip=True)==title]
    if len(headings)!=1:
        return None
    content=headings[0].find_parent(class_='content')
    if content is None:
        return None
    icons=content.select('.tags .tag .hitv-play')
    if len(icons)!=1:
        return None
    raw=icons[0].find_parent(class_='tag').get_text(strip=True)
    match=re.fullmatch(r'([\d,]+(?:\.\d+)?)\s*([万亿]?)',raw)
    if not match:
        return None
    # Confirm the displayed counter against the structured playCnt field.
    fields=re.findall(r'\bplayCnt\s*:\s*"([^"\n]+)"',html)
    if raw not in fields:
        return None
    value=float(match[1].replace(',',''))*{'':1,'万':1e4,'亿':1e8}[match[2]]
    if not math.isfinite(value) or value<0:
        return None
    return {'value':value,'raw':raw,'scope':'芒果TV剧集页累计播放展示值',
            'precision':'官网取整展示值，非精确到次的播放计数','field':'detail.playCnt'}
