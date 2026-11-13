import {memo,useEffect,useRef} from 'react';
import {startRain} from './rain-renderer';

const RAINBOW_COLORS=['#dba5a3','#e3bd95','#ddd39c','#b8cdb6','#a8c9d2','#b2bfd9','#c6b4d3'];
/** A single rain surface shares the CSS weather clock; data updates do not restart it. */
export const SunshowerBackground=memo(function SunshowerBackground(){
 const rain=useRef<HTMLCanvasElement>(null);
 useEffect(()=>rain.current?startRain(rain.current):undefined,[]);
 return <><div className="sunshower-background" aria-hidden="true">
  <div className="sunshower-cloudlight"/>
  <div className="sunshower-daylight"><div className="sunshower-sun"/><div className="sunshower-rays"/></div>
  <div className="sunshower-rainbow"><svg viewBox="0 0 500 330" fill="none" focusable="false">{RAINBOW_COLORS.map((color,i)=><path key={color} d={`M -60 ${80+i*5} C 245 ${20+i*5} ${400-i*5} 100 ${430-i*5} 340`} stroke={color} strokeWidth="7" strokeLinecap="round"/>)}</svg></div>
  <canvas className="sunshower-rain" ref={rain}/>
 </div><div className="sunshower-bokeh" aria-hidden="true">{[0,1,2,3,4].map(i=><svg key={i} viewBox="0 0 100 100" fill="none" focusable="false"><polygon points="50,3 91,26.5 91,73.5 50,97 9,73.5 9,26.5" fill="#fffbed" fillOpacity=".32" stroke="#dfcda4" strokeOpacity=".85" strokeWidth="1.5"/></svg>)}</div></>;
});
