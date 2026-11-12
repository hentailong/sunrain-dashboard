import {Point,stamp} from './comparison-chart';

/** One actual final valid reading per statistical day; never sum cumulative snapshots. */
export function dailyHistory(rows:Point[],metric:string){
 const days=new Map<string,Point>();
 for(const row of [...rows].filter(p=>p.metric===metric&&p.value!=null).sort((a,b)=>stamp(a.collected_at||a.time)-stamp(b.collected_at||b.time))){
  const day=String(row.metadata?.statistical_date||row.time.slice(0,10));
  if(/^\d{4}-\d{2}-\d{2}$/.test(day))days.set(day,{...row,time:day});
 }
 return [...days.values()].sort((a,b)=>a.time.localeCompare(b.time));
}

/** Prefer revised official daily heat; use observed snapshots for uncovered days/today. */
export function maoyanDailyHistory(rows:Point[]){
 const days=new Map(dailyHistory(rows,'maoyan_heat_snapshot').map(p=>[p.time,p]));
 for(const row of dailyHistory(rows,'daily_heat'))days.set(row.time,{...row,metric:'maoyan_heat_snapshot'});
 return [...days.values()].sort((a,b)=>a.time.localeCompare(b.time));
}
