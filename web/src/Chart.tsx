import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  BrushComponent,
  DataZoomComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";

echarts.use([
  BarChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  BrushComponent,
  DataZoomComponent,
  CanvasRenderer,
]);
type Props = {
  option: EChartsOption;
  height?: number;
  onSelect?: (name: string, index: number) => void;
  onRange?: (start: number, end: number) => void;
  ariaLabel: string;
};
export default function Chart({
  option,
  height = 260,
  onSelect,
  onRange,
  ariaLabel,
}: Props) {
  const div = useRef<HTMLDivElement>(null);
  const instance = useRef<echarts.EChartsType | null>(null);
  const selectRef = useRef(onSelect),
    rangeRef = useRef(onRange);
  selectRef.current = onSelect;
  rangeRef.current = onRange;
  useEffect(() => {
    const chart = echarts.init(div.current!, undefined, { renderer: "canvas" });
    instance.current = chart;
    chart.on("click", (p: any) => {
      if (p.componentType === "series")
        selectRef.current?.(p.name, p.dataIndex);
    });
    chart.on("brushEnd", (p: any) => {
      const range = p.areas?.[0]?.coordRange;
      if (range)
        rangeRef.current?.(
          Math.max(0, Math.round(range[0])),
          Math.round(range[1]),
        );
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(div.current!);
    return () => {
      observer.disconnect();
      chart.dispose();
      instance.current = null;
    };
  }, []);
  useEffect(() => {
    instance.current?.setOption(
      {
        ...option,
        animation: !window.matchMedia("(prefers-reduced-motion: reduce)")
          .matches,
      },
      { notMerge: true },
    );
    if (onRange)
      instance.current?.dispatchAction({
        type: "takeGlobalCursor",
        key: "brush",
        brushOption: { brushType: "lineX", brushMode: "single" },
      });
  }, [option, onRange]);
  return (
    <div
      ref={div}
      role="img"
      aria-label={ariaLabel}
      style={{ height, width: "100%" }}
    />
  );
}
