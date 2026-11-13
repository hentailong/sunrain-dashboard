/** Always-on sunlight and rain, drawn behind the content without intercepting input. */
export function SunshowerBackground(){
 return <div className="sunshower-background" aria-hidden="true"><div className="sunshower-sun"/><div className="sunshower-rays"/><div className="sunshower-orb"/><div className="sunshower-rain">{Array.from({length:48},(_,i)=><i key={i} style={{left:`${(i*37)%104}%`,animationDelay:`-${(i*1.7)%9}s`,animationDuration:`${3.2+(i%5)*.45}s`,height:`${40+(i%4)*15}px`,opacity:.24+(i%3)*.08}}/>)}</div></div>;
}
