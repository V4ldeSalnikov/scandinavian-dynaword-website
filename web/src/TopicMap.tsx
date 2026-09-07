import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { ScatterChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { LabelLayout } from "echarts/features";
import { Focus, Minus, Plus, RotateCcw } from "lucide-react";
import { COLORS, label } from "./data";
import type { Topic, TopicPoint } from "./Topics";

echarts.use([ScatterChart, DataZoomComponent, GridComponent, TooltipComponent, CanvasRenderer, LabelLayout]);
const PALETTE = ["#5484c9", "#c47761", "#549b8d", "#8a74ba", "#c39644", "#58a0be", "#c16c8b", "#7e9556", "#7282a3", "#ab7950", "#b372b0", "#419ba1", "#6878cc", "#a28a4b", "#9c687b", "#758c72", "#ba875e", "#7584c1", "#6098aa", "#b76872", "#8e9670", "#a67ec1", "#5d8fcd", "#99915c", "#957360", "#5c9f84", "#c287a1", "#6f96b0"];
export const topicColor = (id: number) => id < 0 ? "#a5adbb" : PALETTE[id % PALETTE.length];
export type ColorBy = "topic" | "domain" | "quality" | "pii";
const annotationColors: Record<string, string> = {excellent: "#306e9c", good: "#589b9a", adequate: "#a9ae6d", poor: "#ce9b59", unacceptable: "#bd687d", contains_pii: "#bb708a", no_pii: "#5c9b91", __missing__: "#b3bbc8"};

export default function TopicMap({points, topics, colorBy, onRecord}: {
  points: TopicPoint[]; topics: Topic[]; colorBy: ColorBy; onRecord: (id: number) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.EChartsType | null>(null);
  const callback = useRef(onRecord);
  callback.current = onRecord;
  const [zoomed, setZoomed] = useState(false);
  const [labelsVisible, setLabelsVisible] = useState(true);
  const names = useMemo(() => new Map(topics.map(t => [t.id, t.name])), [topics]);
  const groups = useMemo(() => {
    const result = new Map<string, {name: string; color: string; points: TopicPoint[]}>();
    for (const p of points) {
      const key = colorBy === "topic" ? String(p[3]) : colorBy === "domain" ? p[5] : (colorBy === "quality" ? p[6] : p[7]) || "__missing__";
      if (!result.has(key)) result.set(key, {
        name: colorBy === "topic" ? names.get(p[3]) || "No topic vector" : label(key),
        color: colorBy === "topic" ? topicColor(p[3]) : colorBy === "domain" ? COLORS[key] || "#a5adbb" : annotationColors[key] || "#a5adbb", points: [],
      });
      result.get(key)!.points.push(p);
    }
    return [...result.values()];
  }, [points, colorBy, names]);
  useEffect(() => {
    const instance = echarts.init(container.current!);
    chart.current = instance;
    instance.on("click", (p: any) => {
      if (p.data?.recordNo !== undefined) callback.current(p.data.recordNo);
    });
    instance.on("datazoom", () => setZoomed(true));
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(container.current!);
    return () => { observer.disconnect(); instance.dispose(); chart.current = null; };
  }, []);
  useEffect(() => {
    const centers = topics.map(topic => {
      const members = points.filter(p => p[3] === topic.id);
      if (members.length < 20) return null;
      const median = (axis: 1 | 2) => members.map(p => p[axis]).sort((a,b) => a-b)[Math.floor(members.length/2)];
      return {name: topic.name.split(" · ").slice(0, 2).join(" · "), value: [median(1), median(2)]};
    }).filter(Boolean);
    chart.current?.setOption({
      animation: false,
      grid: {left: 25, right: 25, top: 32, bottom: 28},
      xAxis: {type: "value", show: false, scale: true, min: (v: any) => v.min-(v.max-v.min)*.04, max: (v: any) => v.max+(v.max-v.min)*.04},
      yAxis: {type: "value", show: false, scale: true, min: (v: any) => v.min-(v.max-v.min)*.04, max: (v: any) => v.max+(v.max-v.min)*.04},
      dataZoom: [
        {type: "inside", xAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: true, moveOnMouseMove: true, preventDefaultMouseMove: true},
        {type: "inside", yAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: true, moveOnMouseMove: true, preventDefaultMouseMove: true},
      ],
      tooltip: {trigger: "item", confine: true, renderMode: "richText", backgroundColor: "#23344d", borderWidth: 0,
        textStyle: {color: "#fff", fontFamily: "DM Sans, sans-serif", fontSize: 12}, padding: 14,
        formatter: (p: any) => {
          const record = p.data?.point as TopicPoint | undefined;
          if (!record) return p.name;
          const preview = record[8].slice(0, 175).match(/.{1,43}(?:\s|$)|.{1,43}/g)?.join("\n") || "";
          return `${names.get(record[3]) || "No topic vector"}\n${record[4]} · ${record[5]}\n\n${preview}\n\nClick to read original text`;
        }},
      series: [
        ...groups.map(g => ({type: "scatter", name: g.name, symbolSize: points.length < 1500 ? 6 : 4,
          itemStyle: {color: g.color, opacity: .67}, emphasis: {scale: 2.2, itemStyle: {opacity: 1, borderWidth: 1, borderColor: "#fff"}},
          progressive: 4000,
          data: g.points.map(p => ({value: [p[1],p[2]], name: p[8], recordNo: p[0], point: p})),
        })),
        ...(labelsVisible && colorBy === "topic" ? [{type: "scatter", silent: true, symbolSize: 0, z: 4,
          label: {show: true, formatter: "{b}", color: "#30435b", fontSize: 10, fontFamily: "DM Sans, sans-serif", fontWeight: 600,
            backgroundColor: "rgba(255,255,255,.90)", borderColor: "#e1e6ee", borderWidth: 1, borderRadius: 4, padding: [5,7]},
          labelLayout: {hideOverlap: true}, data: centers,
        }] : []),
      ],
    }, {notMerge: true});
    setZoomed(false);
  }, [groups, points, topics, colorBy, names, labelsVisible]);
  function zoom(factor: number) {
    const options = chart.current?.getOption() as any;
    if (!options) return;
    options.dataZoom.forEach((d: any, i: number) => {
      const middle = (d.start+d.end)/2, half = (d.end-d.start)*factor/2;
      chart.current?.dispatchAction({type: "dataZoom", dataZoomIndex: i, start: Math.max(0,middle-half), end: Math.min(100,middle+half)});
    });
    setZoomed(true);
  }
  function reset() {
    chart.current?.dispatchAction({type: "dataZoom", start: 0, end: 100});
    setZoomed(false);
  }
  return <div className="topic-map-shell">
    <div className="map-hint"><span className="live-dot" /> DOCUMENT LANDSCAPE <span>UMAP · 2D</span></div>
    <div ref={container} className="topic-map" role="img" aria-label={`Interactive map of ${points.length} sampled records. Scroll to zoom, drag to pan, and click a point to read. The mapped-record list below provides keyboard access.`} />
    {!points.length && <div className="map-empty"><Focus size={28}/><strong>No mapped records in this selection</strong><span>The map is a sample. Use the full record browser below to see every matching record.</span></div>}
    <div className="map-bottom">
      <label className="map-label-toggle"><input type="checkbox" checked={labelsVisible} onChange={e => setLabelsVisible(e.target.checked)} disabled={colorBy !== "topic"}/> Topic labels</label>
      <span className="map-instructions">Scroll to zoom · drag to pan · click to read</span>
      <div className="map-tools" aria-label="Map controls">
        <button onClick={() => zoom(.7)} aria-label="Zoom in map"><Plus size={16}/></button>
        <button onClick={() => zoom(1.4)} aria-label="Zoom out map"><Minus size={16}/></button>
        <button onClick={reset} aria-label="Reset map zoom" title="Reset map zoom" className={zoomed ? "changed" : ""}><RotateCcw size={14}/></button>
      </div>
    </div>
    {colorBy !== "topic" && <div className="map-legend">{groups.map(g => <span key={g.name}><i style={{background:g.color}}/>{g.name}</span>)}</div>}
  </div>;
}
