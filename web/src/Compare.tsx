import { useMemo, useState } from "react";
import { ArrowUpRight, Download, Search } from "lucide-react";
import type { Catalog, Corpus } from "./catalog";
import { language } from "./catalog";
import { compact, format, percent, COLORS } from "./data";
import QualityComparison from "./QualityComparison";

const domainColors:Record<string,string>={...COLORS,Spoken:"#426e9d",Academic:"#916387",Technical:"#8b965a",Government:"#857b6b"};
export default function Compare({catalog,initialLanguage}: {catalog:Catalog;initialLanguage?:string}) {
  const [selected,setSelected]=useState<string[]>(initialLanguage&&catalog.datasets.some(d=>d.id===initialLanguage)?[initialLanguage]:catalog.datasets.map(d=>d.id));
  const [measure,setMeasure]=useState<"tokens"|"records">("tokens"),[scale,setScale]=useState<"count"|"share">("share"),[domain,setDomain]=useState(""),[query,setQuery]=useState(""),[limit,setLimit]=useState(12);
  const datasets=catalog.datasets.filter(d=>selected.includes(d.id));
  const domains=useMemo(()=>[...new Set(catalog.datasets.flatMap(d=>d.domains.map(g=>g.name)))].sort(),[catalog]);
  const selectedGroups=(d:Corpus)=>d.domains.filter(g=>!domain||g.name===domain);
  const amount=(d:Corpus)=>selectedGroups(d).reduce((sum,g)=>sum+g[measure],0);
  const max=Math.max(1,...datasets.map(amount));
  const sources=datasets.flatMap(d=>d.sources.filter(s=>(!domain||s.domain===domain)&&`${s.name} ${s.id} ${language(d)}`.toLowerCase().includes(query.toLowerCase())).map(s=>({...s,language:language(d),dataset:d.id,version:d.version}))).sort((a,b)=>b[measure]-a[measure]||a.id.localeCompare(b.id));
  const totalRecords=sources.reduce((n,s)=>n+s.records,0),totalTokens=sources.reduce((n,s)=>n+s.tokens,0);
  function exportCSV() {
    const quote=(v:unknown)=>'"'+String(v??'').replaceAll('"','""')+'"';
    const rows=[['Language','Version','Source','Domain','Records','Tokens','Machine-labelled records','Source card'],...sources.map(s=>[s.language,s.version,s.id,s.domain,s.records,s.tokens,s.annotated,s.url])];
    const url=URL.createObjectURL(new Blob([rows.map(row=>row.map(quote).join(',')).join('\n')],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='dynaword-source-comparison.csv';a.click();URL.revokeObjectURL(url);
  }
  return <main className="comparison-page">
    <div className="section-heading"><div><p className="section-label">CORPUS COMPARISON</p><h1>Compare the collections</h1><p>Select languages and a domain to compare their size and source composition.</p></div></div>
    <fieldset className="language-picker"><legend>Languages</legend>{catalog.datasets.map(d=><div key={d.id} className={`language-choice ${selected.includes(d.id)?'selected':''}`}><label><input type="checkbox" checked={selected.includes(d.id)} onChange={()=>{setSelected(s=>s.includes(d.id)?s.filter(x=>x!==d.id):[...s,d.id]);setLimit(12);}}/><strong>{language(d)}</strong><span>{d.version}</span></label><a href={d.url} target="_blank" rel="noreferrer" aria-label={`${language(d)} dataset card`}>Dataset card <ArrowUpRight size={12}/></a></div>)}</fieldset>
    <div className="comparison-controls"><label>Domain <select aria-label="Compare domain" value={domain} onChange={e=>{setDomain(e.target.value);setLimit(12);}}><option value="">All domains</option>{domains.map(d=><option key={d}>{d}</option>)}</select></label><label>Measure <select aria-label="Comparison measure" value={measure} onChange={e=>setMeasure(e.target.value as typeof measure)}><option value="tokens">Tokens</option><option value="records">Records</option></select></label><label>Scale <select aria-label="Comparison scale" value={scale} onChange={e=>setScale(e.target.value as typeof scale)}><option value="count">Absolute count</option><option value="share">Share of each corpus</option></select></label><button className="text-button" onClick={()=>{setSelected(catalog.datasets.map(d=>d.id));setDomain('');setQuery('');setLimit(12);}}>Reset comparison</button></div>
    {!datasets.length ? <div className="comparison-empty">Select at least one language to compare its sources and domains.</div> : <>
      <section className="comparison-chart" aria-label="Corpus domain comparison">
        <div className="section-heading"><h2>{domain||'Domains by language'}</h2><span>{scale==='count'?`Same scale · ${measure}`:`Percentage of each language’s ${measure}`}</span></div>
        {datasets.map(d=><div className="comparison-bar-row" key={d.id}><div className="bar-language"><strong>{language(d)}</strong><small>{d.version}</small></div><div className="comparison-bar-track">{selectedGroups(d).sort((a,b)=>domains.indexOf(a.name)-domains.indexOf(b.name)).map(g=><button key={g.name} style={{width:`${100*g[measure]/(scale==='share'?d[measure]:max)}%`,background:domainColors[g.name]||'#747984'}} title={`${language(d)} · ${g.name}: ${format(g[measure])} ${measure} (${percent(g[measure],d[measure])})`} aria-label={`${language(d)}, ${g.name}: ${format(g[measure])} ${measure}. Select domain.`} onClick={()=>{setDomain(domain===g.name?'':g.name);setLimit(12);}}/>)}</div><strong className="bar-total" title={`${format(amount(d))} ${measure}`}>{scale==='share'?percent(amount(d),d[measure]):compact(amount(d))}</strong></div>)}
        <p className="chart-hint">Tap a segment or domain below to compare it across languages.</p><div className="domain-legend">{domains.filter(n=>datasets.some(d=>d.domains.some(g=>g.name===n))).map(n=><button key={n} className={domain===n?'selected':''} aria-pressed={domain===n} onClick={()=>{setDomain(domain===n?'':n);setLimit(12);}}><i style={{background:domainColors[n]||'#747984'}}/>{n}</button>)}</div>
      </section>
      <QualityComparison datasets={datasets} domain={domain}/>
      <details className="domain-values"><summary>View exact domain counts</summary><section className="domain-matrix"><div className="section-heading"><h2>Counts by domain</h2></div><div className="comparison-table-scroll"><table><thead><tr><th>Domain</th>{datasets.map(d=><th key={d.id}>{language(d)}</th>)}</tr></thead><tbody>{domains.filter(n=>!domain||n===domain).map(n=><tr key={n}><th scope="row"><button onClick={()=>{setDomain(domain===n?'':n);setLimit(12);}}>{n}</button></th>{datasets.map(d=>{const group=d.domains.find(g=>g.name===n);return <td key={d.id}>{group?<><span>{format(group[measure])}</span><small>{percent(group[measure],d[measure])}</small></>:<span aria-label="No sources in this domain">—</span>}</td>;})}</tr>)}</tbody></table></div></section></details>
      <section className="source-comparison"><div className="section-heading"><h2>Sources <span className="count-badge">{sources.length}</span></h2><button className="quiet-link" onClick={exportCSV}><Download size={14}/> Export counts</button></div><div className="source-comparison-tools"><label><Search size={16}/><input aria-label="Find comparison source" placeholder="Find a source…" value={query} onChange={e=>{setQuery(e.target.value);setLimit(12);}}/></label><span>{compact(totalRecords)} records · {compact(totalTokens)} tokens in matching sources</span></div><div className="comparison-table-scroll"><table><thead><tr><th>Source</th><th>Language</th><th>Domain</th><th>Records</th><th>Tokens</th></tr></thead><tbody>{sources.slice(0,limit).map(s=><tr key={`${s.dataset}/${s.id}`}><th scope="row"><a href={s.url} target="_blank" rel="noreferrer">{s.name.replaceAll('_',' ')} <ArrowUpRight size={12}/></a></th><td>{s.language}</td><td>{s.domain}</td><td>{format(s.records)}</td><td>{format(s.tokens)}</td></tr>)}</tbody></table></div>{!sources.length&&<p className="comparison-empty">No matching sources.</p>}{sources.length>limit&&<button className="button secondary" onClick={()=>setLimit(n=>n+50)}>Show more sources ({limit} of {sources.length})</button>}</section>
    </>}
    <p className="comparison-footnote">Dataset licences vary by source. Follow a source’s documentation before reusing its texts. Comparisons use the releases above; record browsing covers all five languages. Danish search uses {catalog.indexed_danish.version}.</p>
  </main>;
}
