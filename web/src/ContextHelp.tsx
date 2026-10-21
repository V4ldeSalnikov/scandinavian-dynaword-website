import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Info } from "lucide-react";

export default function ContextHelp({label, children}: {label: string; children: ReactNode}) {
  const [open, setOpen] = useState(false), id = useId(), ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {if (!ref.current?.contains(e.target as Node)) setOpen(false);};
    const key = (e: KeyboardEvent) => {if (e.key === "Escape") setOpen(false);};
    document.addEventListener("pointerdown", close); document.addEventListener("keydown", key);
    return () => {document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", key);};
  }, [open]);
  return <span className="context-help" ref={ref}><button type="button" aria-label={label} aria-expanded={open} aria-controls={id} onClick={e => {e.preventDefault();setOpen(!open);}}><Info size={15}/></button>{open && <span id={id} role="note" className="context-help-content">{children}</span>}</span>;
}
