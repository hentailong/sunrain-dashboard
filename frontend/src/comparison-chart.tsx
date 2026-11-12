import {useEffect,useMemo,useState,ReactNode} from 'react';
import {formatValue,resetsDaily} from './data-display';
import {API,apiFetch} from './config';
import {minutePoint} from './dengta-minutes';

const DRAMAS=['今天是太阳雨','折月亮'];
const COLORS=['#ed9b12','#5973d9'];
export type Range={start:number,end:number};
export type Point={metric:string,time:string,value:number|null,url:string,unit:string,collected_at?:string,source_time?:string,metadata?:Record<string,any>};
type Group={source:string,name:string,color?:string,left_status?:{state?:string,message?:string,collection_interval_minutes?:number},right_status?:{state?:string,message?:string,collection_interval_minutes?:number},rows:{metric:string,lower_is_better:boolean,comparable?:boolean,left?:{value:number|null,source_time?:string,collected_at?:string},right?:{value:number|null,source_time?:string,collected_at?:string}}[]};
export type History=Record<string,Point[][]>;
export const stamp=(s:string)=>Date.parse(s.length===10?s+'T00:00:00+08:00':s);
// The upstream timestamp can stay unchanged while Dengta's live values change.
export const snapshotPoint=minutePoint;
// Dengta refreshes every minute; keep that resolution in every comparison view.
const comparisonInterval=(metric:string,step:number)=>(metric.startsWith('dengta_')||metric.startsWith('kuyun_'))?60000:step;
const date=(v:number)=>new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
const escapeHtml=(s:string)=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export const compactTime=(v:number)=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(v);
const clockTime=(v:number)=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(v);
export function axisFor(range:Range){return {type:'time',min:range.start,max:range.end,splitNumber:5,axisLine:{lineStyle:{color:'#dce2e9'}},axisTick:{show:false},axisLabel:{fontSize:12,color:'#788496',hideOverlap:true,margin:12,formatter:(v:number)=>range.end-range.start<=48*3600000?clockTime(v):compactTime(v)}}}
export function zoomFor(){return [{type:'inside',xAxisIndex:0,filterMode:'none',zoomOnMouseWheel:'ctrl',moveOnMouseWheel:false}]}
export function SharedTimeBar({range,Chart}:{range:Range,Chart:any}){
 const option=useMemo(()=>({animation:false,grid:{left:0,right:0,top:0,bottom:0},xAxis:{...axisFor(range),show:false},yAxis:{show:false,type:'value'},tooltip:{show:false},dataZoom:[{type:'slider',xAxisIndex:0,filterMode:'none',left:8,right:8,top:6,height:18,showDetail:false,showDataShadow:false,brushSelect:false,borderColor:'#e4e8ee',backgroundColor:'#f3f5f8',fillerColor:'rgba(107,130,166,.13)',handleStyle:{color:'#fff',borderColor:'#8d9db3'},moveHandleSize:0}],series:[]}),[range.start,range.end]);
 return <div className="shared-timeline" aria-label="所有对比图的统一缩放滑块"><Chart option={option} sync="drama-comparison" className="timeline-chart"/></div>
}

// One request per source/drama; a failed adapter does not remove other sources.
export function useComparisonHistory(groups:Group[],hours:number,version?:string){
 const sources=groups.filter(g=>g.rows.some(r=>!['availability','page_displayed_metric'].includes(r.metric))).map(g=>g.source).join('|');
 const key=sources+'|'+hours;
 const [state,setState]=useState<{key:string,history:History,error:string,loading:boolean}>({key:'',history:{},error:'',loading:true});
 useEffect(()=>{let active=true;setState(old=>old.key===key?{...old,error:'',loading:true}:{key,history:{},error:'',loading:true});
 Promise.allSettled(sources.split('|').filter(Boolean).map(async source=>{
  const rows=await Promise.all(DRAMAS.map(title=>apiFetch(`${API}/series?source=${source}&hours=${hours}&title=${encodeURIComponent(title)}`).then(r=>{if(!r.ok)throw new Error(source);return r.json()})));
  return [source,rows] as const;
 })).then(results=>{if(!active)return;const succeeded:History={};const failed:string[]=[];for(const r of results){if(r.status==='fulfilled')succeeded[r.value[0]]=r.value[1];else failed.push(String(r.reason))}setState(old=>({key,history:{...(old.key===key?old.history:{}),...succeeded},error:failed.length?'部分平台历史读取失败；保留此前结果，其他平台仍正常展示。':'',loading:false}))});
 return()=>{active=false}
 },[key,version]);
 return state.key===key?state:{key,history:{},error:'',loading:true};
}

