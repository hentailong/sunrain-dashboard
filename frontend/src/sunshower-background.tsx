import {useState} from 'react';

const MOTION_KEY='sunrain-background-motion';
function initialMotion(){
 try{const saved=localStorage.getItem(MOTION_KEY);if(saved==='on'||saved==='off')return saved==='on'}catch{}
 return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** An explicit page preference can enable the shower without changing system settings. */
export function SunshowerBackground(){
 const [motion,setMotion]=useState(initialMotion);
 const toggle=()=>{const next=!motion;setMotion(next);try{localStorage.setItem(MOTION_KEY,next?'on':'off')}catch{}};
 return <><div className="sunshower-background" data-motion={motion?'on':'off'} aria-hidden="true"><div className="sunshower-sun"/><div className="sunshower-rays"/><div className="sunshower-rain">{Array.from({length:48},(_,i)=><i key={i} style={{left:`${(i*37)%104}%`,animationDelay:`-${(i*1.7)%9}s`,animationDuration:`${2.8+(i%5)*.45}s`,height:`${55+(i%4)*18}px`,opacity:.32+(i%3)*.1}}/>)}</div></div><button type="button" className="sunshower-toggle" aria-label="太阳雨动效" aria-pressed={motion} onClick={toggle}><span aria-hidden="true">☀</span>太阳雨 · {motion?'动态':'静止'}<i aria-hidden="true"/></button></>;
}
