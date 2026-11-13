export type ForecastHour={hour:number,plays:number};

export type HistoricalHour=ForecastHour&{day:string};

/** Adjust each complete historical curve independently, then blend by recency. */
export function forecastFromHistory(today:ForecastHour[],history:HistoricalHour[],todayDate:string){
 const currentDate=Date.parse(todayDate+'T00:00:00+08:00');
 const unavailable=(reason:string)=>({available:false as const,reason});
 if(!/^\d{4}-\d{2}-\d{2}$/.test(todayDate)||!Number.isFinite(currentDate))return unavailable('统计日期异常，暂不预测');
 const validation=forecastDay(today,[]);
 if(validation.available&&validation.complete)return {...validation,referenceDays:[] as string[]};
 if(!validation.available&&validation.reason!=='昨日完整分时尚未齐全，暂不预测')return validation;
 const groups=new Map<string,ForecastHour[]>();
 for(const row of history){
  const age=(currentDate-Date.parse(row.day+'T00:00:00+08:00'))/86400000;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(row.day)||!Number.isInteger(age)||age<1||age>7)continue;
  const group=groups.get(row.day)||[];group.push(row);groups.set(row.day,group);
 }
 let weighted=0,weights=0;
 const referenceDays:string[]=[];
 for(const [day,rows] of [...groups].sort(([a],[b])=>a.localeCompare(b))){
  const prediction=forecastDay(today,rows);
  if(!prediction.available)continue;
  const age=(currentDate-Date.parse(day+'T00:00:00+08:00'))/86400000;
  const weight=2**(-(age-1)/3);
  weighted+=prediction.remaining*weight;weights+=weight;referenceDays.push(day);
 }
 if(!weights)return unavailable('近 7 天尚无完整分时历史，暂不预测');
 const remaining=weighted/weights,total=today.reduce((sum,r)=>sum+r.plays,0)+remaining;
 if(!Number.isFinite(total))return unavailable('分时变化异常，暂不预测');
 return {available:true as const,complete:false,total,remaining,cutoff:today.length,referenceDays};
}

/** Blend relative and absolute hourly changes; recent hours have more influence. */
export function forecastDay(today:ForecastHour[],yesterday:ForecastHour[]){
 const index=(rows:ForecastHour[])=>{
  const result=new Map<number,number>();
  for(const row of rows){
   if(!Number.isInteger(row.hour)||row.hour<0||row.hour>23||!Number.isFinite(row.plays)||row.plays<0||result.has(row.hour))return null;
   result.set(row.hour,row.plays);
  }
  return result;
 };
 const current=index(today),previous=index(yesterday);
 const unavailable=(reason:string)=>({available:false as const,reason});
 if(!current||!previous)return unavailable('分时数据异常，暂不预测');
 const count=current.size;
 if(count===24)return {available:true as const,complete:true,total:[...current.values()].reduce((a,b)=>a+b,0),remaining:0,cutoff:24};
 if(count<3)return unavailable('至少积累 3 个完整小时后预测');
 if(Array.from({length:count},(_,hour)=>hour).some(hour=>!current.has(hour)))return unavailable('今日分时存在缺口，暂不预测');
 if(previous.size!==24)return unavailable('昨日完整分时尚未齐全，暂不预测');
 let weights=0,deltaSum=0,ratioWeights=0,ratioSum=0;
 // Six recent completed hours, with a three-hour half-life. Compute both
 // same-hour ratios and differences, without interpreting a missing hour as 0.
 for(let hour=Math.max(0,count-6);hour<count;hour++){
  const weight=2**(-(count-1-hour)/3),actual=current.get(hour)!,baseline=previous.get(hour)!;
  weights+=weight;deltaSum+=weight*(actual-baseline);
  if(baseline>0){ratioWeights+=weight;ratioSum+=weight*actual/baseline}
 }
 const delta=deltaSum/weights,ratio=ratioWeights?ratioSum/ratioWeights:null;
 let remaining=0;
 for(let hour=count;hour<24;hour++){
  const baseline=previous.get(hour)!;
  const absolute=Math.max(0,baseline+delta);
  remaining+=ratio!==null&&baseline>0?(baseline*ratio+absolute)/2:absolute;
 }
 const total=[...current.values()].reduce((a,b)=>a+b,0)+remaining;
 if(!Number.isFinite(total))return unavailable('分时变化异常，暂不预测');
 return {available:true as const,complete:false,total,remaining,cutoff:count};
}
