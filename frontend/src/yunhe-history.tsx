import {useMemo} from 'react';
import {Point,stamp} from './comparison-chart';
import {formatValue} from './data-display';

const METRICS=[
 {key:'market_share',name:'有效播放市占',unit:'%',color:'#4d96c2'},
 {key:'yunhe_all_heat',name:'全舆情热度',unit:'热度指数',color:'#82c4bd'},
];

export function yunheDailySeries(rows:Point[]){
 const maps=METRICS.map(metric=>{
  const days=new Map<string,Point>();
  for(const row of rows.filter(p=>p.metric===metric.key).sort((a,b)=>stamp(a.collected_at||a.time)-stamp(b.collected_at||b.time))){
   if(/^\d{4}-\d{2}-\d{2}$/.test(row.time)&&Number.isFinite(stamp(row.time)))days.set(row.time,row);
  }
  return days;
 });
 const dates=[...new Set(maps.flatMap(map=>[...map.keys()]))].sort();
 const timeline:string[]=[];
 if(dates.length)for(let time=stamp(dates[0]);time<=stamp(dates[dates.length-1]);time+=86400000)timeline.push(new Date(time+8*3600000).toISOString().slice(0,10));
 return {dates,timeline,series:maps.map(map=>timeline.map(day=>{
  const point=map.get(day);
  return {value:point?.value??null,url:point?.url,day,unit:point?.unit};
 }))};
}

export function YunheHistory({rows,pending,error,Chart}:{rows:Point[],pending:boolean,error:string,Chart:any}){
 const data=useMemo(()=>yunheDailySeries(rows),[rows]);
 const hasValues=data.series.some(series=>series.some(p=>p.value!=null));
 const option={animation:false,legend:{top:8,itemGap:25,textStyle:{color:'#c4c8d3'},data:METRICS.map(m=>m.name)},tooltip:{trigger:'axis',confine:true,backgroundColor:'#1c202b',borderColor:'#3a3e49',textStyle:{color:'#eee7dc'},formatter:(items:any[])=>{
  const date=items[0]?.axisValue||'';
  return `统计日期 ${date}<br/>`+METRICS.map(metric=>{
   const point=items.find(p=>p.seriesName===metric.name);
   return `${point?.marker||''}${metric.name}：<b>${point?.value!=null?formatValue(Number(point.value))+' '+metric.unit:'暂无数据'}</b>`;
  }).join('<br/>');
 }},grid:{left:65,right:76,top:66,bottom:48},xAxis:{type:'category',data:data.timeline,boundaryGap:true,axisTick:{show:false},axisLine:{lineStyle:{color:'#343844'}},axisLabel:{color:'#a0a9ba',hideOverlap:true,formatter:(date:string)=>date.slice(5).replace('-','/')}},yAxis:METRICS.map((metric,i)=>({type:'value',min:0,name:i?'全舆情热度':'有效播放市占（%）',position:i?'right':'left',nameTextStyle:{color:metric.color,fontSize:11},axisLabel:{color:metric.color,formatter:(value:number)=>i?formatValue(value):`${value}%`},splitLine:{show:i===0,lineStyle:{color:'#2b303d',type:'dashed'}}})),series:METRICS.map((metric,i)=>({name:metric.name,type:i===0?'bar':'line',yAxisIndex:i,barMaxWidth:48,connectNulls:false,symbol:'circle',symbolSize:6,itemStyle:{color:metric.color,...(i===0?{borderRadius:[4,4,0,0]}:{})},lineStyle:{color:metric.color,width:2.5},data:data.series[i]}))};
 return <section className="chart-panel platform-history yunhe-history"><div className="section-head"><div><h3>有效播放市占与全舆情热度</h3><p>全部统计日期 · {data.dates.length}天{data.dates.length?` · ${data.dates[0]} — ${data.dates[data.dates.length-1]}`:''}</p></div></div>{error&&<p className="connection-error" role="alert">{error}</p>}{pending?<div className="chart-skeleton">读取云合历史中…</div>:hasValues?<Chart option={option}/>:<div className="empty-history"><span>◷</span><h3>尚无云合历史记录</h3><p>取得有效数据后，将按来源统计日期展示。</p></div>}<p className="chart-note">左轴为有效播放市占率，右轴为全舆情热度；两项指标按各自统计日期展示。同日修订取最后一条记录，缺失日期不补值。</p></section>;
}
