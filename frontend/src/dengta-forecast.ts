export type ForecastHour={hour:number,plays:number};

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
