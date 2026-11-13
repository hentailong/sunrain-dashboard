import {useEffect,useState} from 'react';
import {measurementTime} from './data-display';
import {API,apiFetch,STATIC_DATA} from './config';
import {forecastFromHistory} from './dengta-forecast';

type Hour={day:string,hour:number,plays:number,share:number|null,collected_at:string,source_url:string};
type HourlyData={today:string,yesterday:string,rows:Hour[],status:{state:string,last_success?:string,message?:string}};
const wan=(n:number)=>(n/10000).toLocaleString('zh-CN',{maximumFractionDigits:1})+' 万';
export function summarizeHours(today:Hour[],yesterday:Hour[]){
 const current=new Map(today.map(r=>[r.hour,r]));const previous=new Map(yesterday.map(r=>[r.hour,r]));
 let cutoff=0,currentTotal=0,previousTotal=0;
 // Compare the same continuous, complete window starting at midnight.
 while(cutoff<24&&current.has(cutoff)&&previous.has(cutoff)){
  currentTotal+=current.get(cutoff)!.plays;previousTotal+=previous.get(cutoff)!.plays;cutoff++;
 }
 return {total:today.reduce((sum,r)=>sum+r.plays,0),cutoff,currentTotal,previousTotal,diff:cutoff?currentTotal-previousTotal:null};
}

export function DengtaHourly({version,Chart}:{version?:string,Chart:any}){
 const [data,setData]=useState<HourlyData>();const [error,setError]=useState('');
 useEffect(()=>{let active=true;apiFetch(`${API}/dengta/hourly`).then(r=>{if(!r.ok)throw new Error('hourly');return r.json()}).then(value=>{if(active){setData(value);setError('')}}).catch(()=>{if(active)setError('分时数据暂时无法更新，保留此前记录。')});return()=>{active=false}},[version]);
 const today=(data?.rows||[]).filter(r=>r.day===data?.today);const yesterday=(data?.rows||[]).filter(r=>r.day===data?.yesterday);
 const summary=summarizeHours(today,yesterday);
 const forecast=forecastFromHistory(today,data?.rows||[],data?.today||'');
 const hourly=(rows:Hour[],share=false)=>Array.from({length:24},(_,hour)=>{const row=rows.find(r=>r.hour===hour);return {value:row?(share?row.share:row.plays/10000):null,url:row?.source_url}});
 const option={animation:false,textStyle:{color:'#929bad'},legend:{top:8,itemWidth:11,itemHeight:10,itemGap:16,textStyle:{color:'#b5bdcb',fontSize:11},data:['今日','昨日','市占率']},tooltip:{trigger:'axis',confine:true,backgroundColor:'#1c202b',borderColor:'#3a3e49',textStyle:{color:'#e9e6de'},formatter:(items:any[])=>{
  const hour=Number(items[0]?.dataIndex??0);return `${hour}:00–${hour+1}:00（北京时间）<br/>`+items.filter(p=>p.value!=null).map(p=>`${p.marker}${p.seriesName}：<b>${Number(p.value).toLocaleString('zh-CN',{maximumFractionDigits:2})}${p.seriesName==='市占率'?'%':' 万次'}</b>`).join('<br/>');
 }},grid:{left:64,right:62,top:48,bottom:38},xAxis:{type:'category',data:Array.from({length:24},(_,i)=>`${i}点`),axisTick:{show:false},axisLine:{lineStyle:{color:'#343844'}},axisLabel:{color:'#939daf',fontSize:10,interval:1,hideOverlap:true},splitLine:{show:true,lineStyle:{color:'#252a35'}}},yAxis:[{type:'value',min:0,name:'正片播放量（万次）',nameLocation:'middle',nameGap:47,nameTextStyle:{color:'#939daf',fontSize:10},axisLabel:{color:'#939daf',fontSize:10},splitLine:{lineStyle:{color:'#292e39'}}},{type:'value',min:0,name:'市占率（%）',nameLocation:'middle',nameGap:44,nameTextStyle:{color:'#939daf',fontSize:10},axisLabel:{color:'#939daf',fontSize:10,formatter:'{value}%'},splitLine:{show:false}}],series:[
  {name:'今日',type:'bar',data:hourly(today),barMaxWidth:34,itemStyle:{color:'#2897d6',borderColor:'#54b7e7',borderWidth:1,borderRadius:[3,3,0,0]}},
  {name:'昨日',type:'line',data:hourly(yesterday),connectNulls:false,symbol:'none',itemStyle:{color:'#949eb6'},lineStyle:{color:'#949eb6',type:'dashed',width:1.5}},
  {name:'市占率',type:'line',yAxisIndex:1,data:hourly(today,true),connectNulls:false,symbol:'circle',symbolSize:5,lineStyle:{color:'#ffc458',width:1.8},itemStyle:{color:'#ffc458'}}
 ]};
 return <article className="dengta-hourly-panel" data-metric="dengta_hourly"><header><h3>正片播放量 · 分时</h3><p>灯塔全网正片播放量 · {STATIC_DATA?'定时采集':'每分钟检查'}{data?.status.last_success?` · 最近采集 ${measurementTime(data.status.last_success)}`:''}<br/>仅显示已结束的完整小时 · 北京时间 {data?.today||''}</p></header>{error||data?.status.state==='error'?<p className="hourly-notice" role="status">{error||data?.status.message}</p>:null}<Chart option={option}/>{!today.length&&<p className="hourly-notice">{data?'今日尚未返回完整小时数据。':'正在读取灯塔分时数据…'}</p>}<div className="hourly-summary"><div><span>分时合计</span><b>{today.length?wan(summary.total):'—'} · 已闭合 {today.length} / 24 格</b></div><div><span>昨日同时段</span>{summary.diff!=null?<b><i className={summary.diff>0?'up':summary.diff<0?'down':'flat'}>{summary.diff>0?'▲':summary.diff<0?'▼':'—'} {wan(Math.abs(summary.diff))}</i> · 两边都算到 {String(summary.cutoff).padStart(2,'0')}:00 · 昨日 {wan(summary.previousTotal)}</b>:<small>{yesterday.length?'尚无连续完整的共同小时，暂不计算差值':'昨日分时尚未存档，积累后显示虚线与差值'}</small>}</div><div className="hourly-forecast"><span>{forecast.available&&forecast.complete?'今日全天播放量':'预测今日总播放量'}</span><div className="hourly-forecast-value">{forecast.available?<><b>{forecast.complete?'':'约 '}{wan(forecast.total)}</b><small>{forecast.complete?'24 个完整小时已齐全 · 实际值':`已统计 ${wan(summary.total)} ＋ 后续预测 ${wan(forecast.remaining)} · 仅供参考`}</small></>:<small>{forecast.reason}</small>}</div></div></div>{forecast.available&&!forecast.complete&&<p className="hourly-forecast-note">参考近 7 天内 {forecast.referenceDays.length} 个完整历史日（{forecast.referenceDays.map(day=>day.slice(5).replace('-','/')).join('、')}），结合今日最近 {Math.min(6,forecast.cutoff)} 小时的同比增减与差值估算；较近日期和小时权重更高，每小时更新。</p>}</article>;
}
