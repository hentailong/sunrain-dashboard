/** GitHub Pages reads public snapshots; local development uses FastAPI. */
export const GITHUB_DEPLOY = import.meta.env.VITE_GITHUB_DEPLOY === 'true';
export const API = (import.meta.env.VITE_API_BASE || 'http://localhost:8000/api').replace(/\/$/, '');
export const STATIC_DATA = GITHUB_DEPLOY && !import.meta.env.VITE_API_BASE;
export const COLLECTION_DELAY_NOTICE = '受 GitHub Actions 调度影响，数据更新可能延迟，请以各项统计时间为准。';
let snapshot: any;
let loadedAt = 0;
let inflight: Promise<any> | undefined;
async function fetchSnapshot(){
 const base=import.meta.env.VITE_DATA_URL||`${import.meta.env.BASE_URL}data/snapshot.json`;
 if(import.meta.env.VITE_DATA_URL){
  // Read the preceding completed minute. Twelve rotating refs outlive GitHub's
  // five-minute branch cache without relying on rate-limited anonymous APIs.
  const minute=Math.floor(Date.now()/60000)-1;
  const url=base.replace(/\/(?:refs\/heads\/)?data\/snapshot\.json$/,`/minute-${minute%12}/snapshot.json`);
  try{
   const r=await fetch(`${url}?t=${Date.now()}`,{cache:'no-store'});
   if(r.ok){const value=await r.json();if(value.publication_minute===minute)return value}
  }catch{}
 }
 const r=await fetch(`${base}?t=${Date.now()}`,{cache:'no-store'});
 if(!r.ok)throw new Error('数据快照读取失败');
 return r.json();
}
async function readSnapshot() {
 if (snapshot && Date.now()-loadedAt<15000) return snapshot;
 if (!inflight) inflight=fetchSnapshot()
  .then(value=>{if(!snapshot||Date.parse(value.overview.updated_at)>=Date.parse(snapshot.overview.updated_at))snapshot=value;loadedAt=Date.now();return snapshot}).finally(()=>{inflight=undefined});
 return inflight;
}
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
 if (!STATIC_DATA) return fetch(input,init);
 if (init?.method && init.method!=='GET') return new Response('',{status:405});
 const url=new URL(input,location.href), data=await readSnapshot();
 let value: any;
 if(url.pathname.endsWith('/overview')) value=data.overview;
 else if(url.pathname.endsWith('/series')) value=data.series[url.searchParams.get('source')||'']||[];
 else if(url.pathname.endsWith('/dengta/daily')) value=data.dengta_daily;
 else if(url.pathname.endsWith('/dengta/hourly')) value=data.dengta_hourly;
 else return new Response('',{status:404});
 return new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
}
