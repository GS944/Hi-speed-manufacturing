import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, CornerDownLeft, Search, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { useDebounced } from "../lib/hooks";
import { fmtDate, fmtMoney, fmtNum } from "../lib/format";
import { Badge, Button, Modal, Spinner, StatusPill, cx } from "./ui";

const EXAMPLES = ["status of 2475", "emergency orders pending for taegutec", "what is at globe-tech",
  "how many overdue orders for tungaloy", "orders likely to be late", "annexure for 2052", "unusual costs"];

type Suggestion = { order_no: string; status: string; customer: string; item: string };

export default function CommandBar() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [sugs, setSugs] = useState<Suggestion[]>([]);
  const [active, setActive] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const dq = useDebounced(q, 180);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); inputRef.current?.focus(); setOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (/^\s*[\w-]{1,10}\s*$/.test(dq) && /\d/.test(dq)) {
      api<Suggestion[]>(`/api/orders/suggest?q=${encodeURIComponent(dq.trim())}`).then(setSugs).catch(() => setSugs([]));
    } else setSugs([]);
    setActive(-1);
  }, [dq]);

  const run = async (text = q) => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await api("/api/ask", { method: "POST", json: { q: text } });
      if (r.kind === "navigate") {
        nav(r.target === "annexure" ? `/annexure/${r.order_no}` : `/track/${r.order_no}`);
        setOpen(false);
        setQ("");
        inputRef.current?.blur();
      } else {
        setResult(r);
        setOpen(false);
      }
    } catch (e: any) {
      setResult({ answer: e.message, kind: "message" });
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" && sugs.length) { e.preventDefault(); setActive((a) => Math.min(sugs.length - 1, a + 1)); }
    else if (e.key === "ArrowUp" && sugs.length) { e.preventDefault(); setActive((a) => Math.max(-1, a - 1)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (active >= 0 && sugs[active]) { nav(`/track/${sugs[active].order_no}`); setQ(""); setOpen(false); inputRef.current?.blur(); }
      else run();
    } else if (e.key === "Escape") { setOpen(false); inputRef.current?.blur(); }
  };

  return (
    <div className="relative w-full max-w-xl">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
        <input ref={inputRef} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)} onKeyDown={onKeyDown}
          placeholder="Track an order or ask… e.g. “emergency orders pending for taegutec”"
          aria-label="Search orders or ask a question"
          className="h-9 w-full rounded-lg border border-line bg-surface-2 pl-9 pr-16 text-sm text-ink outline-none placeholder:text-muted focus:border-primary focus:bg-surface focus:ring-2 focus:ring-primary/20" />
        <span className="absolute right-2 top-1/2 -translate-y-1/2">
          {busy ? <Spinner className="size-4" /> : <kbd className="rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] text-muted">Ctrl K</kbd>}
        </span>
      </div>
      {open && (
        <div className="card fade-in absolute left-0 right-0 top-11 z-40 overflow-hidden" style={{ boxShadow: "var(--shadow-lg)" }}>
          {sugs.length > 0 && (
            <div className="border-b border-line py-1">
              <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">Orders</div>
              {sugs.map((s, i) => (
                <button key={s.order_no} onMouseDown={() => nav(`/track/${s.order_no}`)}
                  className={cx("flex w-full items-center gap-3 px-3 py-2 text-left text-[13px] hover:bg-surface-3", i === active && "bg-surface-3")}>
                  <span className="w-14 font-semibold tabular">#{s.order_no}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-2">{s.customer} · {s.item}</span>
                  <StatusPill status={s.status} />
                </button>
              ))}
            </div>
          )}
          <div className="py-1">
            <div className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted"><Sparkles className="size-3.5" /> Ask in plain English</div>
            {q.trim() && (
              <button onMouseDown={() => run()} className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-surface-3">
                <CornerDownLeft className="size-3.5 text-muted" /> <span className="truncate">“{q}”</span>
              </button>
            )}
            {!q.trim() && EXAMPLES.map((ex) => (
              <button key={ex} onMouseDown={() => { setQ(ex); run(ex); }} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] text-ink-2 hover:bg-surface-3">
                <ArrowRight className="size-3.5 text-muted" /> {ex}
              </button>
            ))}
          </div>
        </div>
      )}
      <AnswerModal result={result} onClose={() => setResult(null)} onOpen={(n) => { setResult(null); nav(`/track/${n}`); }} />
    </div>
  );
}

