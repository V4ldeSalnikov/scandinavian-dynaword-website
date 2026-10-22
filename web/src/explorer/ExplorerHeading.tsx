import {Database, Filter} from 'lucide-react';
export type ExplorerView='records'|'statistics'|'sources';
const flags:Record<string,{name:string;background:string;cross:string;inner?:string}>={
 danish:{name:'Denmark',background:'#c8102e',cross:'#fff'},
 norwegian:{name:'Norway',background:'#ba0c2f',cross:'#fff',inner:'#00205b'},
 swedish:{name:'Sweden',background:'#006aa7',cross:'#fecc00'},
 icelandic:{name:'Iceland',background:'#02529c',cross:'#fff',inner:'#dc1e35'},
 faroese:{name:'Faroe Islands',background:'#fff',cross:'#0065bd',inner:'#ed2939'},
};
export function CountryFlag({language}:{language:string}) {
 const flag=flags[language];if(!flag)return null;
 return <svg className="country-flag" viewBox="0 0 28 20" role="img" aria-label={`${flag.name} flag`}><rect width="28" height="20" fill={flag.background}/><path d="M9 0v20M0 10h28" stroke={flag.cross} strokeWidth={flag.inner?6:3}/>{flag.inner&&<path d="M9 0v20M0 10h28" stroke={flag.inner} strokeWidth="3"/>}</svg>;
}
export function ExplorerHeading({language,version,view,onView,onOpenFilters}:{language:string;version?:string;view:ExplorerView;onView:(view:ExplorerView)=>void;onOpenFilters:()=>void}) {
 return <><div className="page-eyebrow"><button className="mobile-only icon-button" aria-label="Open filters" onClick={onOpenFilters}><Filter size={18}/></button><Database size={13}/> {language.toUpperCase()} / RECORD EXPLORER <span className="revision">{version?`Version ${version.replace(/^v/,'')}`:'Connecting'}</span></div><div className="page-title"><div><h1>{view==='sources'?`Sources in ${language} Dynaword`:view==='records'?`Explore ${language} records`:'Understand your selection'}</h1><p>{view==='sources'?`The collections that make up ${language} Dynaword.`:view==='records'?'Filter by source, length and machine-generated labels.':`Explore the texts, sources, and signals behind ${language} Dynaword.`}</p></div></div><nav className="explorer-tabs" aria-label={`${language} explorer views`}>{([['records','Records'],['statistics','Selection statistics'],['sources','Source details']] as const).map(([key,title])=><button key={key} className={view===key?'active':''} aria-current={view===key?'page':undefined} onClick={()=>onView(key)}>{title}</button>)}</nav></>;
}
