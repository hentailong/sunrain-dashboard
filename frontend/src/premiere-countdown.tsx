import {useEffect,useState} from 'react';
import {stamp} from './comparison-chart';

export function countdownParts(target:number,now:number){
 const seconds=Math.max(0,Math.ceil((target-now)/1000));
 return {hours:Math.floor(seconds/3600),minutes:Math.floor(seconds/60)%60,seconds:seconds%60,ended:seconds===0};
}

export function PremiereCountdown({at}:{at:string}){
 const target=stamp(at);const [now,setNow]=useState(Date.now());
 useEffect(()=>{setNow(Date.now());if(!Number.isFinite(target)||target<=Date.now())return;
  const timer=setInterval(()=>{const time=Date.now();setNow(time);if(time>=target)clearInterval(timer)},1000);
  return()=>clearInterval(timer);
 },[target]);
 if(!Number.isFinite(target))return null;
 const parts=countdownParts(target,now);
 if(parts.ended)return <p className="premiere-countdown-ended">已到首播时间，等待节目单确认</p>;
 return <div className="premiere-countdown" role="timer" aria-label="距离电视首播"><p>距离电视首播</p><div className="countdown-digits">{[['时',parts.hours],['分',parts.minutes],['秒',parts.seconds]].map(([label,value])=><div key={label}><b>{String(value).padStart(2,'0')}</b><small>{label}</small></div>)}</div></div>;
}
