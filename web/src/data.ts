export type Filters = {
  topic_id?: number;
  source?: string;
  domain?: string;
  content_quality?: string;
  pii_presence?: string;
  min_tokens?: number;
  max_tokens?: number;
  annotation_key?: string;
  annotation_value?: string;
};
export type Source = {
  id: string;
  name: string;
  domain: string;
  description: string;
  license: string;
  url: string;
  records: number;
  tokens: number;
  annotated: number;
};
export type Manifest = {
  status: string;
  dataset: string;
  revision: string;
  records: number;
  tokens: number;
  annotated: number;
  sources: Source[];
  search: {
    text: boolean;
    semantic: boolean;
    semantic_index: {
      records_processed: number;
      records_with_vectors: number;
      model?: { name: string };
    };
  };
  published_stats: {
    number_of_samples: number;
    number_of_tokens: number;
    annotations: { number_of_annotated_documents: number };
  };
};
export type Group = {
  name: string;
  records: number;
  tokens: number;
  domain?: string;
};
export type Stats = {
  totals: {
    records: number;
    tokens: number;
    sources: number;
    annotated: number;
  };
  domains: Group[];
  sources: Group[];
  annotations: Group[];
  histogram: { min: number; max: number; records: number }[];
  annotation_covered: number;
  annotation: string;
};
export type RecordRow = {
  record_no: number;
  id: string;
  source: string;
  domain: string;
  token_count: number;
  added: string;
  created: string;
  one_sentence_description?: string;
  content_quality?: string;
  pii_presence?: string;
  content_type?: string[];
  preview?: string;
  [key: string]: unknown;
};
export type RowsResponse = {
  rows: RecordRow[];
  has_more: boolean;
  next_offset: number;
  upstream_matches?: number;
  scanned?: number;
  compared?: number;
};
export const API = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
export async function api<T>(
  path: string,
  params: Record<string, string | number> = {},
  signal?: AbortSignal,
): Promise<T> {
  const query = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  );
  const res = await fetch(
    `${API}/api/${path}${query.size ? "?" + query : ""}`,
    { signal },
  );
  if (!res.ok) {
    let message = "The data service could not complete this request.";
    try {
      const body = await res.json();
      message = body.detail || message;
    } catch {
      /* non-JSON service error */
    }
    throw new Error(message);
  }
  return res.json();
}
export const format = (n: number | undefined) =>
  new Intl.NumberFormat("en-GB").format(n || 0);
export const compact = (n: number | undefined) =>
  n === undefined
    ? "—"
    : new Intl.NumberFormat("en-US", {
        notation: "compact",
        maximumFractionDigits: 2,
      }).format(n);
export const percent = (n: number, total: number) =>
  total ? `${((100 * n) / total).toFixed(1)}%` : "0%";
export const label = (s: string) =>
  s === "__missing__"
    ? "Not annotated"
    : s === "contains_pii"
      ? "PII flagged"
      : s === "no_pii"
        ? "No PII flagged"
        : s.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export const COLORS: Record<string, string> = {
  Other: "#477cba",
  Legal: "#7071c4",
  News: "#45a1a6",
  Books: "#cb9a53",
  Conversation: "#8298bb",
  "Social Media": "#ca7788",
  Web: "#67a482",
  Encyclopedic: "#538cd3",
  Speeches: "#a184c2",
  Medical: "#d58c68",
  Readaloud: "#a7a356",
  Dialect: "#92aab5",
};
export const ANNOTATIONS: Record<string, string> = {
  content_quality: "Content quality",
  pii_presence: "PII detection",
  content_type: "Content type",
  information_density: "Information density",
  educational_value: "Educational value",
  content_safety: "Content safety",
  content_integrity: "Content integrity",
  reasoning_indicators: "Reasoning indicators",
};
export function filterLabels(filters: Filters, sources: Source[]) {
  return Object.entries(filters)
    .filter(([k, v]) => k !== "annotation_key" && v !== undefined && v !== "")
    .map(([key, value]) => ({
      key,
      label:
        key === "topic_id"
          ? Number(value) === -1 ? "No topic vector" : `Topic ${value}`
          : key === "source"
          ? sources.find((s) => s.id === value)?.name || String(value)
          : key === "min_tokens"
            ? `≥ ${format(Number(value))} tokens`
            : key === "max_tokens"
              ? `≤ ${format(Number(value))} tokens`
              : key === "annotation_value"
                ? `${ANNOTATIONS[filters.annotation_key || ""]}: ${label(String(value))}`
                : label(String(value)),
    }));
}
