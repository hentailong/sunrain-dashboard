/** A continuous rain → sunshine → rainbow cycle behind the readable glass surfaces. */
const RAINBOW_COLORS=['#d8837e','#dcaa74','#d7c77a','#9bb8a5','#89b2bb','#8c9fc1','#aa93b5'];
export function SunshowerBackground(){
 return <div className="sunshower-background" aria-hidden="true">
  <div className="sunshower-cloudlight"/>
  <div className="sunshower-daylight"><div className="sunshower-sun"/><div className="sunshower-rays"/><div className="sunshower-orb"/></div>
  <div className="sunshower-rainbow"><svg viewBox="0 0 500 360" fill="none" focusable="false">{RAINBOW_COLORS.map((color,i)=>{const r=340-i*3.5;return <path key={color} d={`M ${450-r} 360 A ${r} ${r} 0 0 1 450 ${360-r}`} stroke={color} strokeWidth="4.5"/>})}</svg></div>
  <div className="sunshower-rain">{Array.from({length:80},(_,i)=><i key={i} style={{left:`${(i*37)%104}%`,animationDelay:`-${(i*1.7)%9}s`,animationDuration:`${.65+(i%5)*.14}s`,height:`${14+(i%4)*8}px`,opacity:.46+(i%3)*.1}}/>)}</div>
 </div>;
}
