import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowDownUp,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  CircleHelp,
  Database,
  ExternalLink,
  FileText,
  Filter,
  Layers3,
  LoaderCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import type { EChartsOption } from "echarts";
const Chart = lazy(() => import("./Chart"));
import ContextHelp from "./ContextHelp";
import ReviewTags, { ExportReviews } from "./ReviewTags";
import {
  ANNOTATIONS,
  COLORS,
  api,
  compact,
  filterLabels,
  format,
  label,
  percent,
  type Filters,
  type Manifest,
  type RecordRow,
  type RowsResponse,
  type Source,
  type Stats,
} from "./data";

const EMPTY: Filters = {};
const fieldOrder = ["unacceptable", "poor", "adequate", "good", "excellent"];
const qualityColors: Record<string, string> = {
  unacceptable: "#bf3944",
  poor: "#cc9857",
  adequate: "#b7aca0",
  good: "#79a18e",
  excellent: "#426f5e",
  __missing__: "#d7d2d0",
  contains_pii: "#bf3944",
  no_pii: "#79a18e",
};
const tooltip = {
  trigger: "item" as const,
  renderMode: "richText" as const,
  backgroundColor: "#302728",
  borderWidth: 0,
  textStyle: { color: "#fff", fontFamily: "system-ui", fontSize: 12 },
  padding: 12,
};
const axisStyle = {
  axisLine: { show: false },
  axisTick: { show: false },
  axisLabel: { color: "#827b7a", fontFamily: "system-ui", fontSize: 11 },
  splitLine: { lineStyle: { color: "#f0eceb", type: "dashed" as const } },
};

