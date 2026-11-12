import {Point,stamp} from './comparison-chart';
import {isRank} from './data-display';

/** Best recorded value; the latest occurrence wins when the record is tied. */
export function historicalBest(rows:Point[],metric:string):Point|undefined {
 const rank=isRank(metric);
 return rows.filter(p=>p.metric===metric&&p.value!=null&&Number.isFinite(p.value)&&(rank?p.value>0:p.value>=0))
  .reduce<Point|undefined>((best,p)=>{
   if(!best||(rank?p.value!<best.value!:p.value!>best.value!)||
     (p.value===best.value&&stamp(p.time)>stamp(best.time)))return p;
   return best;
  },undefined);
}
