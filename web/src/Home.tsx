import { ArrowRight, ArrowUpRight } from "lucide-react";
import { compact, format } from "./data";
import { language, type Catalog } from "./catalog";
import ContextHelp from "./ContextHelp";

export default function Home({catalog}: {catalog:Catalog}) {
  const tokens=catalog.datasets.reduce((sum,d)=>sum+d.tokens,0),sources=catalog.datasets.reduce((sum,d)=>sum+d.sources.length,0);
  return <main className="landing">
    <section className="intro-block">
      <p className="section-label">SCANDINAVIAN DYNAWORD</p>
      <h1>Open language data.<br/>Continuously developed.</h1>
      <p className="intro-copy">Danish, Swedish, Norwegian, Icelandic and Faroese text collections, brought together through a shared approach to documentation, licensing and ongoing improvement.</p>
      <div className="intro-actions"><a className="button" href="#compare">Compare the corpora <ArrowRight size={16}/></a><a className="quiet-link" href="#records">Explore records <ArrowRight size={15}/></a></div>
      <dl className="headline-numbers"><div><dt>Languages</dt><dd>5</dd></div><div><dt>Tokens <ContextHelp label="About token counts">Published counts use the Llama 3 tokenizer. These totals describe the releases listed below; they are not the number of words or unique documents.</ContextHelp></dt><dd>{compact(tokens)}</dd></div><div><dt>Source collections</dt><dd>{format(sources)}</dd></div></dl>
    </section>
    <section className="corpus-directory" aria-labelledby="collections-heading">
      <div className="section-heading"><div><p className="section-label">THE COLLECTIONS</p><h2 id="collections-heading">Five languages. A shared methodology.</h2></div><a className="quiet-link" href="#compare">Compare domains <ArrowRight size={15}/></a></div>
      <div className="directory-scroll"><table className="directory-table"><thead><tr><th>Language</th><th>Version</th><th>Records <ContextHelp label="About record counts">A record may be a document, paragraph or transcript segment, depending on the source. Use token counts to compare text volume across languages.</ContextHelp></th><th>Tokens</th><th>Sources</th><th>Dataset</th></tr></thead><tbody>{catalog.datasets.map(d=><tr key={d.id}><th scope="row"><a href={`#compare?language=${d.id}`}>{language(d)} <ArrowRight size={14}/></a></th><td>{d.version}</td><td title={format(d.records)}>{compact(d.records)}</td><td title={format(d.tokens)}>{compact(d.tokens)}</td><td>{d.sources.length}</td><td><a className="dataset-card-link" href={d.url} target="_blank" rel="noreferrer" aria-label={`${language(d)} dataset card`}>Dataset card <ArrowUpRight size={13}/></a></td></tr>)}</tbody></table></div>
      <p className="data-date">Published release statistics checked {new Date(catalog.generated_at).toLocaleDateString("en-GB",{day:"numeric",month:"long",year:"numeric"})}. Source licences and release details are documented in each dataset card.</p>
    </section>
    <section className="method-intro"><div><p className="section-label">WHY DYNAWORD?</p><h2>Data that can keep improving.</h2><p>Useful language data is spread across repositories, formats and institutions. Dynaword provides a way to collect it transparently, document its origins and keep extending it as new sources become available.</p><a className="quiet-link" href="https://arxiv.org/abs/2508.02271" target="_blank" rel="noreferrer">Read the original Dynaword paper <ArrowUpRight size={15}/></a></div><ol className="principles"><li><span>01</span><div><h3>Traceable licensing</h3><p>Keep each source’s licence and provenance available.</p></div></li><li><span>02</span><div><h3>Reproducible collection</h3><p>Document how a comparable corpus can be rebuilt.</p></div></li><li><span>03</span><div><h3>Clear documentation</h3><p>Describe sources, processing and the limits of the data.</p></div></li><li><span>04</span><div><h3>Continuous development</h3><p>Make it possible to add sources and improve future releases.</p></div></li></ol></section>
    <section className="annotation-intro"><div><p className="section-label">EXPLORING THE DATA</p><h2>Inspect the records behind the numbers.</h2><p>Compare domains across languages, then use the record explorer to combine source, length and annotation filters. Open the original text and save records for review.</p></div><div className="annotation-note"><h3>Machine-generated annotations</h3><p>Propella provides document-level labels such as content quality, content type and possible personal information.</p><a className="quiet-link" href="#records">Open the record explorer <ArrowRight size={15}/></a></div></section>
  </main>;
}
