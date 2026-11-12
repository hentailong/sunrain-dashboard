import {dailyHistory} from './daily-history';
import {PremiereCountdown} from './premiere-countdown';
import {historicalBest} from './milestone-history';
import {DengtaHourly} from './dengta-hourly';
import {useEffect,useMemo,useState} from 'react';
import {alignedComparison,snapshotPoint,stamp,Point} from './comparison-chart';
import {formatValue,isRank,measurementTime,resetsDaily,seriesSummary,timeWindow,queryHoursFor} from './data-display';
import {API,apiFetch} from './config';
import {KuyunTrend} from './kuyun-trend';

type Reading={metric:string,value:number|null,unit:string,collected_at:string,source_time?:string,source_url:string,metadata?:Record<string,unknown>};
type Source={id:string,name:string,state?:string,last_success?:string,message?:string,url:string,metrics?:Reading[],broadcast?:{channel:string,premiere_at:string,announcement_url:string,schedule?:{at:string,episodes:string,estimated?:boolean}[]}};
type Spec={source:string,metric:string,name:string,color:string};
const SPECS:Spec[]=[
 {source:'dengta',metric:'dengta_play_count',name:'今日正片播放量',color:'#efbd69'},
 {source:'dengta',metric:'dengta_play_share',name:'实时播放市占',color:'#efbd69'},
 {source:'kuyun',metric:'kuyun_live_rating',name:'酷云直播收视',color:'#6bbad2'},
 {source:'yunhe',metric:'market_share',name:'云合有效播放市占',color:'#a498e5'},
 {source:'yunhe',metric:'yunhe_all_heat',name:'云合全舆情热度',color:'#a498e5'},
 {source:'douyin',metric:'douyin_drama_heat',name:'抖音剧集热度',color:'#6bbad2'},
 {source:'maoyan',metric:'maoyan_heat_snapshot',name:'猫眼当日热度',color:'#ed947d'},
 {source:'weibo',metric:'topic_reads',name:'微博话题阅读',color:'#dc959e'},
 {source:'weibo',metric:'topic_discussions',name:'微博话题讨论',color:'#dc959e'},
 {source:'douban',metric:'rating',name:'豆瓣评分',color:'#6ec5a2'},
 {source:'douban',metric:'short_comments',name:'豆瓣短评',color:'#6ec5a2'},
 {source:'baidu_index',metric:'search_index',name:'百度搜索指数',color:'#82a7ed'},
 {source:'mango',metric:'mango_play_count',name:'芒果累计播放量',color:'#d7a563'},
];
const metricValue=(value:number|null|undefined,metric:string)=>metric.startsWith('kuyun_')&&value!=null?value.toLocaleString('zh-CN',{minimumFractionDigits:4,maximumFractionDigits:4}):formatValue(value);
const reading=(sources:Source[],spec:Spec)=>sources.find(s=>s.id===spec.source)?.metrics?.find(m=>m.metric===spec.metric);
const shortTime=(s?:string)=>s?measurementTime(s):'等待有效记录';
const escapeHtml=(v:string)=>v.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));

