import type {Point} from './comparison-chart';

export function kuyunChartData(rows:Point[],start:number,end:number){
 const sorted=[...rows].sort((a,b)=>Date.parse(a.collected_at||a.time)-Date.parse(b.collected_at||b.time));
 const daily=new Map<string,Point>(), today=new Map<number,Point>(), yesterday=new Map<number,Point>();
 const officialDays=new Set(rows.filter(p=>p.metric==='kuyun_history_rating').map(p=>p.time.slice(0,10)));
 for(const p of sorted){
  if(p.metric==='kuyun_daily_rating'&&p.time.length===10&&Date.parse(p.time+'T00:00:00+08:00')<start){daily.set(p.time,p);continue}
  if(!['kuyun_live_rating','kuyun_history_rating'].includes(p.metric)||p.value==null)continue;
  const at=Date.parse(p.source_time||p.time),slot=Math.floor(at/60000)*60000;
  if(at>=start&&at<=end&&p.metric==='kuyun_live_rating')today.set(slot,p);
  if(at>=start-86400000&&at<start&&(p.metric==='kuyun_history_rating'||!officialDays.has(p.time.slice(0,10))))yesterday.set(slot+86400000,p);
 }
 const dailyPoints=[...daily.values()].sort((a,b)=>a.time.localeCompare(b.time));
 const slots=[...today.keys(),...yesterday.keys()].sort((a,b)=>a-b);
 const range=slots.length?{start:Math.max(start,slots[0]-300000),end:Math.min(start+86340000,slots[slots.length-1]+300000)}:{start,end:start+86340000};
 const series=[today,yesterday].map(map=>Array.from({length:1440},(_,minute)=>{
  const at=start+minute*60000,p=map.get(at);
  return {value:[at,p?.value??null],originalTime:p?.source_time||p?.time,official:p?.metric==='kuyun_history_rating'};
 }));
 const todayPoints=[...today.values()].sort((a,b)=>Date.parse(a.source_time||a.time)-Date.parse(b.source_time||b.time));
 return {daily:dailyPoints,series,range,last:todayPoints[todayPoints.length-1],todayCount:today.size,yesterdayCount:yesterday.size};
}
