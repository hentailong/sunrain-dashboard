"""Pair only readings with matching metric, unit and statistical period."""
from datetime import datetime

EXPECTED = {
    'mango': [('updated_episodes', '集'), ('page_displayed_metric', '页面显示值')],
    'weibo': [('topic_reads', '次'), ('topic_discussions', '次'), ('official_followers', '人'), ('official_posts', '条')],
    'douban': [('rating', '分'), ('rating_count', '人'), ('short_comments', '条'), ('reviews', '条'),
               ('watching', '人'), ('watched', '人'), ('wish', '人'), ('discussion_count', '条')],
    'douyin': [('douyin_drama_heat', '热度'), ('douyin_drama_rank', '名')],
    'maoyan': [('rank', '名'), ('maoyan_heat_snapshot','热度指数'), ('daily_heat', '热度指数')],
    'yunhe': [('market_share', '%'), ('daily_rank', '名'), ('yunhe_all_heat', '热度指数'), ('yunhe_heat_rank', '名')],
    'baidu_index': [('search_index', '指数')],
    'xiaohongshu': [],
    'dengta': [('dengta_play_count', '次'), ('dengta_play_share', '%'), ('dengta_play_rank', '名')],
}
RANKS = {'rank', 'daily_rank', 'yunhe_heat_rank', 'douyin_drama_rank', 'dengta_play_rank'}


def pair(left, right, metric, interval, current):
    result = {'comparable': False, 'delta': None, 'relative_percent': None,
              'lower_is_better': metric in RANKS}
    if ':' in metric or metric.startswith('video_'):
        return result | {'reason': '不同视频样本不直接比较数值差，需分别查看原视频'}
    if not left or not right or left['value'] is None or right['value'] is None:
        return result | {'reason': '一方或双方暂无有效数据'}
    if metric == 'page_displayed_metric':
        return result | {'reason': '页面展示值含义未确认，暂不计算差值'}
    if left['unit'] != right['unit']:
        return result | {'reason': '来源单位不同'}
    if (metric == 'maoyan_heat_snapshot' or metric.startswith('dengta_')) and left.get('metadata',{}).get('statistical_date') != right.get('metadata',{}).get('statistical_date'):
        return result | {'reason':'当日趋势快照的统计日期不同，暂不计算差值'}
    if left.get('source_time') or right.get('source_time'):
        if not left.get('source_time') or left['source_time'] != right.get('source_time'):
            return result | {'reason': '来源统计日期不同，暂不计算差值'}
    else:
        stamps = [datetime.fromisoformat(item['collected_at']) for item in (left, right)]
        tolerance = max(1800, interval * 120)
        if abs((stamps[0] - stamps[1]).total_seconds()) > tolerance:
            return result | {'reason': '两部剧采集时间间隔过大，等待同一轮更新'}
        if any((current - stamp).total_seconds() > tolerance for stamp in stamps):
            return result | {'reason': '实时指标已过期，等待自动更新后比较'}
    delta = left['value'] - right['value']
    return result | {'comparable': True, 'delta': delta,
                     'relative_percent': delta / abs(right['value']) * 100 if right['value'] and metric not in RANKS and left['unit'] != '%' else None,
                     'reason': '同统计日期' if left.get('source_time') else '同轮采集快照，具体时间见数值下方'}


def build_comparison(left_sources, right_sources, current):
    groups = []
    for left_source, right_source in zip(left_sources, right_sources):
        source = left_source['id']
        assert source == right_source['id']
        left = {m['metric']: m for m in left_source['metrics'] if m['metric'] != 'availability'}
        right = {m['metric']: m for m in right_source['metrics'] if m['metric'] != 'availability'}
        metrics = dict(EXPECTED[source])
        metrics.update({m['metric']: m['unit'] for m in [*left.values(), *right.values()]})
        rows = []
        for metric, unit in metrics.items():
            a, b = left.get(metric), right.get(metric)
            rows.append({'metric': metric, 'unit': unit, 'left': a, 'right': b,
                         **pair(a, b, metric, left_source.get('collection_interval_minutes') or 15, current)})
        groups.append({'source': source, 'name': left_source['name'], 'color': left_source['color'],
                       'left_status': {k: left_source.get(k) for k in ('state','message','last_success','url')},
                       'right_status': {k: right_source.get(k) for k in ('state','message','last_success','url')},
                       'rows': rows})
    return groups
