/** GitHub Pages reads public snapshots; local development uses FastAPI. */
export const GITHUB_DEPLOY = import.meta.env.VITE_GITHUB_DEPLOY === 'true';
export const API = (import.meta.env.VITE_API_BASE || 'http://localhost:8000/api').replace(/\/$/, '');
export const STATIC_DATA = GITHUB_DEPLOY && !import.meta.env.VITE_API_BASE;
let snapshot: any;
let loadedAt = 0;
let inflight: Promise<any> | undefined;
async function readSnapshot() {
 if (snapshot && Date.now()-loadedAt<15000) return snapshot;
 if (!inflight) inflight=fetch(`${import.meta.env.VITE_DATA_URL||`${import.meta.env.BASE_URL}data/snapshot.json`}?t=${Date.now()}`,{cache:'no-store'})
  .then(r=>{if(!r.ok)throw new Error('数据快照读取失败');return r.json()})
  .then(value=>{snapshot=value;loadedAt=Date.now();return value}).finally(()=>{inflight=undefined});
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