function AnswerModal({ result, onClose, onOpen }: { result: any; onClose: () => void; onOpen: (n: string) => void }) {
  const nav = useNavigate();
  if (!result) return null;
  const p = result.parsed || {};
  const ents = Object.entries(p.entities || {}) as [string, string][];
  const listUrl = () => {
    const sp = new URLSearchParams();
    if (result.filters?.status) sp.set("status", result.filters.status);
    if (result.filters?.customer) sp.set("customer", result.filters.customer);
    if (result.filters?.priority) sp.set("priority", result.filters.priority);
    if (result.filters?.category) sp.set("category", result.filters.category);
    return `/orders?${sp}`;
  };
  return (
    <Modal open onClose={onClose} title="Answer" width="max-w-4xl"
      footer={<>{(result.kind === "orders" || result.kind === "count") && <Button onClick={() => { onClose(); nav(listUrl()); }}>Open in Orders</Button>}<Button variant="primary" onClick={onClose}>Done</Button></>}>
      <p className="text-[15px] font-medium text-ink">{result.answer}</p>
      {(p.intent || ents.length > 0) && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
          <span>Understood as</span>
          {p.intent && <Badge tone="info">{String(p.intent).replace("_", " ")} · {Math.round((p.confidence || 0) * 100)}%</Badge>}
          {p.status && <Badge>status: {p.status}</Badge>}
          {p.period && <Badge>period: {p.period}</Badge>}
          {ents.map(([k, v]) => <Badge key={k}>{k}: {v}</Badge>)}
        </div>
      )}
      {result.kind === "orders" && result.rows?.length > 0 && (
        <div className="mt-4 max-h-[50vh] overflow-auto rounded-lg border border-line">
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 bg-surface-2 text-left text-[12px] text-muted"><tr>
              <th className="px-3 py-2">Order</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Customer</th><th className="px-3 py-2">Item</th><th className="px-3 py-2">Stage</th><th className="px-3 py-2">Due</th></tr></thead>
            <tbody>{result.rows.slice(0, 100).map((r: any) => (
              <tr key={r.id} className="cursor-pointer border-t border-line hover:bg-surface-2" onClick={() => onOpen(r.order_no)}>
                <td className="px-3 py-2 font-semibold tabular">#{r.order_no}</td><td className="px-3 py-2"><StatusPill status={r.status} /></td>
                <td className="px-3 py-2">{r.customer}</td><td className="max-w-[260px] truncate px-3 py-2 text-ink-2">{r.item}</td>
                <td className="px-3 py-2 text-ink-2">{r.stage}</td><td className="px-3 py-2 tabular">{fmtDate(r.due_date)}</td></tr>))}</tbody>
          </table>
        </div>
      )}
      {result.kind === "entries" && result.entries?.length > 0 && (
        <div className="mt-4 max-h-[50vh] overflow-auto rounded-lg border border-line">
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 bg-surface-2 text-left text-[12px] text-muted"><tr>
              <th className="px-3 py-2">DC</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Order</th><th className="px-3 py-2">Vendor</th><th className="px-3 py-2">Operation</th><th className="px-3 py-2 text-right">Qty</th><th className="px-3 py-2 text-right">Unit cost</th>{result.entries[0]?.reason && <th className="px-3 py-2">Why flagged</th>}</tr></thead>
            <tbody>{result.entries.slice(0, 150).map((e: any) => (
              <tr key={e.id} className="border-t border-line">
                <td className="px-3 py-2 tabular">{e.doc_no}</td><td className="px-3 py-2 tabular">{fmtDate(e.issue_date)}</td>
                <td className="px-3 py-2">{e.refs?.map((k: string) => <button key={k} className="mr-1 font-medium text-primary hover:underline" onClick={() => onOpen(k)}>#{k}</button>)}</td>
                <td className="px-3 py-2">{e.vendor}</td><td className="px-3 py-2">{e.operation}</td>
                <td className="px-3 py-2 text-right tabular">{fmtNum(e.qty)}</td><td className="px-3 py-2 text-right tabular">{fmtMoney(e.unit_cost)}</td>
                {e.reason && <td className="px-3 py-2 text-[12px] text-ink-2">{e.reason}</td>}</tr>))}</tbody>
          </table>
        </div>
      )}
      {result.kind === "table" && (
        <table className="mt-4 w-full text-[13px]"><thead className="text-left text-[12px] text-muted"><tr>{result.columns.map((c: string) => <th key={c} className="px-3 py-2">{c}</th>)}</tr></thead>
          <tbody>{result.table.map((r: any[], i: number) => <tr key={i} className="border-t border-line">{r.map((v, j) => <td key={j} className="px-3 py-2 tabular">{v}</td>)}</tr>)}</tbody></table>
      )}
    </Modal>
  );
}
