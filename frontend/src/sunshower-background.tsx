/** Always-on sunlight and rain, drawn behind the content without intercepting input. */
export function SunshowerBackground(){
 return <div className="sunshower-background" aria-hidden="true"><div className="sunshower-sun"/><div className="sunshower-rays"/><div className="sunshower-orb"/><div className="sunshower-rain">{Array.from({length:80},(_,i)=><i key={i} style={{left:`${(i*37)%104}%`,animationDelay:`-${(i*1.7)%9}s`,animationDuration:`${.65+(i%5)*.14}s`,height:`${14+(i%4)*8}px`,opacity:.46+(i%3)*.1}}/>)}</div></div>;
}