// Union of real timestamps: preserve either drama's history, with identical bounds everywhere.
export function fittedRange(history:History,window:Range,visible:boolean[],step=15*60000):Range{
 let first=Infinity,last=-Infinity;
 for(const pair of Object.values(history))for(let i=0;i<pair.length;i++)if(visible[i])for(const original of pair[i]){
  const p=snapshotPoint(original);
  const t=stamp(p.time);if(!['availability','page_displayed_metric'].includes(p.metric)&&p.value!=null&&Number.isFinite(t)&&t>=window.start&&t<=window.end){const slot=slotTime(p,comparisonInterval(p.metric,step));first=Math.min(first,slot);last=Math.max(last,slot)}
 }
 if(!Number.isFinite(first))return window;
 const span=last-first;
 // A lone observation needs a readable domain; never manufacture observations.
 const padding=Math.max(span*.025,span===0?30*60000:60000);
 return {start:Math.max(Math.floor((window.start+8*3600000)/step)*step-8*3600000,first-padding),end:Math.min(window.end,last+padding)};
}
const slotTime=(p:Point,step:number)=>p.time.length===10?stamp(p.time):Math.floor((stamp(p.time)+8*3600000)/step)*step-8*3600000;
// Compare observations in the same period, never carry a reading into an empty period.
export function alignedComparison(pair:Point[][],step=15*60000){
 pair=pair.map(rows=>rows.map(snapshotPoint));
 const points=pair.flat();
 const isDaily=points.length>0&&points.every(p=>p.time.length===10);
 const interval=isDaily?86400000:comparisonInterval(points[0]?.metric||'',step);
 const maps=pair.map(rows=>{const map=new Map<number,Point>();for(const p of [...rows].sort((a,b)=>stamp(a.time)-stamp(b.time)))map.set(slotTime(p,interval),p);return map});
 const slots=[...new Set(maps.flatMap(map=>[...map.keys()]))].sort((a,b)=>a-b);
 if(!slots.length)return [[],[]];
 const timeline:number[]=[];for(let t=slots[0];t<=slots[slots.length-1];t+=interval)timeline.push(t);
 const breaks=new Set<number>();for(const map of maps){let day='';for(const t of timeline){const p=map.get(t);const next=p?.metadata?.statistical_date;if(p&&resetsDaily(p.metric)&&day&&next&&day!==next)breaks.add(t);if(next)day=next}}
 return maps.map(map=>{const data:any[]=[];for(const t of timeline){const p=map.get(t);
  if(breaks.has(t))data.push({value:[t-1,null]});
  data.push({value:[t,p?.value??null],url:p?.url,originalTime:p?.time,sourceTime:p?.source_time,collectedAt:p?.collected_at,unit:p?.unit,statisticalDate:p?.metadata?.statistical_date,broadcastId:p?.metadata?.broadcast_id,interval});
 }return data});
}
export function comparisonSeries(aligned:any[][],visible:boolean[],metric:string){
 return DRAMAS.flatMap((title,i)=>{
  if(!visible[i])return [];
  const rows=aligned[i]||[];
  const days=resetsDaily(metric)?[...new Set(rows.filter(p=>p.value[1]!=null).map(p=>p.statisticalDate||'unknown'))]:['all'];
  return (days.length?days:['all']).map(day=>({id:title+'|'+day,name:title,type:'line',connectNulls:true,symbol:'circle',symbolSize:6,showSymbol:true,lineStyle:{color:COLORS[i],width:2},itemStyle:{color:COLORS[i]},data:day==='all'?rows:rows.map(p=>p.statisticalDate===day?p:{...p,value:[p.value[0],null],url:undefined})}));
 });
}
export function comparisonTooltip(params:any,titles=DRAMAS){
 const items=Array.isArray(params)?params:[params];const t=Number(items[0]?.axisValue??items[0]?.value?.[0]);
 const interval=items.find(p=>p.data?.interval)?.data.interval;
 const heading=Number.isFinite(t)?`<div style="font-size:12px;color:#748092;margin-bottom:12px">${compactTime(t)}${interval?' — '+(interval>=86400000?compactTime(t+interval):clockTime(t+interval)):''}</div>`:'';
 return heading+titles.map((title)=>{
  const p=items.find(p=>p.seriesName===title&&p.value?.[1]!=null);const color=COLORS[DRAMAS.indexOf(title)];
  return `<div style="margin-bottom:12px"><div style="display:flex;justify-content:space-between;gap:20px;align-items:center"><span style="color:${color}">${escapeHtml(title)}</span><b style="color:#243047;font-size:16px">${p?Number(p.value[1]).toLocaleString('zh-CN',{maximumFractionDigits:2}):'暂无数据'}</b></div>${p?`<div style="color:#8590a0;font-size:11px;margin-top:3px">原始记录时间 ${date(stamp(p.data.originalTime))}</div>`:''}</div>`;
 }).join('')+'<div style="border-top:1px solid #edf0f4;padding-top:8px;font-size:11px;color:#8590a0">同一时段最后一条记录</div>';
}
const numberLabel=(v:number)=>formatValue(v);

