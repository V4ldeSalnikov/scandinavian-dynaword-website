import { useState } from "react";
import type { RecordRow } from "./data";
const KEY = "dynaword:reviews:v1.2.23";
type Review = {record_no: number; id: string; source: string; version: string; tag: string; saved_at: string};
function read(): Record<string, Review> {
  try {return JSON.parse(localStorage.getItem(KEY) || "{}");} catch {return {};}
}
export function ExportReviews() {
  const [message, setMessage] = useState("");
  function download() {
    const data = Object.values(read());
    if (!data.length) {setMessage("No records saved for review yet. Open a record to add a review tag.");return;}
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));
    const a=document.createElement("a");a.href=url;a.download="dynaword-review-tags.json";a.click();URL.revokeObjectURL(url);setMessage("");
  }
  return <div className="review-export"><button className="text-button" onClick={download}>Export review tags</button>{message && <span role="status">{message}</span>}</div>;
}
export default function ReviewTags({record}: {record: RecordRow}) {
  const [tag,setTag]=useState(()=>read()[record.record_no]?.tag || ""), [error,setError]=useState("");
  function save(value: string) {
    try {
      const saved=read();
      if(value) saved[record.record_no]={record_no:record.record_no,id:record.id,source:record.source,version:"v1.2.23",tag:value,saved_at:new Date().toISOString()};
      else delete saved[record.record_no];
      localStorage.setItem(KEY,JSON.stringify(saved));setTag(value);setError("");
    } catch {setError("Your browser could not save this tag. Try allowing local storage.");}
  }
  return <div className="review-tags"><label>Review tag <select aria-label="Review tag" value={tag} onChange={e=>save(e.target.value)}><option value="">None</option><option value="review">Needs review</option><option value="ocr">OCR / formatting issue</option><option value="duplicate">Possible duplicate</option><option value="quality">Quality concern</option><option value="privacy">Privacy concern</option></select></label><small>Saved only in this browser. Export tags from Records.</small>{error && <p role="alert">{error}</p>}</div>;
}
