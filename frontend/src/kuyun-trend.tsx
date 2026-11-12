import type {ReactNode} from 'react';
import type {Point} from './comparison-chart';
import {kuyunChartData} from './kuyun-chart-data';
import {measurementTime} from './data-display';

const rate=(value:number|null|undefined)=>value==null?'—':value.toFixed(4);
const clock=(value:number)=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(value);

export function KuyunTrend({rows,range,all=false,pending=false,error='',Chart,actions,compact=false}:{rows:Point[],range:{start:number,end:number},all?:boolean,pending?:boolean,error?:string,Chart:any,actions?:ReactNode,compact?:boolean}){
 const data=kuyunChartData(rows,range.start,range.end),last=all?data.daily[data.daily.length-1]:data.last;
 const hasData=all?data.daily.length>0:data.todayCount+data.yesterdayCount>0;
 const option={animation:false,tooltip:{trigger:'axis',confine:true,valueFormatter:(value:number|null)=>value==null?'暂无数据':rate(value)+'%'},
  legend:all?undefined:{data:['今日','昨日'],top:0,textStyle:{color:'#939daf'}},
  grid:{left:70,right:20,top:all?20:40,bottom:40},
  xAxis:all?{type:'category',data:data.daily.map(p=>p.time),axisLabel:{hideOverlap:true,formatter:(s:string)=>s.slice(5).replace('-','/')}}:{type:'time',min:data.range.start,max:data.range.end,axisLabel:{hideOverlap:true,formatter:clock},splitNumber:5},
  yAxis:{type:'value',scale:true,axisLabel:{formatter:(n:number)=>rate(n)+'%'}},
  series:all?[{name:'日均收视',type:'bar',barMaxWidth:30,itemStyle:{color:'#6bbad2',borderRadius:[3,3,0,0]},data:data.daily.map(p=>p.value)}]:data.series.map((points,index)=>({name:index?'昨日':'今日',type:'line',connectNulls:false,showSymbol:false,lineStyle:{color:index?'#9da6ba':'#6bbad2',type:index?'dashed':'solid',width:2},data:points}))};
 return <section className={compact?'solo-chart':'chart-panel platform-history'} data-metric="kuyun_live_rating" aria-label={all?'酷云日均收视趋势':'酷云今日与昨日收视'}>
  <div className="section-head"><div><h3>{compact?'酷云直播收视':all?'日均收视趋势':'区间趋势'}</h3><p>{all?'全部已发布日期 · 官方日均收视':'今日实线 · 昨日虚线 · 北京时间对齐'}</p></div>{actions}</div>
  <div className="trend-readouts"><div><small>{all?'最新日均收视':'今日最新'}</small><b>{rate(last?.value)}{last&&<em>%</em>}</b></div></div>
  {error&&<p className="connection-error">{error}</p>}
  {hasData?<Chart option={option}/>:<div className="solo-empty"><span>◷</span><p>{pending?'正在读取历史…':'暂无有效收视记录'}</p></div>}
  <div className="solo-chart-foot"><span>{all?`${data.daily.length} 个统计日`:`今日 ${data.todayCount} 条 · 昨日 ${data.yesterdayCount} 条`}{last?` · 截至 ${measurementTime(last.time)}`:''}</span></div>
  <p className="chart-note">{all?'使用酷云发布的节目日均收视，不以本地采样均值代替；未发布的日期不补值。':'今日为播出时段实时采样，昨日优先使用酷云官方分钟曲线；缺失分钟不补值，非播出时段不补零。'}</p>
 </section>;
}