export function SingleDashboard({sources,version,Chart,onSource}:{sources:Source[],version?:string,Chart:any,onSource:(id:string)=>void}){
 const hours=0;
 const windowRange=useMemo(()=>timeWindow(hours),[hours,version]);
 const [history,setHistory]=useState<Record<string,Point[]>>({});const [failed,setFailed]=useState<string[]>([]);const [pending,setPending]=useState(true);
 const sourceIds=sources.filter(s=>s.id!=='mango'&&s.id!=='xiaohongshu').map(s=>s.id).join('|');
 // Keep a week for daily reports while intraday panels follow the selected window.
 const queryHours=Math.max(168,queryHoursFor(windowRange));
 useEffect(()=>{let active=true;setPending(true);Promise.allSettled(sourceIds.split('|').filter(Boolean).map(async id=>{const r=await apiFetch(`${API}/series?source=${id}&title=${encodeURIComponent('今天是太阳雨')}&hours=${queryHours}${['yunhe','douyin','weibo','baidu_index','kuyun'].includes(id)?'&all_history=true':''}`);if(!r.ok)throw new Error(id);return [id,await r.json()] as [string,Point[]]})).then(results=>{if(!active)return;const next:Record<string,Point[]>={};const errors:string[]=[];results.forEach((r,i)=>{if(r.status==='fulfilled')next[r.value[0]]=r.value[1];else errors.push(sourceIds.split('|')[i])});setHistory(old=>({...old,...next}));setFailed(errors);setPending(false)});return()=>{active=false}},[sourceIds,queryHours,version]);
 const episodes=sources.find(s=>s.id==='mango')?.metrics?.find(m=>m.metric==='updated_episodes');
 const total=Number(episodes?.metadata?.total_episodes)||0;
 const kuyun=sources.find(s=>s.id==='kuyun');const liveReading=reading(sources,SPECS[2]);const broadcast=kuyun?.broadcast;
 const live=kuyun?.state==='ok'&&liveReading?.value!=null&&Date.now()-stamp(liveReading.source_time||liveReading.collected_at)<180000&&Date.now()<stamp(String(liveReading.metadata?.broadcast_end||''));
 const beforePremiere=!!broadcast&&Date.now()<stamp(broadcast.premiere_at);
 const recentProgramme=String(liveReading?.metadata?.programme||'');
 
 const nextBroadcast=broadcast?.schedule?.filter(s=>stamp(s.at)>Date.now()-180000).sort((a,b)=>stamp(a.at)-stamp(b.at))[0];
 const televisionInfo=live?`播放中 · ${recentProgramme||'今天是太阳雨'}`:nextBroadcast?`${stamp(nextBroadcast.at)<=Date.now()?'等待开播确认':'下次播出'} ${shortTime(nextBroadcast.at)}${nextBroadcast.estimated?'（预计）':''} · 第 ${nextBroadcast.episodes} 集`:beforePremiere&&broadcast?`下次播出 ${shortTime(broadcast.premiere_at)}`:'下次播出时间待公布';
 const kuyunMetric=(key:string)=>kuyun?.metrics?.find(m=>m.metric===key&&m.value!=null);
 const kuyunDaily=kuyunMetric('kuyun_daily_rating'),kuyunPeak=kuyunMetric('kuyun_peak_rating'),kuyunHighest=kuyunMetric('kuyun_highest_daily_rating'),kuyunRank=kuyunMetric('kuyun_provincial_rank');
 const yesterdayDate=new Date(windowRange.start-1+28800000).toISOString().slice(0,10);
 const kuyunDailyLabel=kuyunDaily?.source_time===yesterdayDate?'昨日平均收视':'最近播出平均收视';
 const kuyunRankBadge=kuyunRank&&<span className="metric-rank" title={`节目历史收视排名 · ${kuyunRank.source_time}`}>省级卫视 No.{kuyunRank.value}</span>;

 const liveLabel=live?'播放中':kuyun?.state==='off_air'?(beforePremiere?'待首播':'非播出时段'):'暂未取得直播数据';
 const sections=[{id:'playback',title:'播放 · 实时表现',sub:'灯塔正片播放与云合有效播放分别展示',specs:[SPECS[0],SPECS[2],SPECS[3]]},{id:'heat',title:'热度 · 全网关注',sub:'各平台独立统计，不混合计算热度',specs:[SPECS[6],SPECS[11]]}];
 return <>
  <section className="drama-hero" aria-label="剧集介绍"><img className="drama-poster" src={`${import.meta.env.BASE_URL}images/sunrain-official-poster.jpg`} alt="今天是太阳雨 · 芒果TV官方海报" width="280" height="392" fetchPriority="high"/><div className="hero-copy"><p className="hero-kicker">剧集档案</p><h1>今天是太阳雨</h1><div className="hero-tags"><span>青春 · 爱情</span><span>中国内地</span><span>芒果TV独播</span>{total>0&&<span>全 <b>{total}</b> 集</span>}</div><div className="hero-cast"><h2>主演</h2><div>{['杨超越','董思成','孙宁','刘佳玺','孙毓舒','陈天明','李雨真','张思敏','肖添仁','杨童舒'].map(name=><span key={name}>{name}</span>)}</div></div><div className="hero-synopsis"><h2>剧情简介</h2><p>倔强少女郑雨与孤独少年陈砚周的故事。郑雨因家庭贫困被迫扛起重担，陈砚周因兄长离世陷入自我封闭，两人从校园竞争对手逐渐成为彼此生命中的光，共同面对人生暴雨。</p></div><div className="hero-broadcast"><span><b>湖南卫视</b>金鹰独播剧场</span><small>{televisionInfo}</small></div></div><div className="episode-track"><div><span>追剧进度 <b>{episodes?.value!=null?`已更新 ${episodes.value}${total?` / ${total}`:''} 集`:'等待平台更新'}</b></span><small>剧集资料来自芒果TV</small></div>{total>0&&episodes?.value!=null&&<progress aria-label="剧集更新进度" value={episodes.value} max={total}/>}<small>最近更新 {shortTime(episodes?.collected_at)}</small></div></section>
  <div className="dashboard-section-title"><h2>核心指标</h2><span className="live-pill"><i className="live-dot"/>灯塔每分钟检查</span><div/></div>
  <section className="core-metrics" aria-label="核心指标">{[...SPECS.filter(s=>!['short_comments','topic_discussions','topic_reads','rating'].includes(s.metric)),SPECS[7],SPECS[9]].map(spec=>{const stored=reading(sources,spec),m=spec.source==='kuyun'&&!live?kuyunDaily:stored,source=sources.find(s=>s.id===spec.source);const rankKey=spec.metric==='dengta_play_count'?'dengta_play_rank':spec.metric==='market_share'?'daily_rank':spec.metric==='yunhe_all_heat'?'yunhe_heat_rank':spec.source==='maoyan'?'rank':spec.source==='douyin'?'douyin_drama_rank':'';const rank=source?.metrics?.find(r=>r.metric===rankKey);const sameDate=['maoyan','dengta'].includes(spec.source)?!!m&&!!rank&&(m.source_time||m.collected_at).slice(0,10)===(rank.source_time||rank.collected_at).slice(0,10):!!m?.source_time&&rank?.source_time===m.source_time;return <div className="core-metric" style={{'--metric-color':spec.color} as React.CSSProperties} key={spec.metric}><div className="core-label"><span><b className="platform-glyph">{{mango:'芒',dengta:'灯',kuyun:'酷',douyin:'抖',maoyan:'猫',yunhe:'云',weibo:'微',douban:'豆',baidu_index:'百'}[spec.source]||'·'}</b>{source?.name||(spec.source==='kuyun'?'酷云':spec.source)}</span></div><h3>{spec.metric==='topic_reads'?'微博话题与官微':spec.name}{spec.source==='kuyun'&&kuyunRankBadge}{sameDate&&rank?.value!=null&&<span className="metric-rank" title={`排名${rank.source_time?'统计':'采集'} ${shortTime(rank.source_time||rank.collected_at)}`}>第 {rank.value} 名</span>}</h3><div className={`core-value ${m?.value==null?'missing':''}`}>{m?.value==null?(spec.metric==='rating'?'暂无评分':spec.source==='kuyun'?(beforePremiere?'待首播':'—'):'—'):isRank(spec.metric)?`第 ${m.value}`:metricValue(m.value,spec.metric)}<small>{m?.value!=null?m.unit:''}</small></div>{spec.source==='kuyun'&&<><small className="rank-date">{live?'实时收视率':kuyunDailyLabel}</small><div className="kuyun-card-stats"><span>历史最高均值 <b>{metricValue(kuyunHighest?.value,'kuyun_live_rating')}{kuyunHighest?'%':''}</b></span><span>历史秒峰值 <b>{metricValue(kuyunPeak?.value,'kuyun_live_rating')}{kuyunPeak?'%':''}</b></span></div></>}{spec.source==='mango'&&<small className="rank-date">官网取整展示值</small>}{spec.metric==='topic_reads'&&<small className="weibo-reading-label">累计话题阅读</small>}{spec.metric==='topic_reads'&&<div className="weibo-counts">{[['topic_discussions','讨论'],['official_followers','官微粉丝']].map(([key,name])=><span key={key}>{name} <b>{formatValue(source?.metrics?.find(m=>m.metric===key)?.value)}</b></span>)}</div>}{['yunhe','maoyan','douyin','dengta'].includes(spec.source)&&!sameDate&&rank?.value!=null&&<small className="rank-date">第 {rank.value} 名 · 排名统计 {shortTime(rank.source_time)}</small>}{spec.metric==='rating'&&<div className="douban-counts"><span>短评 <b>{formatValue(source?.metrics?.find(m=>m.metric==='short_comments')?.value)}</b></span><span>长评 <b>{formatValue(source?.metrics?.find(m=>m.metric==='reviews')?.value)}</b></span></div>}<p>{m?.value==null?(spec.source==='kuyun'?beforePremiere?'今晚20:10 · 湖南卫视':kuyun?.message||'正在检查节目单':String(m?.metadata?.missing_reason||'暂未取得有效数据')):`${m.source_time?'统计':'采集'} ${shortTime(m.source_time||m.collected_at)}`}</p>{source?.state!=='ok'&&spec.source!=='kuyun'&&m?.value!=null&&<small className="stale-reading">保留上次成功读数</small>}</div>})}</section>
  <div className="overview-highlights"><Milestones sources={sources} history={history}/><section className="broadcast-panel" aria-label="酷云直播收视"><div className="broadcast-heading"><div><p className="hero-kicker">LIVE TELEVISION</p><h2>酷云直播收视 {kuyunRankBadge}</h2><p>湖南卫视 · 今天是太阳雨</p></div><span className={`broadcast-state ${live?'is-live':''}`}>{liveLabel}</span></div><div className="broadcast-content"><div className="broadcast-reading">{beforePremiere&&broadcast?<PremiereCountdown at={broadcast.premiere_at}/>:<strong>{metricValue(live?liveReading?.value:kuyunDaily?.value,'kuyun_live_rating')}{(live?liveReading?.value:kuyunDaily?.value)!=null&&<em className="broadcast-unit">%</em>}</strong>}<span>{live?'实时收视率':beforePremiere?'今晚 20:10 起，金鹰独播剧场首播':kuyunDailyLabel}</span><div className="broadcast-stats">{[['历史最高均值',kuyunHighest?.value],['历史峰值（秒）',kuyunPeak?.value],...(live?[[kuyunDailyLabel,kuyunDaily?.value]]:[])].map(([label,value])=><div key={String(label)}><small>{label}</small><b>{value==null?(pending?'读取中…':'暂无数据'):`${metricValue(Number(value),'kuyun_live_rating')}%`}</b></div>)}</div><small className="broadcast-stats-note">酷云官方节目统计 · 排名统计日 {kuyunRank?.source_time||'暂无数据'}</small></div><div><p>{live?String(liveReading?.metadata?.programme||'今天是太阳雨'):kuyun?.message||'正在连接酷云节目单'}</p><small>{live?`来源更新 ${shortTime(liveReading?.source_time)}`:'每分钟核对节目名称；开播后自动记录，停播期间不补零。'}</small></div></div></section></div>
  <div className="single-trend-controls"><div><h2>数据趋势</h2><p>云合、百度指数展示全部统计日期 · 其他图表展示今日数据</p></div></div>
  {failed.length>0&&<p className="import-notice" role="alert">{failed.map(id=>sources.find(s=>s.id===id)?.name||id).join('、')}历史暂未更新，保留此前记录。</p>}
  {sections.map(section=>{const specs=section.specs;if(!specs.length)return null;return <section key={section.id} id={section.id} className="trend-section"><div className="dashboard-section-title"><h2>{section.title}</h2><span>{section.sub}</span><div/></div><div className="solo-chart-grid">{specs.map(spec=>spec.source==='kuyun'?<KuyunTrend key={spec.metric} rows={history.kuyun||[]} range={windowRange} pending={pending} Chart={Chart} compact/>:spec.source==='dengta'?<DengtaHourly key={spec.metric} version={version} Chart={Chart}/>:<TrendPanel key={spec.metric} spec={spec} rows={history[spec.source]||[]} range={windowRange} latest={reading(sources,spec)} pending={pending} Chart={Chart} onSource={()=>onSource(spec.source)} hours={hours}/>)}</div></section>})}
  <section className="source-strip"><div><h2>平台详情</h2><p>查看各平台指标、历史趋势与采集状态</p></div><div>{sources.map(s=><button key={s.id} onClick={()=>onSource(s.id)}><i className={s.state==='ok'?'status-ok':'status-idle'}/>{s.name}</button>)}</div></section>
 </>;
}

