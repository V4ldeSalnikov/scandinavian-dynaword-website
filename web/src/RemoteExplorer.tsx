import {useEffect,useRef,useState} from 'react';
import {ArrowDown,ArrowUpRight,ArrowRight,Search,X,LoaderCircle,SlidersHorizontal,RefreshCw} from 'lucide-react';
import {api,compact,format,label,type Stats,type Filters} from './data';
import SelectionStatistics from './explorer/SelectionStatistics';
import SourceDetails from './explorer/SourceDetails';
import {CountryFlag,ExplorerHeading,type ExplorerView} from './explorer/ExplorerHeading';
import type {Corpus} from './catalog';
import {language} from './catalog';
type Row={id:string;record_no:number;source:string;domain:string;token_count:number;preview:string;config:string;row_index:number;annotations_available:boolean;[key:string]:unknown};
type Result={rows:Row[];has_more:boolean;next_offset:number;total:number|null;scanned?:number};
const fields:Record<string,string>={content_quality:'Content quality',pii_presence:'PII detection',content_integrity:'Content integrity',content_ratio:'Content ratio',content_length:'Content length',information_density:'Information density',educational_value:'Educational value',reasoning_indicators:'Reasoning indicators',content_safety:'Content safety'};
export default function RemoteExplorer({corpus}:{corpus:Corpus}) {
  const [view,setView]=useState<ExplorerView>('records');
  const [stats,setStats]=useState<Stats|null>(null),[statsLoading,setStatsLoading]=useState(false),[statsError,setStatsError]=useState('');
  const [source,setSource]=useState(''),[domain,setDomain]=useState(''),[annotations,setAnnotations]=useState<Record<string,string>>({}),[field,setField]=useState('content_quality');
  const [min,setMin]=useState(''),[max,setMax]=useState(''),[sourceQuery,setSourceQuery]=useState('');
  const [result,setResult]=useState<Result|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[offset,setOffset]=useState(0),[retry,setRetry]=useState(0),[mobile,setMobile]=useState(false),[jump,setJump]=useState('');
  const [searchInput,setSearchInput]=useState(''),[query,setQuery]=useState(''),[searchMode,setSearchMode]=useState('text'),[activeMode,setActiveMode]=useState('text');
  const [searchReady,setSearchReady]=useState({text:false,semantic:false});
  const dialog=useRef<HTMLElement>(null);
  useEffect(()=>{
    const c=new AbortController();
    const check=()=>api<{text:boolean;semantic:boolean}>(`corpora/${corpus.id}/search-status`,{},c.signal).then(r=>{if(!c.signal.aborted)setSearchReady(r);}).catch(()=>{});
    check();const timer=setInterval(check,30000);return()=>{c.abort();clearInterval(timer);};
  },[corpus.id]);
  const [active,setActive]=useState<Row|null>(null),[text,setText]=useState(''),[readerError,setReaderError]=useState(''),[readerLoading,setReaderLoading]=useState(false),[truncated,setTruncated]=useState(false),[textLimit,setTextLimit]=useState(16000),[readerTab,setReaderTab]=useState('text');
  const filterJSON=JSON.stringify({source,domain,annotations,min_tokens:min,max_tokens:max});
  useEffect(()=>{setOffset(0);setResult(null);},[filterJSON,query,activeMode]);
  useEffect(()=>{
    if(view!=='records')return;
    const c=new AbortController();setLoading(true);setError('');
    api<Result>(`corpora/${corpus.id}/${query?'search':'rows'}`,{filters:filterJSON,offset,...(query?{q:query,mode:activeMode}:{})},c.signal).then(next=>{if(!c.signal.aborted)setResult(previous=>offset&&previous?{...next,rows:[...previous.rows.filter(row=>!next.rows.some(n=>n.id===row.id&&n.source===row.source)),...next.rows]}:next);}).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!c.signal.aborted)setLoading(false);});
    return()=>c.abort();
  },[corpus.id,filterJSON,offset,retry,query,activeMode,view]);
  useEffect(()=>{
    if(!active)return;const c=new AbortController();setText('');setReaderError('');setReaderLoading(true);setTextLimit(16000);setReaderTab('text');
    api<{text:string;truncated:boolean}>(`corpora/${corpus.id}/record`,{id:active.id,config:active.config,row_index:active.row_index},c.signal).then(r=>{setText(r.text);setTruncated(r.truncated);}).catch(e=>{if(e.name!=='AbortError')setReaderError(e.message);}).finally(()=>{if(!c.signal.aborted)setReaderLoading(false);});
    const previous=document.activeElement as HTMLElement;const overflow=document.body.style.overflow;document.body.style.overflow='hidden';dialog.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')setActive(null);if(e.key==='Tab'){const items=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button,a[href],input,select')||[]).filter(el=>el.offsetParent!==null);const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}};document.addEventListener('keydown',escape);return()=>{c.abort();document.removeEventListener('keydown',escape);document.body.style.overflow=overflow;previous?.focus();};
  },[active,corpus.id]);
  useEffect(()=>{
    if(view!=='statistics')return;
    const c=new AbortController();setStats(null);setStatsLoading(true);setStatsError('');
    api<Stats>(`corpora/${corpus.id}/stats`,{filters:filterJSON,annotation:field},c.signal).then(r=>{if(!c.signal.aborted)setStats(r);}).catch(e=>{if(e.name!=='AbortError')setStatsError(e.message);}).finally(()=>{if(!c.signal.aborted)setStatsLoading(false);});
    return()=>c.abort();
  },[corpus.id,filterJSON,field,retry,view,searchReady.text]);
  const chartFilters:Filters={source,domain,...annotations,...(min?{min_tokens:Number(min)}:{}),...(max?{max_tokens:Number(max)}:{})};
  function chartFilter(key:keyof Filters,value:string|undefined){
    if(key==='source')setSource(value||'');else if(key==='domain'){setDomain(value||'');setSource('');}
    else setAnnotations(old=>{const next={...old};if(value)next[key]=value;else delete next[key];return next;});
  }
  const sources=corpus.sources.filter(s=>(!domain||s.domain===domain)&&s.id.toLowerCase().includes(sourceQuery.toLowerCase()));
  const selectedSources=corpus.sources.filter(s=>!domain||s.domain===domain);
  const selectedTotal=selectedSources.reduce((n,s)=>n+s.records,0);
  const hasFilters=source||domain||min||max||Object.keys(annotations).length;
  const displayedTitle=(row:Row)=>String(row.one_sentence_description||row.preview||row.id).split('\n').find(s=>s.trim())?.slice(0,130)||row.id;
  function clear(){setSource('');setDomain('');setAnnotations({});setMin('');setMax('');setOffset(0);}
  function annotation(value:string){setAnnotations(old=>{const next={...old};if(value)next[field]=value;else delete next[field];return next;});}
  const chips=Object.entries(annotations);
  return <div className="explorer remote-explorer"><div className="workspace">
    {mobile&&<button className="sidebar-backdrop" aria-label="Close filters" onClick={()=>setMobile(false)}/>}
    <aside className={`sidebar ${mobile?'open':''}`}><div className="sidebar-head"><span><SlidersHorizontal size={16}/> Filter corpus</span><button className="icon-button" onClick={clear} aria-label="Reset filters"><RefreshCw size={14}/></button><button className="icon-button mobile-only" aria-label="Close filters" onClick={()=>setMobile(false)}><X size={16}/></button></div>
      <div className="dataset-selector"><CountryFlag language={corpus.id}/><div><strong>{corpus.name}</strong></div></div>
      <label className="filter-label" htmlFor="remote-domain">DOMAIN</label><select id="remote-domain" value={domain} onChange={e=>{setDomain(e.target.value);setSource('');}}><option value="">All domains</option>{corpus.domains.map(d=><option key={d.name}>{d.name}</option>)}</select>
      <label className="filter-label" htmlFor="remote-source-search">DATA SOURCES</label><input id="remote-source-search" aria-label="Find a source" placeholder="Find a source…" value={sourceQuery} onChange={e=>setSourceQuery(e.target.value)}/><div className="source-list"><button className={`source-option ${!source?'selected':''}`} onClick={()=>setSource('')}>All sources <span>{compact(selectedTotal)}</span></button>{sources.map(s=><button className={`source-option ${source===s.id?'selected':''}`} key={s.id} onClick={()=>setSource(s.id)}>{s.name.replaceAll('_',' ')} <span>{compact(s.records)}</span></button>)}</div>
      <label className="filter-label" htmlFor="remote-annotation">ANNOTATIONS</label>{corpus.annotation_distributions?<><select id="remote-annotation" aria-label="Annotation field" value={field} onChange={e=>setField(e.target.value)}>{Object.entries(fields).map(([k,n])=><option key={k} value={k}>{n}</option>)}</select><select aria-label="Annotation value" value={annotations[field]||''} onChange={e=>annotation(e.target.value)}><option value="">All values</option>{annotations[field]==='__missing__'&&<option value="__missing__">Not annotated</option>}{Object.keys(corpus.annotation_distributions[field]||{}).map(v=><option key={v} value={v}>{label(v)}</option>)}</select></>:<p className="remote-muted">Not published for this release.</p>}
      {(corpus.annotation_distributions||searchReady.text)&&<><label className="filter-label">DOCUMENT LENGTH <small>tokens</small></label><div className="length-inputs"><input type="number" min="0" placeholder="Min" aria-label="Minimum tokens" value={min} onChange={e=>setMin(e.target.value)}/><span>–</span><input type="number" min="0" placeholder="Max" aria-label="Maximum tokens" value={max} onChange={e=>setMax(e.target.value)}/></div></>}
    </aside>
    <main><ExplorerHeading language={language(corpus)} version={corpus.version} view={view} onView={setView} onOpenFilters={()=>setMobile(true)}/>
      {view==='records'&&searchReady.text&&<form className="search-bar" onSubmit={e=>{e.preventDefault();setQuery(searchInput.trim());setActiveMode(searchMode);}}><Search size={19}/><input aria-label="Search the complete corpus" placeholder={`Search ${language(corpus)} texts…`} value={searchInput} onChange={e=>setSearchInput(e.target.value)} maxLength={1000}/><select aria-label="Search mode" value={searchMode} onChange={e=>setSearchMode(e.target.value)}><option value="text">Text search</option><option value="semantic" disabled={!searchReady.semantic}>Semantic search</option></select><button type="submit" disabled={searchInput.trim().length===1}>Search <ArrowRight size={15}/></button>{query&&<button type="button" className="text-button" aria-label="Clear search" onClick={()=>{setQuery('');setSearchInput('');}}><X size={15}/></button>}</form>}
      <div className="selection-bar"><div className="filter-chips">{domain&&<button onClick={()=>setDomain('')}>{domain} ×</button>}{source&&<button onClick={()=>setSource('')}>{source} ×</button>}{chips.map(([k,v])=><button key={k} onClick={()=>setAnnotations(old=>{const n={...old};delete n[k];return n;})}>{fields[k]}: {label(v)} ×</button>)}{min&&<button onClick={()=>setMin('')}>≥ {min} tokens ×</button>}{max&&<button onClick={()=>setMax('')}>≤ {max} tokens ×</button>}{!hasFilters&&<span>All records selected</span>}</div>{hasFilters&&<button className="text-button" onClick={clear}>Clear all</button>}</div>
      {view==='records'&&error&&<div className="remote-error" role="alert"><p>{error}</p><button className="button secondary" onClick={()=>setRetry(n=>n+1)}>Retry</button></div>}
      {view==='statistics'&&(statsError?<div className="remote-error" role="alert"><p>{statsError}</p><button className="button secondary" onClick={()=>setRetry(n=>n+1)}>Retry</button></div>:<SelectionStatistics stats={stats} loading={statsLoading} sources={corpus.sources} filters={chartFilters} annotation={field} onAnnotation={setField} onFilter={chartFilter} onRange={(a,b)=>{setMin(String(a));setMax(String(b));}} annotationFields={fields}/>)}
      {view==='sources'&&<SourceDetails sources={corpus.sources} domain={domain} selectedSource={source} query={sourceQuery} onExplore={id=>{setSource(id);setOffset(0);setView('records');}}/>}
      {view==='records'&&<><section className="panel records-panel" aria-busy={loading}><div className="panel-heading"><div><h2>{query?(activeMode==='semantic'?'Top matches':'Search results'):'Records'} <span className="count-badge">{result?.total!=null?compact(result.total):loading?'Loading…':'Filtered results'}</span></h2><p>Select a record to read its original text.</p></div>{loading&&<LoaderCircle size={18} className="spin"/>}</div>
        <div className="record-table-scroll"><table className="record-table"><thead><tr><th>TEXT / RECORD</th><th>SOURCE</th><th>TOKENS</th><th>QUALITY</th></tr></thead><tbody>{result?.rows.map(row=><tr key={`${row.config}/${row.row_index}/${row.id}`}><td><button className="record-title" onClick={()=>setActive(row)}>{displayedTitle(row)}</button><p className="record-preview">{row.preview.slice(0,220)}</p><small className="record-id">{row.id}</small></td><td>{row.source}</td><td>{format(row.token_count)}</td><td>{row.content_quality?label(String(row.content_quality)):'—'}</td></tr>)}</tbody></table>{!loading&&!error&&!result?.rows.length&&<div className="comparison-empty">{result?.has_more?'No matches in this batch. Continue to check the next records.':'No matching records.'}</div>}</div>
        <div className="record-footer"><span>{result?.rows.length||0} records loaded</span>{result?.has_more&&<button className="button secondary" disabled={loading} onClick={()=>setOffset(result.next_offset)}>{loading?'Loading…':'Load more records'} <ArrowDown size={14}/></button>}</div>
      </section>
      {!hasFilters&&!query&&<form className="record-jump" onSubmit={e=>{e.preventDefault();setResult(null);setOffset(Math.max(0,Math.min(corpus.records-1,Number(jump)-1)));setRetry(n=>n+1);}}><label>Go to record <input type="number" min="1" max={corpus.records} aria-label="Go to record number" placeholder="1" value={jump} onChange={e=>setJump(e.target.value)}/></label><button className="button secondary">Go</button></form>}
    </>}
    </main>
    {active&&<div className="modal-backdrop" onClick={()=>setActive(null)}><section ref={dialog} className="modal reader-modal" role="dialog" aria-modal="true" aria-label="Record reader" onClick={e=>e.stopPropagation()}><div className="modal-header"><h2>{active.source}</h2><button aria-label="Close record" onClick={()=>setActive(null)}><X size={20}/></button></div><div className="reader-tabs"><button className={readerTab==='text'?'active':''} onClick={()=>setReaderTab('text')}>Original text</button><button className={readerTab==='metadata'?'active':''} onClick={()=>setReaderTab('metadata')}>Metadata & annotations</button></div><div className="remote-reader-content">{readerTab==='text'?<>{readerError?<p role="alert">{readerError}</p>:!readerLoading?<><pre className="reader-text">{text.slice(0,textLimit)}</pre>{textLimit<text.length&&<button className="button secondary" onClick={()=>setTextLimit(n=>n+16000)}>Load more text</button>}{truncated&&<p>The dataset service shortened this record. <a href={corpus.sources.find(s=>s.id===active.source)?.url||corpus.url} target="_blank" rel="noreferrer">Open the source <ArrowUpRight size={12}/></a></p>}</>:<p><LoaderCircle className="spin" size={18}/> Loading original text…</p>}</>:<dl className="remote-metadata">{Object.entries(active).filter(([key,value])=>!['preview','text','config','row_index','record_no','text_truncated','annotations_available'].includes(key)&&value!=null).map(([key,value])=><div key={key}><dt>{label(key)}</dt><dd>{Array.isArray(value)?value.join(', '):String(value)}</dd></div>)}</dl>}</div></section></div>}
  </div></div>;
}