export function pairedReadout(aligned:any[][],visible:boolean[],range?:Range){
 const active=visible.flatMap((v,i)=>v?[i]:[]);const count=aligned[0]?.length||aligned[1]?.length||0;
 let chosen=-1;const inside=(i:number)=>{const t=(aligned[0]?.[i]||aligned[1]?.[i])?.value[0];return !range||(t>=range.start&&t<=range.end)};
 for(let i=count-1;i>=0;i--)if(inside(i)&&active.length&&active.every(j=>aligned[j]?.[i]?.value[1]!=null)){chosen=i;break}
 if(chosen<0)for(let i=count-1;i>=0;i--)if(inside(i)&&active.some(j=>aligned[j]?.[i]?.value[1]!=null)){chosen=i;break}
 return {points:aligned.map(rows=>rows[chosen]),time:chosen>=0?(aligned[0]?.[chosen]||aligned[1]?.[chosen])?.value[0]:undefined};
}
function MetricCard({group,metric,pair,range,readoutRange,visible,step,Chart,label,onAnalyze}:{group:Group,metric:Group['rows'][number],pair:Point[][],range:Range,readoutRange:Range,visible:boolean[],step:number,Chart:any,label:(s:string)=>string,onAnalyze:(source:string,metric:string)=>void}){
 const aligned=useMemo(()=>alignedComparison(pair,step),[pair,step]);
 const readout=pairedReadout(aligned,visible,readoutRange);
 const points=readout.points;
 const both=visible.every(Boolean)&&points.every(p=>p?.value[1]!=null);
 const canCompare=both&&metric.comparable&&points[0].unit===points[1].unit;
 const delta=canCompare?points[0].value[1]-points[1].value[1]:null;
 const series=comparisonSeries(aligned,visible,metric.metric);
 const option={animation:false,tooltip:{trigger:'axis',confine:true,backgroundColor:'#fff',borderColor:'#e7ebf0',padding:14,extraCssText:'max-width:290px;white-space:normal;box-shadow:0 8px 30px rgba(25,40,60,.12);border-radius:10px;',formatter:(params:any)=>comparisonTooltip(params,DRAMAS.filter((_,i)=>visible[i]))},legend:{show:false},grid:{left:58,right:18,top:16,bottom:38},xAxis:axisFor(range),dataZoom:zoomFor(),yAxis:{type:'value',scale:true,inverse:metric.lower_is_better,minInterval:metric.lower_is_better?1:undefined,splitNumber:4,splitLine:{lineStyle:{color:'#eef1f5',type:'dashed'}},axisLabel:{fontSize:12,color:'#8390a1',formatter:numberLabel}},series,...(!visible.some(Boolean)?{title:{text:'勾选剧集后查看趋势',left:'center',top:'middle',textStyle:{fontSize:13,color:'#8b97a7'}}}:{})};
 return <article className="chart-panel metric-comparison-chart" data-source={group.source} data-metric={metric.metric}>
  <div className="metric-card-heading"><h3>{label(metric.metric)}</h3><span className="metric-unit">{metric.lower_is_better?'排名越小越靠前':pair.flat().find(p=>p.unit)?.unit||''}</span></div>
  <div className={`paired-readings ${visible.filter(Boolean).length===1?'single-reading':''}`}>{DRAMAS.map((title,i)=>visible[i]&&<div key={title} className={`paired-reading drama-${i}`} data-value={points[i]?.value[1]} data-original-time={points[i]?.originalTime} title={points[i]?.originalTime?Number(points[i].value[1]).toLocaleString('zh-CN')+' '+(points[i].unit||'')+' · 原始记录 '+date(stamp(points[i].originalTime)):'此时段暂无数据'}><span><i/>{title}</span><b>{points[i]?.value[1]!=null?(metric.lower_is_better?'第'+numberLabel(points[i].value[1])+'名':numberLabel(points[i].value[1])+(points[i].unit==='%'?'%':'')):'暂无数据'}</b></div>)}</div>
  <div className="paired-context" data-time={readout.time}><span>{readout.time!=null?`${both?'图中共同刻度':'图中记录刻度'} · ${compactTime(readout.time)}`:'暂无可显示的记录'}</span>{delta!=null&&<span className="paired-delta">{metric.lower_is_better?(delta===0?'排名相同':`太阳雨${delta<0?'领先':'落后'}${Math.abs(delta)}位`):`差值 ${delta>0?'+':''}${numberLabel(delta)}${points[0].unit==='%'?'个百分点':''}`}</span>}</div>
  <Chart option={option} sync="drama-comparison"/>
  <div className="metric-card-foot"><span>{resetsDaily(metric.metric)?'当日统计 · 跨日分段':'同刻度对比'}</span><button className="metric-analyze" onClick={()=>onAnalyze(group.source,metric.metric)}>变化分析 ↗</button><details className="sample-info"><summary>记录信息</summary><div>{DRAMAS.map((title,i)=><p key={title}>{title}：{pair[i].filter(p=>p.value!=null).length}条记录 / {aligned[i].filter(p=>p.value[1]!=null).length}个对齐点</p>)}<p>连线展示走势，缺失时段没有补点。</p></div></details></div>
 </article>
}
export function MetricComparisonGrid({groups,history,range,readoutRange,visible,loading,error,Chart,label,step,renderDetails,onExpandRange,onAnalyze}:{groups:Group[],history:History,range:Range,readoutRange:Range,visible:boolean[],loading:boolean,error:string,Chart:any,label:(s:string)=>string,step:number,renderDetails:(source:string)=>ReactNode,onExpandRange:()=>void,onAnalyze:(source:string,metric:string)=>void}){
 return <div className="metric-comparison-sections">{error&&<p className="import-notice" role="alert">{error}</p>}{groups.map(g=>{
 const choices=g.rows.filter(r=>!['availability','page_displayed_metric'].includes(r.metric)).map(metric=>({metric,pair:(history[g.source]||[[],[]]).map(rows=>rows.filter(p=>p.metric===metric.metric))}));
 const present=choices.filter(c=>c.pair.some(rows=>rows.some(p=>p.value!=null)));
 const empty=choices.filter(c=>!present.includes(c));
 return <section className={`metric-source-section ${present.length?'':'source-without-chart'}`} key={g.source} data-source={g.source}>
  <div className="metric-source-heading"><div><span className="source-mark" style={{background:g.color||'#8591a2'}}>{g.name.slice(0,1)}</span><h2>{g.name}</h2><span className="source-caption">{present.length?`${present.length} 项趋势`:loading?'读取历史中':'当前时段暂无趋势'}</span></div><span className="source-cadence">{g.left_status?.collection_interval_minutes?`${g.left_status.collection_interval_minutes}分钟检查`:''}</span></div>
  {loading&&!present.length&&choices.some(c=>c.metric.left?.value!=null||c.metric.right?.value!=null)?<div className="chart-skeleton" role="status">正在读取{g.name}历史…</div>:<div className="metric-comparison-grid">{present.map(c=><MetricCard key={c.metric.metric} group={g} metric={c.metric} pair={c.pair} range={range} readoutRange={readoutRange} visible={visible} step={step} Chart={Chart} label={label} onAnalyze={onAnalyze}/>)}</div>}
  {!loading&&empty.length>0&&<div className="unavailable-metrics"><span>本时段无记录</span>{empty.map(c=><span className="empty-metric" key={c.metric.metric}>{label(c.metric.metric)}{c.metric.metric==='rating'&&c.metric.left?.value==null&&c.metric.right?.value==null?' · 暂未开分':''}</span>)}{empty.some(c=>c.metric.left?.value!=null||c.metric.right?.value!=null)&&<button onClick={onExpandRange}>查看7天历史 ↗</button>}</div>}
  {renderDetails(g.source)}
 </section>
 })}</div>
}