function Explorer({initialFilters = {}, active = true}: {initialFilters?: Filters; active?: boolean}) {
  const [manifest, setManifest] = useState<Manifest | null>(null),
    [initialError, setInitialError] = useState("");
  const [filters, setFilters] = useState<Filters>(initialFilters),
    [annotation, setAnnotation] = useState("content_quality");
  const [stats, setStats] = useState<Stats | null>(null),
    [statsLoading, setStatsLoading] = useState(true),
    [statsError, setStatsError] = useState("");
  const [rows, setRows] = useState<RecordRow[]>([]),
    [rowsLoading, setRowsLoading] = useState(false),
    [rowsError, setRowsError] = useState("");
  const [hasMore, setHasMore] = useState(false),
    [nextOffset, setNextOffset] = useState(0),
    [sort, setSort] = useState("original"),
    [searchTotal, setSearchTotal] = useState<number | null>(null);
  const [query, setQuery] = useState(""),
    [searchInput, setSearchInput] = useState(""),
    [searchMode, setSearchMode] = useState("text"),
    [activeMode, setActiveMode] = useState("text"),
    [compared, setCompared] = useState(0);
  const [previews, setPreviews] = useState<
    Record<string, { text?: string; unavailable?: boolean }>
  >({});
  const [measure, setMeasure] = useState<"tokens" | "records">("tokens"),
    [composition, setComposition] = useState<"domains" | "sources">("domains");
  const [view, setView] = useState<"statistics" | "records" | "sources">("records"),
    [sourceQuery, setSourceQuery] = useState("");
  const [activeRecord, setActiveRecord] = useState<number | null>(null),
    [sidebarOpen, setSidebarOpen] = useState(false);
  const [refresh, setRefresh] = useState(0),
    [sourceDetail, setSourceDetail] = useState<Source | null>(null);
  const rowRequest = useRef<AbortController | null>(null),
    previewRequest = useRef<AbortController | null>(null);
  const [annotationValues,setAnnotationValues] = useState<Record<string,string[]>>({});
  useEffect(()=>{if(!active||manifest?.status!=="ready")return;const c=new AbortController();api<Record<string,string[]>>("annotation-values",{},c.signal).then(setAnnotationValues).catch(()=>{});return()=>c.abort();},[active,manifest?.status,refresh]);
  const filtersJSON = JSON.stringify(filters);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let interval: ReturnType<typeof setTimeout>;
    const load = () =>
      api<Manifest>("manifest", {}, AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]))
        .then((m) => {
          setManifest(m);
          setInitialError("");
          if (m.status !== "ready" || !m.search.text || !m.search.semantic)
            interval = setTimeout(load, 8000);
        })
        .catch((e) => {
          if (e.name !== "AbortError") {
            setInitialError(e.message);
            interval = setTimeout(load, 8000);
          }
        });
    load();
    return () => {
      controller.abort();
      clearTimeout(interval);
    };
  }, [refresh, active]);
  useEffect(() => {
    if (!active || manifest?.status !== "ready") return;
    const controller = new AbortController();
    setStatsLoading(true);
    setStatsError("");
    api<Stats>("stats", { filters: filtersJSON, annotation }, controller.signal)
      .then(setStats)
      .catch((e) => {
        if (e.name !== "AbortError") setStatsError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setStatsLoading(false);
      });
    return () => controller.abort();
  }, [filtersJSON, annotation, manifest?.status, refresh, active]);
  const loadRows = useCallback(
    async (offset = 0, append = false) => {
      rowRequest.current?.abort();
      previewRequest.current?.abort();
      const controller = new AbortController();
      rowRequest.current = controller;
      setRowsLoading(true);
      setRowsError("");
      try {
        const result = await api<RowsResponse>(
          query ? "search" : "rows",
          query
            ? {
                q: query,
                mode: activeMode,
                filters: filtersJSON,
                cursor: offset,
              }
            : { filters: filtersJSON, offset, limit: 30, sort },
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setRows((previous) =>
          append ? [...previous, ...result.rows] : result.rows,
        );
        setHasMore(result.has_more);
        setNextOffset(result.next_offset);
        setSearchTotal(result.upstream_matches ?? null);
        setCompared(result.compared || 0);
        const existing = Object.fromEntries(
          result.rows
            .filter((r) => r.preview)
            .map((r) => [r.record_no, { text: r.preview }]),
        );
        setPreviews((p) => ({ ...p, ...existing }));
        const missing = result.rows
          .filter((r) => !r.preview)
          .slice(0, 30)
          .map((r) => r.record_no);
        if (missing.length) {
          const pController = new AbortController();
          previewRequest.current = pController;
          api<Record<string, { text?: string; unavailable?: boolean }>>(
            "previews",
            { ids: missing.join(",") },
            pController.signal,
          )
            .then((p) => setPreviews((prev) => ({ ...prev, ...p })))
            .catch(() => {});
        }
      } catch (e: any) {
        if (e.name !== "AbortError") setRowsError(e.message);
      } finally {
        if (!controller.signal.aborted) setRowsLoading(false);
      }
    },
    [query, activeMode, filtersJSON, sort],
  );
  useEffect(() => {
    if (!active || manifest?.status !== "ready") return;
    if (view !== "records") return;
    setRows([]);
    setRowsLoading(true);
    const timer = setTimeout(
      loadRows,
      query && activeMode === "semantic" ? 300 : 0,
    );
    return () => {
      clearTimeout(timer);
      rowRequest.current?.abort();
      previewRequest.current?.abort();
    };
  }, [loadRows, manifest?.status, refresh, query, activeMode, view, active]);
  const setFilter = useCallback(
    (key: keyof Filters, value: string | number | undefined) => {
      setFilters((f) => {
        const next = { ...f };
        if (value === undefined || value === "") delete next[key];
        else (next as Record<string, unknown>)[key] = value;
        return next;
      });
    },
    [],
  );
  const reset = () => {
    setFilters(EMPTY);
    setQuery("");
    setSearchInput("");
  };
  const chips = filterLabels(filters, manifest?.sources || []);
  const selectAnnotation = useCallback(
    (value: string) => {
      setFilter(annotation as keyof Filters, value);
    },
    [annotation, setFilter],
  );
  const selectRange = useCallback(
    (start: number, end: number) => {
      const hist = stats?.histogram;
      if (hist?.[start] && hist?.[end])
        setFilters((f) => ({
          ...f,
          min_tokens: hist[start].min,
          max_tokens: hist[end].max,
        }));
    },
    [stats?.histogram],
  );
  const domains = useMemo(
    () =>
      Array.from(new Set(manifest?.sources.map((s) => s.domain) || [])).sort(),
    [manifest],
  );
  const totals = stats?.totals;
  const compositionData = useMemo(
    () =>
      [...(stats?.[composition] || [])]
        .sort((a, b) => b[measure] - a[measure])
        .slice(0, composition === "domains" ? 12 : 15),
    [stats, composition, measure],
  );
  const compositionOption = useMemo<EChartsOption>(
    () => ({
      animationDuration: 350,
      grid: {
        top: 4,
        right: 52,
        bottom: 22,
        left: composition === "sources" ? 152 : 109,
      },
      tooltip: {
        ...tooltip,
        formatter: (p: any) =>
          `${p.name}\n${format(p.value)} ${measure}\n${percent(p.value, totals?.[measure] || 0)} of current selection`,
      },
      xAxis: {
        type: "value",
        splitNumber: 3,
        ...axisStyle,
        axisLabel: {
          ...axisStyle.axisLabel,
          formatter: (v: number) => compact(v),
        },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: compositionData.map((d) =>
          composition === "sources"
            ? manifest?.sources.find((s) => s.id === d.name)?.name || d.name
            : d.name,
        ),
        ...axisStyle,
        axisLabel: {
          color: "#605656",
          fontSize: 11,
          width: composition === "sources" ? 140 : 100,
          overflow: "truncate",
        },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 17,
          data: compositionData.map((d) => ({
            value: d[measure],
            itemStyle: {
              color: COLORS[d.domain || d.name] || "#c5565e",
              borderRadius: [0, 3, 3, 0],
            },
          })),
          label: {
            show: true,
            position: "right",
            color: "#746b6a",
            fontSize: 10,
            formatter: (p: any) => compact(p.value),
          },
          emphasis: { itemStyle: { opacity: 0.78 } },
          cursor: "pointer",
        },
      ],
    }),
    [compositionData, composition, measure, totals, manifest],
  );
  const annotationData = useMemo(
    () =>
      [...(stats?.annotations || [])].sort((a, b) => {
        if (annotation === "content_quality") {
          const aIndex = fieldOrder.indexOf(a.name),
            bIndex = fieldOrder.indexOf(b.name);
          return (aIndex < 0 ? 99 : aIndex) - (bIndex < 0 ? 99 : bIndex);
        }
        return b.records - a.records;
      }),
    [stats, annotation],
  );
  const annotationOption = useMemo<EChartsOption>(
    () => ({
      animationDuration: 350,
      grid: { top: 8, right: 53, bottom: 26, left: 110 },
      tooltip: {
        ...tooltip,
        formatter: (p: any) =>
          `${label(p.name)}\n${format(p.value)} records\n${percent(p.value, totals?.records || 0)} of current selection`,
      },
      xAxis: {
        type: "value",
        splitNumber: 3,
        ...axisStyle,
        axisLabel: {
          ...axisStyle.axisLabel,
          formatter: (v: number) => compact(v),
        },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: annotationData.map((d) => d.name),
        ...axisStyle,
        axisLabel: {
          color: "#605656",
          fontSize: 11,
          width: 98,
          overflow: "truncate",
          formatter: (v: string) => label(v),
        },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 26,
          data: annotationData.map((d) => ({
            value: d.records,
            itemStyle: {
              color: qualityColors[d.name] || "#bf7176",
              borderRadius: [0, 3, 3, 0],
            },
          })),
          label: {
            show: true,
            position: "right",
            formatter: (p: any) => percent(p.value, totals?.records || 0),
            color: "#7a716f",
            fontSize: 10,
          },
          cursor: "pointer",
        },
      ],
    }),
    [annotationData, totals, annotation],
  );
  const histogramOption = useMemo<EChartsOption>(
    () => ({
      animationDuration: 250,
      grid: { left: 47, right: 18, top: 15, bottom: 30 },
      tooltip: {
        ...tooltip,
        formatter: (p: any) => {
          const b = stats?.histogram[p.dataIndex];
          return b
            ? `${format(b.min)}–${format(b.max)} tokens\n${format(b.records)} records\n${percent(b.records, totals?.records || 0)} of current selection`
            : "";
        },
      },
      brush: {
        toolbox: [],
        xAxisIndex: 0,
        brushMode: "single",
        brushStyle: {
          color: "rgba(181,18,27,.12)",
          borderColor: "#b5121b",
          borderWidth: 1,
        },
      },
      xAxis: {
        type: "category",
        data: stats?.histogram.map((b) => (b.min === 0 ? "0" : compact(b.min))),
        ...axisStyle,
        axisLabel: { ...axisStyle.axisLabel, interval: 2 },
      },
      yAxis: {
        type: "value",
        splitNumber: 3,
        ...axisStyle,
        axisLabel: {
          ...axisStyle.axisLabel,
          formatter: (v: number) => compact(v),
        },
      },
      series: [
        {
          type: "bar",
          data: stats?.histogram.map((b) => b.records),
          barCategoryGap: "18%",
          itemStyle: { color: "#c5565e", borderRadius: [3, 3, 0, 0] },
          emphasis: { itemStyle: { color: "#b5121b" } },
        },
      ],
    }),
    [stats?.histogram, totals],
  );

  return (
    <div className="explorer">
      <div className="workspace">
        <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
          <div className="sidebar-head">
            <span>
              <SlidersHorizontal size={16} /> Filter corpus
            </span>
            <button
              className="icon-button"
              title="Reset filters"
              aria-label="Reset filters"
              onClick={reset}
            >
              <RefreshCw size={14} />
            </button>
            <button
              className="icon-button mobile-only"
              aria-label="Close filters"
              onClick={() => setSidebarOpen(false)}
            >
              <X size={16} />
            </button>
          </div>
          <div className="dataset-selector">
            <span className="danish-flag" />
            <div>
              <strong>Danish Dynaword</strong>

            </div>
          </div>
          <label className="filter-label" htmlFor="domain">
            DOMAIN
          </label>
          <select
            id="domain"
            value={filters.domain || ""}
            onChange={(e) => setFilter("domain", e.target.value)}
          >
            <option value="">All domains</option>
            {domains.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
          <div className="filter-label source-label">
            <span>DATA SOURCES</span>
            <span>{manifest?.sources.length || "—"}</span>
          </div>
          <div className="input-search small">
            <Search size={14} />
            <input
              aria-label="Find a source"
              placeholder="Find a source…"
              value={sourceQuery}
              onChange={(e) => setSourceQuery(e.target.value)}
            />
          </div>
          <div className="source-list">
            <button
              className={`source-option ${!filters.source ? "selected" : ""}`}
              onClick={() => setFilter("source", undefined)}
            >
              <span className="radio" />
              All sources<span>{compact(manifest?.records)}</span>
            </button>
            {manifest?.sources
              .filter(
                (s) =>
                  (!filters.domain || s.domain === filters.domain) &&
                  (s.name + " " + s.id)
                    .toLowerCase()
                    .includes(sourceQuery.toLowerCase()),
              )
              .map((s) => (
                <button
                  key={s.id}
                  title={`${s.name} · ${format(s.records)} records`}
                  className={`source-option ${filters.source === s.id ? "selected" : ""}`}
                  onClick={() =>
                    setFilter(
                      "source",
                      filters.source === s.id ? undefined : s.id,
                    )
                  }
                >
                  <span className="radio" />
                  <span className="source-name">{s.name}</span>
                  <span>{compact(s.records)}</span>
                </button>
              ))}
          </div>
          <div className="filter-divider" />
          <label className="filter-label" htmlFor="annotation-field">ANNOTATIONS</label>
          <select id="annotation-field" aria-label="Annotation field" value={annotation} onChange={e=>setAnnotation(e.target.value)}>{Object.entries(ANNOTATIONS).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select>
          <select aria-label="Annotation value" value={String(filters[annotation as keyof Filters]||'')} onChange={e=>setFilter(annotation as keyof Filters,e.target.value)}><option value="">All values</option>{(annotationValues[annotation]||[]).map(v=><option key={v} value={v}>{label(v)}</option>)}<option value="__missing__">No machine label</option></select>
          <div className="filter-label">
            DOCUMENT LENGTH <span>tokens</span>
          </div>
          <div className="range-inputs">
            <input
              type="number"
              min="0"
              aria-label="Minimum tokens"
              placeholder="Min"
              value={filters.min_tokens ?? ""}
              onChange={(e) =>
                setFilter(
                  "min_tokens",
                  e.target.value ? Number(e.target.value) : undefined,
                )
              }
            />
            <span>–</span>
            <input
              type="number"
              min="0"
              aria-label="Maximum tokens"
              placeholder="Max"
              value={filters.max_tokens ?? ""}
              onChange={(e) =>
                setFilter(
                  "max_tokens",
                  e.target.value ? Number(e.target.value) : undefined,
                )
              }
            />
          </div>
        </aside>
        <main>
          <div className="page-eyebrow">
            <button
              className="mobile-only icon-button"
              aria-label="Open filters"
              onClick={() => setSidebarOpen(true)}
            >
              <Filter size={18} />
            </button>
            <Database size={13} /> DANISH / RECORD EXPLORER{" "}
            <span className="revision">
              {manifest?.revision
                ? "Version 1.2.23"
                : "CONNECTING"}
            </span>
          </div>
          <div className="page-title">
            <div>
              <h1>
                {view === "sources"
                  ? "Sources in Danish Dynaword"

                  : view === "records"
                    ? "Explore Danish records"
                    : "Understand your selection"}
              </h1>
              <p>
                {view === "sources"
                  ? "The collections that make up Danish Dynaword."

                  : view === "records"
                    ? "Filter by source, length and machine-generated labels."
                    : "Explore the texts, sources, and signals behind Danish Dynaword."}
              </p>
            </div>

          </div>
          <div className="explorer-tabs" aria-label="Danish explorer views">
            <button className={view === "records" ? "active" : ""} onClick={() => setView("records")}>Records</button>
            <button className={view === "statistics" ? "active" : ""} onClick={() => setView("statistics")}>Selection statistics</button>
            <button className={view === "sources" ? "active" : ""} onClick={() => setView("sources")}>Source details</button>
          </div>
          <p className="index-scope">Full-corpus search covers Danish v1.2.23. <a href="#compare">Compare the latest releases in all five languages →</a></p>
          {!manifest || manifest.status !== "ready" ? (
            <div className="preparing">
              {initialError ? <CircleHelp size={28} /> : <LoaderCircle className="spin" size={28} />}
              <h2>{initialError ? "Waiting for the data service" : manifest ? "Preparing the complete corpus" : "Connecting to the corpus"}</h2>
              <p>
                {initialError
                  ? "The backend may be waking after inactivity or temporarily unavailable. We’ll retry automatically every few seconds."
                  : manifest
                    ? `${manifest.sources.length} of 50 sources indexed. The explorer will appear when all records are ready.`
                    : "Loading the complete Danish dataset. The first connection can take longer after inactivity."}
              </p>
              <button
                className="button"
                onClick={() => setRefresh((r) => r + 1)}
              >
                Retry connection
              </button>
            </div>
          ) : (
            <>
              {view === "statistics" && <section
                className="metrics"
                aria-label="Selection statistics"
                aria-busy={statsLoading}
              >
                <Metric
                  icon={<FileText size={16} />}
                  title="RECORDS"
                  value={compact(totals?.records)}
                  detail={
                    chips.length
                      ? "in your selection"
                      : "across the complete corpus"
                  }
                />
                <Metric
                  icon={<Layers3 size={16} />}
                  title="TOKENS"
                  value={compact(totals?.tokens)}
                  detail="Llama 3 tokenizer"
                />
                <Metric
                  icon={<Database size={16} />}
                  title="SOURCES"
                  value={String(totals?.sources ?? "—")}
                  detail={
                    chips.length ? "in your selection" : "distinct collections"
                  }
                />
                <Metric
                  icon={<FileText size={16} />}
                  title="MACHINE LABELS"
                  value={percent(totals?.annotated || 0, totals?.records || 0)}
                  detail={`${compact(totals?.annotated)} of ${compact(totals?.records)} have automated quality labels`}
                />
              </section>}
              {view === "records" && <>
              <form
                className="search-bar"
                onSubmit={(e) => {
                  e.preventDefault();
                  setQuery(searchInput.trim());
                  setActiveMode(searchMode);
                }}
              >
                <Search size={19} />
                <input
                  aria-label="Search the complete corpus"
                  placeholder={
                    searchMode === "semantic"
                      ? "Describe a topic in Danish, e.g. vedvarende energi…"
                      : "Find words or phrases in the original Danish texts…"
                  }
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                />
                <select
                  aria-label="Search mode"
                  value={searchMode}
                  onChange={(e) => setSearchMode(e.target.value)}
                >
                  <option value="text">Text search</option>
                  <option value="semantic" disabled={!manifest.search.semantic}>
                    {manifest.search.semantic
                      ? "Semantic · beta"
                      : "Semantic · preparing"}
                  </option>
                </select>
                <button
                  type="submit"
                  disabled={searchInput.trim().length === 1}
                >
                  Search <ArrowRight size={15} />
                </button>
              </form>
              <ExportReviews />
              <div className="search-explainer"><ContextHelp label="How search works">Text search uses a full-text BM25 index. Semantic search uses Danish word embeddings and an approximate vector index, then reranks matching candidates. It can miss relevant results, particularly for rare words and historical spelling. Both modes respect your filters.</ContextHelp><span>{searchMode === "text" ? "Find words and phrases in the original texts." : "Search by meaning · approximate results · Danish word-vector baseline"}</span></div>
              </>}
              <div className="selection-bar">
                <span>
                  <Filter size={13} />
                  {chips.length
                    ? `${chips.length} active filter${chips.length === 1 ? "" : "s"}`
                    : "All records selected"}
                </span>
                <div className="filter-chips">
                  {chips.map((chip) => (
                    <button
                      key={chip.key}
                      onClick={() => {
                        if (chip.key === "annotation_value")
                          setFilters((f) => {
                            const next = { ...f };
                            delete next.annotation_key;
                            delete next.annotation_value;
                            return next;
                          });
                        else setFilter(chip.key as keyof Filters, undefined);
                      }}
                    >
                      {chip.label}
                      <X size={11} />
                    </button>
                  ))}
                  {query && (
                    <button
                      onClick={() => {
                        setQuery("");
                        setSearchInput("");
                      }}
                    >
                      Search: {query}
                      <X size={11} />
                    </button>
                  )}
                </div>
                {(chips.length > 0 || query) && (
                  <button className="text-button" onClick={reset}>
                    Clear all
                  </button>
                )}
                {statsLoading && <LoaderCircle size={14} className="spin" />}
              </div>
              {statsError && (
                <ErrorBox
                  message={statsError}
                  retry={() => setRefresh((r) => r + 1)}
                />
              )}
              {view === "statistics" && (
                <Suspense fallback={<div className="loading-rows">Loading selection charts…</div>}>
                  <div
                    className={`chart-grid ${statsLoading ? "updating" : ""}`}
                  >
                    <section className="panel composition">
                      <div className="panel-heading">
                        <div>
                          <h2>Corpus composition <ContextHelp label="About domains and sources">Domains describe the source collection. They are separate from a document’s predicted content type. Counts here are computed from every record matching your filters.</ContextHelp></h2>

                        </div>
                        <div className="segmented" aria-label="Chart measure">
                          <button
                            className={measure === "tokens" ? "active" : ""}
                            onClick={() => setMeasure("tokens")}
                          >
                            Tokens
                          </button>
                          <button
                            className={measure === "records" ? "active" : ""}
                            onClick={() => setMeasure("records")}
                          >
                            Records
                          </button>
                        </div>
                      </div>
                      <div className="chart-tabs">
                        <button
                          className={composition === "domains" ? "active" : ""}
                          onClick={() => setComposition("domains")}
                        >
                          By domain
                        </button>
                        <button
                          className={composition === "sources" ? "active" : ""}
                          onClick={() => setComposition("sources")}
                        >
                          By source
                        </button>
                        <span>
                          Click a bar to explore <ArrowDown size={11} />
                        </span>
                      </div>
                      <Chart
                        height={composition === "domains" ? 306 : 358}
                        option={compositionOption}
                        ariaLabel={`Corpus composition by ${composition}. Use the domain or source filters for keyboard selection.`}
                        onSelect={(_, i) =>
                          setFilter(
                            composition === "domains" ? "domain" : "source",
                            compositionData[i]?.name,
                          )
                        }
                      />
                      <ChartTable
                        caption="Composition values"
                        entries={compositionData.map((d) => ({
                          name:
                            composition === "sources"
                              ? manifest.sources.find((s) => s.id === d.name)
                                  ?.name || d.name
                              : d.name,
                          value: d[measure],
                        }))}
                        total={totals?.[measure] || 0}
                        unit={measure}
                      />
                      <div className="panel-foot">
                        <span>
                          {composition === "sources"
                            ? "Largest 15 sources in this selection"
                            : "Share of the current selection"}
                        </span>
                        <span>
                          {format(totals?.[measure])} {measure}
                        </span>
                      </div>
                    </section>
                    <section className="panel annotations">
                      <div className="panel-heading">
                        <div>
                          <h2>Annotations <ContextHelp label="About automated labels">These are model-generated assessments, not human annotations. Coverage means a field has a machine label; it does not measure accuracy. A filtered selection may have 100% coverage simply because you selected records with a label.</ContextHelp></h2>

                        </div>
                        <span className="tiny-badge">AUTOMATED</span>
                      </div>
                      <select
                        className="annotation-select"
                        aria-label="Annotation to visualise"
                        value={annotation}
                        onChange={(e) => setAnnotation(e.target.value)}
                      >
                        {Object.entries(ANNOTATIONS).map(([k, v]) => (
                          <option value={k} key={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                      <Chart
                        height={Math.max(267, annotationData.length * 26 + 40)}
                        option={annotationOption}
                        ariaLabel={`${ANNOTATIONS[annotation]} distribution. Use the annotation category selector below for keyboard selection.`}
                        onSelect={(name) => selectAnnotation(name)}
                      />
                      <ChartTable
                        caption="Annotation values"
                        entries={annotationData.map((d) => ({
                          name: label(d.name),
                          value: d.records,
                        }))}
                        total={totals?.records || 0}
                        unit="records"
                      />
                      <div className="annotation-tools">
                        <select
                          aria-label="Filter by chart annotation category"
                          value={String(filters[annotation as keyof Filters]||'')}
                          onChange={e=>selectAnnotation(e.target.value)}
                        >
                          <option value="">Select a category to filter</option>
                          {annotationData.map((d) => (
                            <option key={d.name} value={d.name}>
                              {label(d.name)}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="panel-foot">
                        <span>
                          {percent(
                            stats?.annotation_covered || 0,
                            totals?.records || 0,
                          )}{" "}
                          machine-label coverage
                        </span>
                        <span>
                          {annotation === "content_type"
                            ? "Multiple labels per record"
                            : "Missing values shown separately"}
                        </span>
                      </div>
                    </section>
                  </div>
                  <section
                    className={`panel lengths ${statsLoading ? "updating" : ""}`}
                  >
                    <div className="panel-heading">
                      <div>
                        <h2>Document lengths <ContextHelp label="About document lengths">Lengths use the corpus’s recorded Llama 3 token counts. Drag to select a range, or enter bounds in the sidebar. Very long documents share wider bins.</ContextHelp></h2>
                        <p>Drag across the chart to select a token range</p>
                      </div>
                      <span className="subtle-label">
                        DOUBLING TOKEN INTERVALS
                      </span>
                    </div>
                    <Chart
                      height={178}
                      option={histogramOption}
                      onRange={selectRange}
                      ariaLabel="Histogram of document lengths. Drag to select a range, or use minimum and maximum token inputs in the filters."
                    />
                    <ChartTable
                      caption="Document length values"
                      entries={(stats?.histogram || []).map((d) => ({
                        name: `${format(d.min)}–${format(d.max)} tokens`,
                        value: d.records,
                      }))}
                      total={totals?.records || 0}
                      unit="records"
                    />
                    <div className="panel-foot">
                      <span>Number of records per token interval</span>
                      <span>
                        {filters.min_tokens !== undefined ||
                        filters.max_tokens !== undefined
                          ? `${format(filters.min_tokens)}–${format(filters.max_tokens)} tokens selected`
                          : "Select a range to explore its records"}
                      </span>
                    </div>
                  </section>
                </Suspense>
              )}
              {view === "sources" ? (
                <section className="source-cards">
                  {manifest.sources
                    .filter(
                      (s) => !filters.domain || s.domain === filters.domain,
                    )
                    .map((s) => (
                      <button
                        className="source-card"
                        key={s.id}
                        onClick={() => setSourceDetail(s)}
                      >
                        <span
                          className="source-card-icon"
                          style={{ color: COLORS[s.domain] }}
                        >
                          <BookOpen size={20} />
                        </span>
                        <span className="source-card-domain">{s.domain}</span>
                        <h3>{s.name}</h3>
                        <p>{s.description}</p>
                        <div>
                          <strong>
                            {compact(s.records)} <span>records</span>
                          </strong>
                          <strong>
                            {compact(s.tokens)} <span>tokens</span>
                          </strong>
                          <ArrowUpRight size={17} />
                        </div>
                      </button>
                    ))}
                </section>
              ) : view === "records" ? (
                <section className="panel records-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        Records{" "}
                        <span className="count-badge">
                          {query
                            ? compact(searchTotal ?? undefined) +
                              (activeMode === "semantic"
                                ? " ranked"
                                : " matches")
                            : compact(totals?.records)}
                        </span>
                      </h2>
                      <p>
                        {query
                          ? activeMode === "semantic"
                            ? `Semantic results for “${query}” within your filters · approximate ranking with Danish word vectors.`
                            : `Text matches for “${query}” within your filters.`
                          : "Select a record to read its original text."}
                      </p>
                    </div>
                    <label className="sort-control">
                      <ArrowDownUp size={14} />
                      <select
                        aria-label="Sort records"
                        value={query ? "relevance" : sort}
                        disabled={!!query}
                        onChange={(e) => setSort(e.target.value)}
                      >
                        {query && <option value="relevance">Relevance</option>}
                        <option value="original">Dataset order</option>
                        <option value="shortest">Shortest first</option>
                        <option value="longest">Longest first</option>
                      </select>
                    </label>
                  </div>
                  {rowsError ? (
                    <ErrorBox message={rowsError} retry={() => loadRows()} />
                  ) : (
                    <div className="record-table-scroll">
                      <table className="record-table">
                        <thead>
                          <tr>
                            <th>TEXT / RECORD</th>
                            <th>SOURCE</th>
                            <th>TOKENS</th>
                            <th>QUALITY</th>
                            <th>PII</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((r, i) => {
                            const preview =
                              previews[r.record_no]?.text || r.preview;
                            return (
                              <tr
                                key={`${r.record_no}-${i}`}
                                onClick={() => setActiveRecord(r.record_no)}
                              >
                                <td>
                                  <button
                                    className="record-title"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setActiveRecord(r.record_no);
                                    }}
                                  >
                                    {preview
                                      ? preview
                                          .split(/\n/)
                                          .filter(Boolean)[0]
                                          .slice(0, 105)
                                      : r.id}
                                  </button>
                                  <p className="record-preview">
                                    {preview ? (
                                      preview.slice(0, 220)
                                    ) : r.one_sentence_description ? (
                                      <>
                                        <span className="summary-label">
                                          Annotation summary ·{" "}
                                        </span>
                                        {r.one_sentence_description}
                                      </>
                                    ) : (
                                      "Open this record to read the original text."
                                    )}
                                  </p>
                                  <span className="record-id">{r.id}</span>
                                </td>
                                <td>
                                  <span
                                    className="domain-dot"
                                    style={{ background: COLORS[r.domain] }}
                                  />
                                  {manifest.sources.find(
                                    (s) => s.id === r.source,
                                  )?.name || r.source}
                                </td>
                                <td className="numeric">
                                  {format(r.token_count)}
                                </td>
                                <td>
                                  <span
                                    className={`quality-badge ${r.content_quality || "missing"}`}
                                  >
                                    {r.content_quality
                                      ? label(r.content_quality)
                                      : "No machine label"}
                                  </span>
                                </td>
                                <td>
                                  <span
                                    className={`pii-dot ${r.pii_presence || "missing"}`}
                                  />
                                  <span className="pii-label">
                                    {r.pii_presence === "contains_pii"
                                      ? "Flagged"
                                      : r.pii_presence === "no_pii"
                                        ? "Not flagged"
                                        : "Unknown"}
                                  </span>
                                </td>
                                <td>
                                  <ArrowUpRight size={15} />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                      {!rowsLoading && rows.length === 0 && (
                        <div className="empty">
                          <Search size={24} />
                          <h3>
                            {hasMore
                              ? "No matches in these search results yet"
                              : "No matching records"}
                          </h3>
                          <p>
                            {hasMore
                              ? "Continue searching to examine further matches within your filters."
                              : "Try a broader selection or clear your filters."}
                          </p>
                          <button className="button secondary" onClick={reset}>
                            Clear filters
                          </button>
                        </div>
                      )}
                      {rowsLoading && (
                        <div className="loading-rows">
                          <LoaderCircle className="spin" size={17} />{" "}
                          {query
                            ? "Searching the complete corpus…"
                            : "Loading records…"}
                        </div>
                      )}
                    </div>
                  )}
                  <div className="record-footer">
                    <span>
                      {format(rows.length)} records loaded{" "}
                      {query &&
                        (activeMode === "semantic"
                          ? "· ordered by vector similarity"
                          : "· ordered by text relevance")}
                    </span>
                    {hasMore && (
                      <button
                        className="button secondary"
                        disabled={rowsLoading}
                        onClick={() => loadRows(nextOffset, true)}
                      >
                        {query && rows.length === 0
                          ? "Continue searching"
                          : "Load more records"}
                        <ArrowDown size={14} />
                      </button>
                    )}
                    <span>
                      Click any row to inspect <ArrowUpRight size={12} />
                    </span>
                  </div>
                </section>
              ) : null}

            </>
          )}
        </main>
      </div>
      {activeRecord !== null && (
        <Reader
          recordNo={activeRecord}
          sources={manifest?.sources || []}
          onClose={() => setActiveRecord(null)}
        />
      )}
      {sourceDetail && (
        <Modal title={sourceDetail.name} onClose={() => setSourceDetail(null)}>
          <span
            className="domain-tag"
            style={{ color: COLORS[sourceDetail.domain] }}
          >
            {sourceDetail.domain}
          </span>
          <p>{sourceDetail.description}</p>
          <div className="source-detail-stats">
            <div>
              <strong>{format(sourceDetail.records)}</strong>
              <span>records</span>
            </div>
            <div>
              <strong>{compact(sourceDetail.tokens)}</strong>
              <span>tokens</span>
            </div>
          </div>
          <h3>Source licence</h3>
          <p>{sourceDetail.license}</p>
          <a
            className="text-link"
            href={sourceDetail.url}
            target="_blank"
            rel="noreferrer"
          >
            Read source documentation <ExternalLink size={13} />
          </a>
          <button
            className="button"
            onClick={() => {
              setFilter("source", sourceDetail.id);
              setView("records");
              setSourceDetail(null);
            }}
          >
            Explore this source <ArrowRight size={15} />
          </button>
        </Modal>
      )}
    </div>
  );
}

function ChartTable({
  caption,
  entries,
  total,
  unit,
}: {
  caption: string;
  entries: { name: string; value: number }[];
  total: number;
  unit: string;
}) {
  return (
    <details className="chart-data">
      <summary>
        View chart data<span className="sr-only">: {caption}</span>
      </summary>
      <div className="chart-data-scroll" tabIndex={0}>
        <table>
          <caption className="sr-only">
            {caption}; percentages of the current selection
          </caption>
          <thead>
            <tr>
              <th>Category</th>
              <th>{label(unit)}</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.name}>
                <th scope="row">{e.name}</th>
                <td>{format(e.value)}</td>
                <td>{percent(e.value, total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
function Metric({
  icon,
  title,
  value,
  detail,
}: {
  icon: React.ReactNode;
  title: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="metric">
      <div>
        {icon}
        <span>{title}</span>
      </div>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}
function ErrorBox({ message, retry }: { message: string; retry: () => void }) {
  return (
    <div className="error-box" role="alert">
      <p>{message}</p>
      <button className="button secondary" onClick={retry}>
        <RefreshCw size={14} /> Retry
      </button>
    </div>
  );
}
function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const close = useRef<HTMLButtonElement>(null),
    dialog = useRef<HTMLElement>(null),
    onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    close.current?.focus();
    const keydown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (e.key === "Tab") {
        const items = Array.from(
          dialog.current?.querySelectorAll<HTMLElement>(
            'button:not([disabled]),a[href],input,select,[tabindex="0"]',
          ) || [],
        ).filter((el) => el.offsetParent !== null);
        const first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", keydown);
    return () => {
      window.removeEventListener("keydown", keydown);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        ref={dialog}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button
            ref={close}
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
function Reader({
  recordNo,
  sources,
  onClose,
}: {
  recordNo: number;
  sources: Source[];
  onClose: () => void;
}) {
  const [data, setData] = useState<{
      record: RecordRow;
      text: string;
      has_more: boolean;
      offset: number;
      next_offset: number;
      upstream_truncated: boolean;
    } | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [tab, setTab] = useState("text");
  const [retry, setRetry] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError("");
    api<any>(`record/${recordNo}`, {}, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [recordNo, retry]);
  const more = async () => {
    if (!data) return;
    setLoading(true);
    try {
      const next = await api<any>(
        `record/${recordNo}`,
        data.upstream_truncated
          ? {
              complete: "true",
              offset: 0,
              limit: Math.max(data.text.length + 16000, 32000),
            }
          : { offset: data.next_offset, limit: 16000 },
        controllerRef.current?.signal,
      );
      setData({
        ...next,
        text: data.upstream_truncated ? next.text : data.text + next.text,
      });
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setLoading(false);
    }
  };
  const row = data?.record,
    source = sources.find((s) => s.id === row?.source);
  return (
    <Modal title="Inside the record" onClose={onClose}>
      {!data && loading ? (
        <div className="loading-rows">
          <LoaderCircle className="spin" size={18} /> Loading original text…
        </div>
      ) : (
        row && (
          <>
            <div className="reader-source">
              <span
                className="domain-dot"
                style={{ background: COLORS[row.domain] }}
              />
              {source?.name || row.source}
              <span>{format(row.token_count)} tokens</span>
            </div>
            <h3 className="reader-title">
              {data!.text.split("\n").filter(Boolean)[0]?.slice(0, 170) ||
                row.id}
            </h3>
            <code className="reader-id">{row.id}</code>
            <div className="reader-tabs">
              <button
                className={tab === "text" ? "active" : ""}
                onClick={() => setTab("text")}
              >
                Original text
              </button>
              <button
                className={tab === "metadata" ? "active" : ""}
                onClick={() => setTab("metadata")}
              >
                Metadata & annotations
              </button>
            </div>
            {tab === "text" ? (
              <>
                <div
                  className="reader-text"
                  tabIndex={0}
                  aria-label="Original document text"
                >
                  {data!.text}
                </div>
                {data!.has_more && (
                  <button
                    className="button secondary more-text"
                    disabled={loading}
                    onClick={more}
                  >
                    {loading ? (
                      <LoaderCircle className="spin" size={14} />
                    ) : (
                      <ArrowDown size={14} />
                    )}
                    Load more text
                  </button>
                )}
              </>
            ) : (
              <div><p className="machine-note">Content and privacy labels are model predictions, not human annotations.</p><div className="metadata-list">
                {Object.entries(row)
                  .filter(([k]) => !["record_no", "source_row"].includes(k))
                  .map(([k, v]) => (
                    <div key={k}>
                      <dt>{label(k)}</dt>
                      <dd>
                        {v === null || v === undefined
                          ? "No machine label"
                          : Array.isArray(v)
                            ? v.map((x) => label(String(x))).join(", ") ||
                              "No machine label"
                            : String(v)}
                      </dd>
                    </div>
                  ))}
              </div></div>
            )}
            <ReviewTags record={row} />
            <div className="reader-bottom">
              <span>{source?.license}</span>
              <a href={source?.url} target="_blank" rel="noreferrer">
                Source documentation <ExternalLink size={12} />
              </a>
            </div>
          </>
        )
      )}
      {error && (
        <ErrorBox
          message={error}
          retry={() => (data ? more() : setRetry((v) => v + 1))}
        />
      )}
    </Modal>
  );
}
export default Explorer;
