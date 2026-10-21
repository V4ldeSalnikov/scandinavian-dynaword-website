import {useEffect,useState} from 'react';
import type {Corpus} from './catalog';
import {language} from './catalog';
import {format,compact,percent,label} from './data';
const qualityLevels=[['unacceptable','Unacceptable','#b7192d'],['poor','Poor','#d76a78'],['adequate','Adequate','#d5b560'],['good','Good','#67a599'],['excellent','Excellent','#24685c'],['unreported','Unreported','#e6e8ec']];
export default function QualityComparison({datasets,domain}:{datasets:Corpus[];domain:string}) {
  const [field,setField]=useState('content_quality');
  const names:Record<string,string>={content_quality:'Content quality',pii_presence:'PII detection',content_integrity:'Content integrity',content_ratio:'Content ratio',content_length:'Content length',information_density:'Information density',educational_value:'Educational value',reasoning_indicators:'Reasoning indicators',content_safety:'Content safety'};
  const colors=['#b7192d','#d76a78','#d5b560','#67a599','#24685c','#87779c'];
  const categories=[...new Set(datasets.flatMap(d=>Object.keys(d.annotation_distributions?.[field]||{})))];
  const levels=field==='content_quality'?qualityLevels:[...categories.map((key,i)=>[key,label(key),colors[i%colors.length]]),['unreported','Unreported','#e6e8ec']];
  const [scale,setScale]=useState('share'),[focus,setFocus]=useState(''),[inspected,setInspected]=useState<{language:string;level:string;count:number;total:number}|null>(null);
  const languageKey=datasets.map(d=>d.id).join(",");
  useEffect(()=>setInspected(null),[domain,languageKey]);
  const rows=datasets.map(d=>{
    const sources=d.sources.filter(s=>!domain||s.domain===domain);
    const total=domain?sources.reduce((n,s)=>n+s.records,0):d.records;
    const quality=domain?sources.reduce<Record<string,number>>((all,s)=>{for(const [key,n] of Object.entries(s.annotation_distributions?.[field]||{}))all[key]=(all[key]||0)+n;return all;},{}):(d.annotation_distributions?.[field]||{});
    const known=Object.values(quality).reduce((n,x)=>n+x,0);
    return {d,total,known,counts:{...quality,unreported:total-known} as Record<string,number>};
  });
  const max=Math.max(1,...rows.map(r=>focus?(r.counts[focus]||0):r.total));
  return <section className="quality-comparison" aria-label="Annotation comparison">
    <div className="section-heading"><h2>Annotations</h2><div className="annotation-comparison-controls"><select aria-label="Comparison annotation" value={field} onChange={e=>{setField(e.target.value);setFocus('');setInspected(null);}}>{Object.entries(names).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select><select aria-label="Annotation comparison scale" value={scale} onChange={e=>setScale(e.target.value)}><option value="share">Share of records</option><option value="count">Record count</option></select></div></div>
    <div className="chart-focus-line"><span>{domain?`${domain} sources`:'All domains'} · {focus?levels.find(l=>l[0]===focus)?.[1]:names[field]}</span>{focus?<button className="text-button" onClick={()=>{setFocus('');setInspected(null);}}>Show all categories</button>:<span>Tap a colour to compare that category</span>}</div>
    {rows.map(r=><div className="comparison-bar-row" key={r.d.id}><div className="bar-language"><strong>{language(r.d)}</strong></div><div className="comparison-bar-track">{levels.filter(l=>!focus||l[0]===focus).map(([key,label,color])=>{const count=r.counts[key]||0;return count>0&&<button key={key} style={{width:`${100*count/(scale==='share'?(r.total||1):max)}%`,background:color}} aria-label={`${language(r.d)}, ${label}: ${format(count)} records (${percent(count,r.total)}). Compare category.`} title={`${label}: ${format(count)} records (${percent(count,r.total)})`} onMouseEnter={()=>setInspected({language:language(r.d),level:label,count,total:r.total})} onFocus={()=>setInspected({language:language(r.d),level:label,count,total:r.total})} onClick={()=>{setFocus(focus===key?'':key);setInspected({language:language(r.d),level:label,count,total:r.total});}}/>;})}{!r.total&&<span className="chart-no-data">No sources</span>}{r.total>0&&!r.known&&<span className="chart-no-data">Not published</span>}</div><strong className="bar-total">{!r.total||(!r.known&&focus!=="unreported")?"—":focus?(scale==='share'?percent(r.counts[focus]||0,r.total):compact(r.counts[focus]||0)):scale==='share'?(r.total?'100%':'—'):compact(r.total)}</strong></div>)}
    <div className="domain-legend quality-legend">{levels.map(([key,label,color])=><button key={key} aria-pressed={focus===key} className={focus===key?'selected':''} onClick={()=>{setFocus(focus===key?'':key);setInspected(null);}}><i style={{background:color}}/>{label}</button>)}</div>
    <div className="chart-readout" aria-live="polite">{inspected?<><strong>{inspected.language} · {inspected.level}</strong><span>{format(inspected.count)} records · {percent(inspected.count,inspected.total)} of the selected corpus</span></>:<span>Hover, focus or tap a bar to inspect its values.</span>}</div>
  </section>;
}
