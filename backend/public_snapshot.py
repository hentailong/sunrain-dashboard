"""Credential-free snapshot transport for the public GitHub Pages dashboard."""
import json
from datetime import timedelta
from pathlib import Path

from backend import main as m
from backend.dengta_daily import daily_data, initialize as init_daily
from backend.dengta_hourly import hourly_data, initialize as init_hourly

META = {'scope','frequency','statistical_date','resets_daily','sample_minute','request_started_at',
        'broadcast_id','broadcast_start','broadcast_end','programme','channel','total_episodes',
        'missing_reason','peak_resolution','rank_scope','episodes','history_origin'}


def public_series(source):
    cutoff=(m.now()-timedelta(days=3)).isoformat()
    return [reading(r) for r in m.series(source,hours=720,all_history=True)
            if r['metric']!='availability' and not ((source=='dengta' or r['metric'] in ('kuyun_live_rating','kuyun_live_share','kuyun_history_rating'))
                and (r.get('collected_at') if source=='dengta' else r['time'])<cutoff)]


def reading(row):
    result = {k:row[k] for k in ('metric','value','unit','time','collected_at','source_time') if k in row}
    result.update(url='',source_url='',metadata={k:v for k,v in row.get('metadata',{}).items() if k in META})
    return result


def export_snapshot():
    overview = m.overview()
    sources=[]
    for source in overview['sources']:
        row={k:source[k] for k in ('id','name','kind','color','state','last_success','last_attempt','collection_interval_minutes')}
        row['url']='';row['metrics']=[reading(r) for r in source['metrics']]
        state=source.get('state')
        row['message']=source.get('message','') if source['id']=='kuyun' else (
            '最近采集成功' if state=='ok' else '正在更新' if state=='running' else '来源本次未返回有效数据，保留历史读数')
        if source.get('broadcast'):
            row['broadcast']={k:v for k,v in source['broadcast'].items() if k!='announcement_url'}
        sources.append(row)
    daily=daily_data(m.DB_PATH);hourly=hourly_data(m.DB_PATH)
    return {'schema_version':1,'overview':{'title':m.TITLE,'dramas':[m.TITLE],'updated_at':overview['updated_at'],'sources':sources},
            'series':{source:public_series(source) for source in m.SOURCES},
            'dengta_daily':{'points':[reading(r) for r in daily['points']],'status':{'state':daily['status']['state']}},
            'dengta_hourly':{**{k:v for k,v in hourly.items() if k not in ('rows','status')},
                'rows':[{k:v for k,v in r.items() if k!='source_url'} for r in hourly['rows']],
                'status':{'state':hourly['status']['state']}}}


def restore_snapshot(snapshot):
    """Restore only documented public fields, never source configuration or sessions."""
    if snapshot.get('schema_version')!=1:raise ValueError('Unknown snapshot schema')
    m.init_db();init_daily(m.DB_PATH);init_hourly(m.DB_PATH)
    with m.db() as conn:
        for source,rows in snapshot.get('series',{}).items():
            if source not in m.SOURCES:continue
            for row in rows:
                conn.execute('INSERT OR IGNORE INTO observations(source,metric,value,unit,collected_at,source_time,source_url,metadata_json,drama) VALUES(?,?,?,?,?,?,?,?,?)',
                    (source,row['metric'],row['value'],row.get('unit',''),row['collected_at'],row.get('source_time'),'',json.dumps(row.get('metadata',{}),ensure_ascii=False),m.TITLE))
        for source in snapshot['overview']['sources']:
            conn.execute('UPDATE collection_status SET state=?,last_success=?,last_attempt=?,message=? WHERE source=? AND drama=?',
                         (source['state'],source.get('last_success'),source.get('last_attempt'),source.get('message',''),source['id'],m.TITLE))
        days={}
        for row in snapshot['dengta_daily']['points']:
            days.setdefault(row['time'],{})[row['metric']]=row
        for day,rows in days.items():
            plays=rows.get('dengta_play_count');share=rows.get('dengta_play_share')
            if plays and share:
                conn.execute('INSERT OR REPLACE INTO dengta_daily VALUES(?,?,?,?,?)',(day,plays['value'],share['value'],plays['collected_at'],''))
        for row in snapshot['dengta_hourly']['rows']:
            conn.execute('INSERT OR REPLACE INTO dengta_hourly VALUES(?,?,?,?,?,?)',(row['day'],row['hour'],row['plays'],row.get('share'),row['collected_at'],''))
    conn.close()


def save_snapshot(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(export_snapshot(),ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    temporary.replace(path)
