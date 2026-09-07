import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ExternalLink, Info, LoaderCircle, Network, Search, X } from "lucide-react";
import TopicMap, { topicColor, type ColorBy } from "./TopicMap";
import { api, compact, format, percent, type Filters, type Source } from "./data";
import "./topics.css";

export type Topic = {id: number; name: string; keywords: {word: string; score: number}[]; records: number; fit_records: number};
export type TopicPoint = [number, number, number, number, string, string, string | null, string | null, string];
type Model = {status: string; model: string; sample_records: number; sample_sources: Record<string, number>; records: number;
  assigned: number; unassigned: number; fit_outliers: number; topics: Topic[]; method: string; per_source: number; turftopic_version: string};
type TopicView = {points: TopicPoint[]; distributions: {topic_id: number; records: number; tokens: number}[]; selected_records: number; base_records: number};

export default function Topics({filters, sources, queryActive, onTopic, onRecord}: {
  filters: Filters; sources: Source[]; queryActive: boolean; onTopic: (id?: number, name?: string) => void; onRecord: (id: number) => void;
}) {
  const [model, setModel] = useState<Model | null>(null), [data, setData] = useState<TopicView | null>(null);
  const [error, setError] = useState(""), [loading, setLoading] = useState(true), [retry, setRetry] = useState(0);
  const [colorBy, setColorBy] = useState<ColorBy>("topic"), [topicQuery, setTopicQuery] = useState("");
  const [pointLimit, setPointLimit] = useState(12);
  const rawFilters = JSON.stringify(filters);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = () => api<Model>("topics", {}, controller.signal).then(m => {
      setModel(m);
      if (m.status !== "ready") timer = setTimeout(load, 8000);
    }).catch(e => {if(e.name !== "AbortError") setError(e.message);});
    setError(""); load();
    return () => {controller.abort(); clearTimeout(timer);};
  }, [retry]);
  useEffect(() => {
    if (model?.status !== "ready") return;
    const controller = new AbortController();
    setLoading(true); setError(""); setPointLimit(12);
    api<TopicView>("topics/view", {filters: rawFilters}, controller.signal).then(setData)
      .catch(e => {if(e.name !== "AbortError") setError(e.message);})
      .finally(() => {if(!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [model?.status, rawFilters, retry]);
  const selected = model?.topics?.find(t => t.id === filters.topic_id);
  const names = useMemo(() => new Map(sources.map(s => [s.id,s.name])), [sources]);
  const topics = useMemo(() => {
    const lookup = new Map(model?.topics?.map(t => [t.id,t]) || []);
    return (data?.distributions || []).map(d => ({...lookup.get(d.topic_id), ...d,
      id: d.topic_id, name: lookup.get(d.topic_id)?.name || "No topic vector"}));
  }, [model, data]);
  const visibleTopics = topics.filter(t => `${t.name} ${t.keywords?.map(w => w.word).join(" ")}`.toLocaleLowerCase("da").includes(topicQuery.toLocaleLowerCase("da")));
  if (error) return <section className="panel topic-state" role="alert"><Info size={24}/><h2>Topics could not load</h2><p>{error}</p><button className="button" onClick={() => setRetry(r => r+1)}>Try again</button></section>;
  if (!model || model.status !== "ready") return <section className="panel topic-state"><LoaderCircle className="spin" size={26}/><h2>Preparing the topic landscape</h2><p>Turftopic will appear here when its model and full-corpus assignments are ready.</p></section>;
  return <div className="topics-view" aria-busy={loading}>
    <div className="topic-intro">
      <span className="topic-model-tag"><Network size={14}/> TURFTOPIC <span>BETA</span></span>
      <p><strong>{model.topics.length} discovered topics.</strong> One map to explore them.</p>
      <a href="#topic-method" onClick={e => {e.preventDefault(); const details = document.getElementById("topic-method") as HTMLDetailsElement; details.open = true; details.scrollIntoView({block:"start",behavior:"instant"});}}>How this map is made <Info size={13}/></a>
    </div>
    <div className={`topic-layout ${loading ? "topic-updating" : ""}`}>
      <section className="panel topic-map-panel">
        <div className="panel-heading">
          <div><h2>The topic landscape {loading && <LoaderCircle className="spin" size={14}/>}</h2><p>{format(data?.points.length)} of {format(model.sample_records)} map records · current filters</p></div>
          <label className="map-color-label">Colour by <select aria-label="Map colour by" value={colorBy} onChange={e => setColorBy(e.target.value as ColorBy)}>
            <option value="topic">Topic</option><option value="domain">Domain</option><option value="quality">Content quality</option><option value="pii">PII detection</option>
          </select></label>
        </div>
        <TopicMap points={data?.points || []} topics={model.topics} colorBy={colorBy} onRecord={onRecord}/>
        <div className="topic-map-caption"><Info size={14}/><p><strong>A map sample, with full-corpus exploration.</strong> Dots show a source-balanced subset; their density does not represent topic sizes. Nearby texts have similar word vectors. Select a topic to browse all its records below.</p></div>
      </section>
      <section className="panel topic-distribution">
        <div className="panel-heading"><div><h2>Topics in the corpus</h2><p>Full-corpus counts · click to filter</p></div></div>
        <div className="topic-list-search"><Search size={14}/><input aria-label="Find a topic" value={topicQuery} onChange={e => setTopicQuery(e.target.value)} placeholder="Find a topic or keyword…"/>{topicQuery && <button aria-label="Clear topic search" onClick={() => setTopicQuery("")}><X size={13}/></button>}</div>
        <button className={`all-topics ${filters.topic_id === undefined ? "selected" : ""}`} onClick={() => onTopic()} aria-pressed={filters.topic_id === undefined}><span>All topics</span><strong>{compact(data?.base_records)}</strong></button>
        <div className="topic-list" aria-label="Topic distribution">
          {visibleTopics.map(t => <button key={t.id} className={`topic-row ${filters.topic_id === t.id ? "selected" : ""}`}
            aria-label={`Select topic: ${t.name}`} aria-pressed={filters.topic_id === t.id}
            onClick={() => onTopic(filters.topic_id === t.id ? undefined : t.id, filters.topic_id === t.id ? undefined : t.name)}>
            <span className="topic-row-top"><i style={{background:topicColor(t.id)}}/><span>{t.name}</span><strong title={`${format(t.records)} records`}>{compact(t.records)}</strong></span>
            <span className="topic-bar-track"><i style={{background:topicColor(t.id),width: `${100*t.records/Math.max(topics[0]?.records || 1,1)}%`}}/></span>
            <span className="topic-share">{percent(t.records,data?.base_records || 0)} of selection</span>
          </button>)}
          {!visibleTopics.length && <p className="topic-no-match">No matching topics. Try another keyword or clear your filters.</p>}
        </div>
        <div className="topic-list-foot">Counts follow the sidebar filters. All topics remain listed when one is selected.</div>
      </section>
    </div>
    <section className="panel topic-details">
      <div className="topic-detail-heading"><span className="topic-detail-icon" style={{color: selected ? topicColor(selected.id) : undefined}}><Network size={21}/></span>
        <div><span className="topic-kicker">{selected ? `TOPIC ${selected.id} · AUTOMATIC KEYWORDS` : filters.topic_id === -1 ? "UNASSIGNED RECORDS" : "FOLLOW A THREAD"}</span>
          <h2>{selected?.name || (filters.topic_id === -1 ? "No usable document vector" : "What connects these texts?")}</h2>
          <p>{selected ? `${format(data?.selected_records)} records in your current selection. These keywords describe the learned topic; they are not search terms.` : filters.topic_id === -1 ? "These records remain available in browsing and text search, but could not be placed on the topic map." : "Choose a topic to reveal its keywords and explore every matching record, including those outside the map sample."}</p>
        </div>
        {filters.topic_id !== undefined && <button className="text-button" onClick={() => onTopic()}>Clear topic <X size={13}/></button>}
      </div>
      {selected && <div className="topic-keywords" aria-label="Topic keywords">{selected.keywords.map((w,i) => <span key={w.word}><small>{String(i+1).padStart(2,"0")}</small>{w.word}</span>)}</div>}
      {queryActive && <p className="topic-query-note">Your search narrows the record browser below. The map and topic counts describe the metadata and topic filters.</p>}
    </section>
    <details className="panel mapped-records">
      <summary>Read the mapped records <span>{format(data?.points.length)} in this selection · keyboard accessible</span></summary>
      <div className="mapped-record-list">{data?.points.slice(0,pointLimit).map(p => <button key={p[0]} onClick={() => onRecord(p[0])}><span><small>{names.get(p[4]) || p[4]} · {p[5]}</small><span>{p[8] || `Record ${p[0]}`}</span></span><ArrowRight size={15}/></button>)}</div>
      {(data?.points.length || 0) > pointLimit && <button className="text-button mapped-more" onClick={() => setPointLimit(n => n+30)}>Show more mapped records</button>}
      {!data?.points.length && <p className="topic-no-match">No sample points match. The full record browser remains available below.</p>}
    </details>
    <details className="topic-method" id="topic-method"><summary>About the model & coverage <span>Turftopic {model.turftopic_version} · reproducible, seed 42</span></summary>
      <div><p><strong>Model:</strong> Top2Vec with Danish fastText document vectors, UMAP and HDBSCAN. Fitted on {format(model.sample_records)} records: up to {model.per_source} per source, sampled without replacement. The 2D map uses a separate UMAP projection; its axes have no physical meaning, and distances are approximate.</p>
        <p><strong>Full-corpus assignment:</strong> {format(model.assigned)} of {format(model.records)} records assigned to their nearest learned topic centroid. The {format(model.unassigned)} records without a usable vector are unassigned and remain browsable and text-searchable. Every assigned record has one approximate topic, including {format(model.fit_outliers)} training records originally treated as clustering outliers.</p>
        <p><strong>Interpretation:</strong> These are automatically discovered patterns, not verified subjects or dataset annotations. The word-vector baseline may group writing styles, OCR artefacts, or source conventions. Keywords use Turftopic’s c-TF-IDF to find distinctive words in up to 6,000 characters per sampled original; document vectors cover the full text. The map overrepresents small sources to keep them visible.</p>
        <a href="https://x-tabdeveloping.github.io/turftopic/tutorials/arxiv_ml/" target="_blank" rel="noreferrer">Inspired by the Turftopic ArXiv tutorial <ExternalLink size={13}/></a>
      </div>
    </details>
  </div>;
}
