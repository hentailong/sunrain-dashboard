import type {Point} from './comparison-chart';

/** Nearest Beijing minute; daily totals stay within their statistical day. */
export function minutePoint(p:Point):Point {
 if(!p.metric.startsWith('dengta_')||p.time.length===10)return p;
 const raw=Date.parse(p.collected_at||p.time);
 if(!Number.isFinite(raw))return p;
 const day=p.metadata?.statistical_date;
 const start=day?Date.parse(day+'T00:00:00+08:00'):Math.floor((raw+28800000)/86400000)*86400000-28800000;
 const minute=Math.max(start,Math.min(Math.round(raw/60000)*60000,start+86340000));
 return {...p,time:p.metadata?.sample_minute||new Date(minute).toISOString(),source_time:p.source_time||p.time};
}

export function minuteHistory(rows:Point[]):Point[] {
 const result:Point[]=[], latest=new Map<string,Point>();
 for(const original of rows){
  const p=minutePoint(original);
  if(!p.metric.startsWith('dengta_')||p.time.length===10){result.push(p);continue}
  const key=p.metric+'|'+Date.parse(p.time),previous=latest.get(key);
  if(!previous||Date.parse(p.collected_at||p.time)>=Date.parse(previous.collected_at||previous.time))latest.set(key,p);
 }
 return [...result,...latest.values()].sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
}

/** Both series share all 1,440 minute positions; absent observations remain null. */
export function minuteComparison(today:Point[],yesterday:Point[],start:number){
 return [today,yesterday].map((rows,index)=>{
  const samples=new Map(minuteHistory(rows).map(p=>[Date.parse(p.time)+index*86400000,p]));
  return Array.from({length:1440},(_,minute)=>{
   const at=start+minute*60000,p=samples.get(at);
   return {value:[at,p?.value??null],url:p?.url};
  });
 });
}
