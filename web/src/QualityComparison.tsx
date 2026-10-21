import {useEffect,useState} from 'react';
import type {Corpus} from './catalog';
import {language} from './catalog';
import {format,compact,percent} from './data';
import ContextHelp from './ContextHelp';
const levels=[['unacceptable','Unacceptable','#b7192d'],['poor','Poor','#d76a78'],['adequate','Adequate','#d5b560'],['good','Good','#67a599'],['excellent','Excellent','#24685c'],['unreported','Unreported','#e6e8ec']];
export default function QualityComparison({datasets,domain}:{datasets:Corpus[];domain:string}) {
  const [scale,setScale]=useState('share'),[focus,setFocus]=useState(''),[inspected,setInspected]=useState<{language:string;level:string;count:number;total:number}|null>(null);
  const languageKey=datasets.map(d=>d.id).join(",");
  useEffect(()=>setInspected(null),[domain,languageKey]);
  const rows=datasets.map(d=>{
    const sources=d.sources.filter(s=>!domain||s.domain===domain);
    const total=domain?sources.reduce((n,s)=>n+s.records,0):d.records;
    const quality=domain?sources.reduce<Record<string,number>>((all,s)=>{for(const [key,n] of Object.entries(s.quality||{}))all[key]=(all[key]||0)+n;return all;},{}):(d.quality||{});
    const known=Object.values(quality).reduce((n,x)=>n+x,0);
    return {d,total,known,counts:{...quality,unreported:total-known} as Record<string,number>};
  });
  const max=Math.max(1,...rows.map(r=>focus?(r.counts[focus]||0):r.total));
  return <section className="quality-comparison" aria-label="Quality annotation comparison">
    <div className="section-heading"><h2>Annotations <ContextHelp label="About quality comparison">These quality levels are machine predictions, not human judgements. Bars use records, not tokens. Percentage shares use all records in each selected language and domain, including unreported labels. Unreported means no quality count is published; it is not a poor-quality score. Source and language differences can affect how the model assigns labels.</ContextHelp></h2><label>Quality · <select aria-label="Quality comparison scale" value={scale} onChange={e=>setScale(e.target.value)}><option value="share">Share of records</option><option value="count">Record count</option></select></label></div>
    <div className="chart-focus-line"><span>{domain?`${domain} sources`:'All domains'} · {focus?levels.find(l=>l[0]===focus)?.[1]:'Content quality'}</span>{focus?<button className="text-button" onClick={()=>{setFocus('');setInspected(null);}}>Show all quality levels</button>:<span>Tap a colour to compare that quality level</span>}</div>
    {rows.map(r=><div className="comparison-bar-row" key={r.d.id}><div className="bar-language"><strong>{language(r.d)}</strong></div><div className="comparison-bar-track">{levels.filter(l=>!focus||l[0]===focus).map(([key,label,color])=>{const count=r.counts[key]||0;return count>0&&<button key={key} style={{width:`${100*count/(scale==='share'?(r.total||1):max)}%`,background:color}} aria-label={`${language(r.d)}, ${label}: ${format(count)} records (${percent(count,r.total)}). Compare quality level.`} title={`${label}: ${format(count)} records (${percent(count,r.total)})`} onMouseEnter={()=>setInspected({language:language(r.d),level:label,count,total:r.total})} onFocus={()=>setInspected({language:language(r.d),level:label,count,total:r.total})} onClick={()=>{setFocus(focus===key?'':key);setInspected({language:language(r.d),level:label,count,total:r.total});}}/>;})}{!r.total&&<span className="chart-no-data">No sources</span>}{r.total>0&&!r.known&&<span className="chart-no-data">Not published</span>}</div><strong className="bar-total">{!r.total||(!r.known&&focus!=="unreported")?"—":focus?(scale==='share'?percent(r.counts[focus]||0,r.total):compact(r.counts[focus]||0)):scale==='share'?(r.total?'100%':'—'):compact(r.total)}</strong></div>)}
    <div className="domain-legend quality-legend">{levels.map(([key,label,color])=><button key={key} aria-pressed={focus===key} className={focus===key?'selected':''} onClick={()=>{setFocus(focus===key?'':key);setInspected(null);}}><i style={{background:color}}/>{label}</button>)}</div>
    <div className="chart-readout" aria-live="polite">{inspected?<><strong>{inspected.language} · {inspected.level}</strong><span>{format(inspected.count)} records · {percent(inspected.count,inspected.total)} of the selected corpus</span></>:<span>Hover, focus or tap a bar to inspect its values.</span>}</div>
  </section>;
}
