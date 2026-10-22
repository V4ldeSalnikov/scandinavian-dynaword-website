import { lazy, Suspense, useCallback, useMemo, useState } from 'react';
import {ArrowDown, Database, FileText, Layers3} from 'lucide-react';
import type {EChartsOption} from 'echarts';
import {ANNOTATIONS, COLORS, compact, format, label, percent, type Filters, type Stats} from '../data';
const Chart = lazy(() => import('../Chart'));
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

export default function SelectionStatistics({stats, loading:statsLoading, sources, filters, annotation, onAnnotation, onFilter, onRange, annotationFields=ANNOTATIONS}: {
 stats:Stats|null; loading:boolean; sources:{id:string;name:string}[]; filters:Filters; annotation:string;
 onAnnotation:(field:string)=>void; onFilter:(field:keyof Filters,value:string|undefined)=>void;
 onRange:(min:number,max:number)=>void; annotationFields?:Record<string,string>;
}) {
 const [measure,setMeasure]=useState<'tokens'|'records'>('tokens');
 const [composition,setComposition]=useState<'domains'|'sources'>('domains');
 const totals=stats?.totals;
 const filtered=Object.values(filters).some(v=>v!==undefined&&v!=='');
 const histogram=useMemo(()=>{const bins=stats?.histogram||[];const last=bins.reduce((n,b,i)=>b.records?i:n,0);return bins.slice(0,last+1);},[stats?.histogram]);
  const selectRange = useCallback(
    (start: number, end: number) => {
      const hist = stats?.histogram;
      if (hist?.[start] && hist?.[end])
        onRange(hist[start].min, hist[end].max);
    },
    [stats?.histogram, onRange],
  );
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
            ? sources.find((s) => s.id === d.name)?.name || d.name
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
    [compositionData, composition, measure, totals, sources],
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
          const b = histogram[p.dataIndex];
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
        data: histogram.map((b) => (b.min === 0 ? "0" : compact(b.min))),
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
          data: histogram.map((b) => b.records),
          barCategoryGap: "18%",
          itemStyle: { color: "#c5565e", borderRadius: [3, 3, 0, 0] },
          emphasis: { itemStyle: { color: "#b5121b" } },
        },
      ],
    }),
    [histogram, totals],
  );

 return <>
              <section
                className="metrics"
                aria-label="Selection statistics"
                aria-busy={statsLoading}
              >
                <Metric
                  icon={<FileText size={16} />}
                  title="RECORDS"
                  value={compact(totals?.records)}
                  detail={
                    filtered
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
                    filtered ? "in your selection" : "distinct collections"
                  }
                />
                <Metric
                  icon={<FileText size={16} />}
                  title="MACHINE LABELS"
                  value={stats?.annotations_available === false ? "—" : percent(totals?.annotated || 0, totals?.records || 0)}
                  detail={stats?.annotations_available === false ? "Not published for this release" : `${compact(totals?.annotated)} of ${compact(totals?.records)} have automated quality labels`}
                />
              </section>
                <Suspense fallback={<div className="loading-rows">Loading selection charts…</div>}>
                  <div
                    className={`chart-grid ${statsLoading ? "updating" : ""}`}
                  >
                    <section className="panel composition">
                      <div className="panel-heading">
                        <div>
                          <h2>Corpus composition</h2>

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
                          onFilter(
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
                              ? sources.find((s) => s.id === d.name)
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
                          <h2>Annotations</h2>

                        </div>
                        <span className="tiny-badge">AUTOMATED</span>
                      </div>
                      <select
                        className="annotation-select"
                        disabled={stats?.annotations_available === false}
                        aria-label="Annotation to visualise"
                        value={annotation}
                        onChange={(e) => onAnnotation(e.target.value)}
                      >
                        {Object.entries(annotationFields).map(([k, v]) => (
                          <option value={k} key={k}>
                            {v}
                          </option>
                        ))}
                      </select>
{stats?.annotations_available === false ? <p className="statistics-unavailable">Annotations are not published for this release.</p> : <>
                      <Chart
                        height={Math.max(267, annotationData.length * 26 + 40)}
                        option={annotationOption}
                        ariaLabel={`${annotationFields[annotation]} distribution. Use the annotation category selector below for keyboard selection.`}
                        onSelect={(name) => onFilter(annotation as keyof Filters, name)}
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
                          onChange={e=>onFilter(annotation as keyof Filters, e.target.value)}
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
</>}
                    </section>
                  </div>
                  <section
                    className={`panel lengths ${statsLoading ? "updating" : ""}`}
                  >
                    <div className="panel-heading">
                      <div>
                        <h2>Document lengths</h2>
                        {stats?.histogram_available !== false && <p>Drag across the chart to select a token range</p>}
                      </div>
                      <span className="subtle-label">
                        DOUBLING TOKEN INTERVALS
                      </span>
                    </div>
{stats?.histogram_available === false ? <p className="statistics-unavailable">Document lengths will be available when the record index is ready.</p> : <>
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
</>}
                  </section>
                </Suspense>
 </>;
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
