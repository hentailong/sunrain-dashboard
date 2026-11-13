const CYCLE=60_000;
const FRAME=1000/30;

/** CSS fades the rain out at 42% and brings it back at 84% of the same cycle. */
export function rainPauseDelay(elapsed:number){
 const phase=((elapsed%CYCLE)+CYCLE)%CYCLE;
 return phase>=CYCLE*.42&&phase<CYCLE*.84?CYCLE*.84-phase:0;
}

export function startRain(canvas:HTMLCanvasElement){
 const ctx=canvas.getContext('2d',{alpha:true});
 if(!ctx)return()=>{};
 const started=performance.now();
 const weather=canvas.getAnimations?.().find(a=>(a as CSSAnimation).animationName==='sunshower-weather-rain');
 let width=0,height=0,count=0,frame=0,wake=0,lastFrame=-1000,stopped=false;
 const elapsed=()=>typeof weather?.currentTime==='number'?weather.currentTime:performance.now()-started;
 const resize=()=>{
  width=canvas.clientWidth||window.innerWidth;height=canvas.clientHeight||window.innerHeight;
  const ratio=Math.min(window.devicePixelRatio||1,1.25,Math.sqrt(2_500_000/(width*height)));
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
  ctx.setTransform(ratio,0,0,ratio,0,0);
  count=Math.min(150,Math.max(45,Math.round(width/7)));
 };
 const draw=(time:number)=>{
  ctx.clearRect(0,0,width,height);
  const seconds=time/1000;
  for(let depth=0;depth<3;depth++){
   ctx.beginPath();ctx.lineWidth=[.5,.65,.8][depth];ctx.lineCap='round';
   ctx.strokeStyle=['rgba(105,143,162,.16)','rgba(99,139,160,.24)','rgba(91,132,155,.34)'][depth];
   for(let i=depth;i<count;i+=3){
    const y=((seconds*(650+(i%5)*105)+i*137)%(height+90))-60;
    const x=((i*.61803398875%1)*(width+100)-y*.12+width+100)%(width+100)-50;
    const length=7+depth*3+(i%4)*2;
    ctx.moveTo(x+length*.12,y-length);ctx.lineTo(x,y);
   }
   ctx.stroke();
  }
 };
 const stopFrame=()=>{cancelAnimationFrame(frame);clearTimeout(wake);frame=0;wake=0};
 const tick=(now:number)=>{
  frame=0;if(stopped||document.hidden)return;
  const time=elapsed(),pause=rainPauseDelay(time);
  if(pause){ctx.clearRect(0,0,width,height);wake=window.setTimeout(()=>{wake=0;if(!stopped&&!document.hidden)frame=requestAnimationFrame(tick)},pause);return}
  if(now-lastFrame>=FRAME){lastFrame=now-(now-lastFrame)%FRAME;draw(time)}
  frame=requestAnimationFrame(tick);
 };
 const visibility=()=>{stopFrame();if(!document.hidden&&!stopped){lastFrame=-1000;frame=requestAnimationFrame(tick)}};
 resize();visibility();
 window.addEventListener('resize',resize,{passive:true});document.addEventListener('visibilitychange',visibility);
 return()=>{stopped=true;stopFrame();window.removeEventListener('resize',resize);document.removeEventListener('visibilitychange',visibility)};
}
