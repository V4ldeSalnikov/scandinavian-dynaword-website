import {ArrowUpRight} from 'lucide-react';
import {COLORS,format,label} from '../data';
export function RecordTableHead(){
 return <thead><tr><th>TEXT / RECORD</th><th>SOURCE</th><th>TOKENS</th><th>QUALITY</th><th>PII</th><th/></tr></thead>;
}
export function RecordMetadataCells({row,sourceName}:{row:{source:string;domain:string;token_count:number;content_quality?:unknown;pii_presence?:unknown};sourceName?:string}){
 const quality=typeof row.content_quality==='string'?row.content_quality:'';
 const pii=typeof row.pii_presence==='string'?row.pii_presence:'';
 return <><td><span className="domain-dot" style={{background:COLORS[row.domain]}}/>{sourceName||row.source}</td><td className="numeric">{format(row.token_count)}</td><td><span className={`quality-badge ${quality||'missing'}`}>{quality?label(quality):'No machine label'}</span></td><td><span className={`pii-dot ${pii||'missing'}`}/><span className="pii-label">{pii==='contains_pii'?'Flagged':pii==='no_pii'?'Not flagged':'Unknown'}</span></td><td><ArrowUpRight size={15}/></td></>;
}
