import { lazy, Suspense, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import type { Catalog } from "./catalog";
import Home from "./Home";
import Compare from "./Compare";
import "./site.css";
const Explorer=lazy(()=>import("./Explorer"));
type View="overview"|"compare"|"records";
function route() {const [path,query]=location.hash.slice(1).split('?');return {view:(["compare","records"].includes(path)?path:"overview") as View,language:new URLSearchParams(query).get('language')||undefined};}
export default function App() {
  const [locationState,setLocationState]=useState(route),[visitedRecords,setVisitedRecords]=useState(()=>route().view==='records');
  const [catalog,setCatalog]=useState<Catalog|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const view=locationState.view;
  useEffect(()=>{const update=()=>{const next=route();setLocationState(next);if(next.view==='records')setVisitedRecords(true);window.scrollTo(0,0);};window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);},[]);
  useEffect(()=>{const c=new AbortController();setError('');fetch(`${import.meta.env.BASE_URL}data/corpora.json`,{signal:c.signal}).then(r=>{if(!r.ok)throw Error('Dataset summaries could not load.');return r.json();}).then(setCatalog).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>c.abort();},[retry]);
  return <div className="site"><a className="skip-link" href="#main-content" onClick={e=>{e.preventDefault();document.getElementById("main-content")?.focus();}}>Skip to content</a><header className="site-header"><a className="site-brand" href="#overview"><img src={`${import.meta.env.BASE_URL}icon.png`} width="38" height="38" alt=""/><span>Dynaword<small>Scandinavian corpora</small></span></a><nav aria-label="Main navigation">{([['overview','Overview'],['compare','Compare corpora'],['records','Explore records']] as const).map(([key,name])=><a key={key} href={`#${key}`} aria-current={view===key?'page':undefined}>{name}</a>)}</nav></header>
    <div id="main-content" tabIndex={-1}>
      {view!=='records'&&(!catalog?<div className="site-loading">{error?<><p role="alert">{error}</p><button className="button" onClick={()=>setRetry(n=>n+1)}>Try again</button></>:<><LoaderCircle size={20} className="spin"/>Loading dataset summaries…</>}</div>:view==='overview'?<Home catalog={catalog}/>:<Compare key={locationState.language||'all'} catalog={catalog} initialLanguage={locationState.language}/>)}
      {visitedRecords&&<div hidden={view!=='records'}><Suspense fallback={<div className="site-loading"><LoaderCircle className="spin" size={20}/>Opening the record explorer…</div>}><Explorer active={view==='records'}/></Suspense></div>}
    </div>
    <footer className="site-footer"><span>Scandinavian Dynaword</span><div><a href="https://github.com/V4ldeSalnikov/scandinavian-dynaword-website/blob/main/LICENSE" target="_blank" rel="noreferrer">Website code · MIT licence</a><span>Corpus texts retain their source licences.</span></div></footer>
  </div>;
}