function TrendPanel({spec,rows,range,latest,pending,Chart,onSource,hours}:{spec:Spec,rows:Point[],range:{start:number,end:number},latest?:Reading,pending:boolean,Chart:any,onSource:()=>void,hours:number}){
 const metricRows=spec.source==='baidu_index'?dailyHistory(rows,spec.metric):rows.filter(p=>p.metric===spec.metric).map(snapshotPoint);
 const daily=metricRows.length>0&&metricRows.every(p=>p.time.length===10);
 const allDays=['yunhe','baidu_index'].includes(spec.source);
 const start=allDays?-Infinity:range.start;
 const points=metricRows.filter(p=>stamp(p.time)>=start&&stamp(p.time)<=range.end).sort((a,b)=>stamp(a.time)-stamp(b.time));
 const aligned=alignedComparison([points,[]],15*60000)[0];
 const broadcastMetric=spec.source==='kuyun';
 const days=broadcastMetric?[...new Set(aligned.filter(p=>p.value[1]!=null).map(p=>p.broadcastId))]:resetsDaily(spec.metric)?[...new Set(aligned.filter(p=>p.value[1]!=null).map(p=>p.statisticalDate||'unknown'))]:['all'];
 const summary=seriesSummary(points,spec.metric);
 const option={animation:false,textStyle:{color:'#a6abb9'},tooltip:{trigger:'axis',confine:true,backgroundColor:'#1c202b',borderColor:'#3a3e49',textStyle:{color:'#eee7dc'},formatter:(items:any[])=>{const p=items.find(p=>p.value?.[1]!=null);return p?`${spec.source==='dengta'?'采集 ':''}${escapeHtml(shortTime(p.data.originalTime))}${spec.source==='dengta'&&p.data.sourceTime?'<br/>来源更新 '+escapeHtml(shortTime(p.data.sourceTime)):''}<br/>${escapeHtml(spec.name)} <b>${metricValue(p.value[1],spec.metric)}${escapeHtml(latest?.unit||'')}</b>`:'暂无记录'}},grid:{left:62,right:24,top:18,bottom:48},xAxis:{type:'time',min:points.length?undefined:range.start,max:points.length?undefined:range.end,axisLine:{lineStyle:{color:'#353844'}},axisLabel:{color:'#9399a9',hideOverlap:true,formatter:(v:number)=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',...(daily||hours>=168?{month:'2-digit',day:'2-digit'}:{hour:'2-digit',minute:'2-digit',hour12:false})}).format(v)},splitNumber:5},yAxis:{type:'value',scale:true,inverse:isRank(spec.metric),minInterval:isRank(spec.metric)?1:undefined,axisLabel:{color:'#9399a9',formatter:(v:number)=>metricValue(v,spec.metric)},splitLine:{lineStyle:{color:'#272c37',type:'dashed'}}},dataZoom:[{type:'inside',zoomOnMouseWheel:'ctrl',filterMode:'none'}],series:days.map(day=>({name:spec.name,type:'line',smooth:false,connectNulls:false,symbol:'circle',symbolSize:5,showSymbol:points.length<80,lineStyle:{color:spec.color,width:2},itemStyle:{color:spec.color},areaStyle:{color:spec.color,opacity:.06},data:day==='all'?aligned:aligned.map(p=>(broadcastMetric?p.broadcastId===day:p.statisticalDate===day)?p:{...p,value:[p.value[0],null]})}))};
 return <article className="solo-chart" data-metric={spec.metric}><header><div><h3>{spec.name}</h3><p>{allDays?`全部统计日期 · ${new Set(points.map(p=>p.time.slice(0,10))).size}天`:daily?'今日统计':spec.source==='dengta'?'按采集分钟记录 · 当日统计，跨日分段':spec.source==='kuyun'?'每分钟检查 · 按实际播出时段分段':'按实际记录 · 15分钟对齐'}</p></div></header><div className="trend-readouts"><div><small>区间最新</small><b>{summary.last?metricValue(summary.last.value,spec.metric):'—'}<em>{summary.last?.unit||''}</em></b></div></div>{points.some(p=>p.value!=null)?<Chart option={option}/>:<div className="solo-empty"><span>◷</span><p>{pending?'正在读取历史…':'本时段暂无有效记录'}</p><small>{latest?.value!=null?`最近读数统计于 ${shortTime(latest.source_time||latest.collected_at)}`:'取得真实数据后在此展示'}</small></div>}<div className="solo-chart-foot"><span>{summary.count} 条实际记录{summary.last?` · 截至 ${shortTime(summary.last.time)}`:''}</span></div></article>;
}

function Milestones({sources,history}:{sources:Source[],history:Record<string,Point[]>}){
 const best=(source:string,metric:string)=>historicalBest(history[source]||[],metric);
 const satelliteRank=best('kuyun','kuyun_provincial_rank');
 const heatRank=best('yunhe','yunhe_heat_rank');const playRank=best('yunhe','daily_rank');
 const heatPeak=best('douyin','douyin_drama_heat');const readsPeak=best('weibo','topic_reads');
 const heatThreshold=heatPeak&&heatPeak.value!>=1e8?Math.floor(heatPeak.value!/1e8)*1e8:null;
 const readThreshold=readsPeak&&readsPeak.value!>=1e8?Math.floor(readsPeak.value!/1e8)*1e8:null;
 return <section className="milestone-panel" aria-label="里程碑与排名"><header><h2>里程碑与排名</h2><span>已采集历史最佳</span></header><div className="milestone-feature"><span>省级卫视收视排名 · 历史最佳</span><strong>{satelliteRank?<>TOP <em>{satelliteRank.value}</em></>:'等待榜单'}</strong><small>酷云数据 · 统计 {shortTime(satelliteRank?.time)}</small></div><div className="milestone-list"><div><span className="milestone-icon">✦</span><div><b>{heatRank?`云合全舆情热度榜历史最佳第 ${heatRank.value} 名`:'云合全舆情热度榜待更新'}</b><small>云合数据 · 统计 {shortTime(heatRank?.time)}</small></div></div><div><span className="milestone-icon">✦</span><div><b>{heatThreshold?`抖音剧集热度破 ${formatValue(heatThreshold)}`:'抖音剧集热度持续记录'}</b><small>{heatPeak?`历史峰值 ${formatValue(heatPeak.value)} · ${shortTime(heatPeak.time)}`:'等待有效历史'}</small></div></div><div><span className="milestone-icon">✦</span><div><b>{readThreshold?`微博话题阅读突破 ${formatValue(readThreshold)}`:'微博话题阅读持续记录'}</b><small>{readsPeak?`历史峰值 ${formatValue(readsPeak.value)} · ${shortTime(readsPeak.time)}`:'等待有效历史'}</small></div></div><div><span className="milestone-icon">▥</span><div><b>{playRank?`云合热播日榜历史最佳第 ${playRank.value} 名`:'云合热播日榜待更新'}</b><small>正片有效播放口径 · 统计 {shortTime(playRank?.time)}</small></div></div></div></section>;
}

