/** Decorative sunshower; CSS motion respects the system's reduced-motion setting. */
export function SunshowerBackground(){
 return <div className="sunshower-background" aria-hidden="true"><div className="sunshower-sun"/><div className="sunshower-rays"/><div className="sunshower-rain">{Array.from({length:24},(_,i)=><i key={i} style={{left:`${(i*37)%104}%`,animationDelay:`-${(i*1.7)%9}s`,animationDuration:`${4+(i%5)*.7}s`,height:`${35+(i%4)*15}px`,opacity:.14+(i%3)*.07}}/>)}</div></div>;
}
