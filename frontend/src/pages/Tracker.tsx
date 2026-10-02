import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, CalendarClock, Check, ClipboardEdit, Factory, FileSpreadsheet, FileText, Package, Printer, Radar, Search, Truck } from "lucide-react";
import { api } from "../lib/api";
import { useApi } from "../lib/hooks";
import { fmtDate, fmtMoney, fmtNum, relDays } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, Loading, Modal, PageHeader, StatusPill, cx, useToast } from "../components/ui";

const EDITABLE: { role: string; label: string; type: "date" | "number" | "text" }[] = [
  { role: "issued_qty", label: "Issued qty", type: "number" },
  { role: "coating_date", label: "Coating date", type: "date" },
  { role: "coating_qty", label: "Coating qty", type: "number" },
  { role: "reject_qty", label: "Reject qty", type: "number" },
  { role: "despatch_date", label: "Despatch date", type: "date" },
  { role: "despatch_qty", label: "Despatch qty", type: "number" },
  { role: "invoice_ref", label: "Invoice / DC ref", type: "text" },
  { role: "remarks", label: "Remarks", type: "text" },
];

export default function Tracker() {
  const { orderNo } = useParams();
  const nav = useNavigate();
  const [q, setQ] = useState(orderNo || "");
  useEffect(() => setQ(orderNo || ""), [orderNo]);
  const { data, error, loading, reload, setData } = useApi<any>(orderNo ? `/api/orders/${encodeURIComponent(orderNo)}` : null, { poll: 15000 });
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  useEffect(() => { if (data) setUpdatedAt(new Date()); }, [data]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = q.trim();
    if (v) nav(`/track/${encodeURIComponent(v)}`);
  };

  return (
    <>
      <PageHeader title="Live Order Tracker" subtitle="Enter an order number to see its live status, current stage and every operation performed." />
      <form onSubmit={submit} className="card mb-5 flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Order number, e.g. 2475" className="h-12 pl-11 text-[16px]" inputMode="search" aria-label="Order number" autoFocus={!orderNo} />
        </div>
        <Button type="submit" variant="primary" className="h-12 px-6 text-[15px]" icon={<Radar className="size-5" />}>Track</Button>
      </form>

      {!orderNo && <Card><Empty icon={<Radar className="size-6" />} title="Track any order">Status is computed live from your order book and annexure ledgers. Green means work is in progress; red means the order is completed.</Empty></Card>}
      {orderNo && loading && !data && <Loading label={`Looking up order ${orderNo}…`} />}
      {orderNo && error && !data && <NotFound orderNo={orderNo} />}
      {data && (
        <div className="space-y-4 fade-in">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-muted">
            <span className="inline-flex items-center gap-1.5"><span className="live-dot inline-block size-1.5 rounded-full bg-good" />Live view · refreshes every 15 s · updated {updatedAt?.toLocaleTimeString()}</span>
            {data.line_count > 1 && <Badge tone="info">{data.line_count} line items share this order number</Badge>}
          </div>
          {data.lines.map((ln: any) => <LineCard key={ln.id} ln={ln} onUpdated={(p) => p ? setData(p) : reload()} />)}
        </div>
      )}
    </>
  );
}

function NotFound({ orderNo }: { orderNo: string }) {
  const { data } = useApi<any[]>(`/api/orders/suggest?q=${encodeURIComponent(orderNo.slice(0, -1) || orderNo)}`);
  return (
    <Card><Empty icon={<Search className="size-6" />} title={`Order ${orderNo} was not found`}>
      Check the number, or make sure the order book containing it has been uploaded.
      {data && data.length > 0 && (
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {data.map((s) => <Link key={s.order_no} to={`/track/${s.order_no}`} className="rounded-md border border-line px-2 py-1 text-[13px] text-primary hover:bg-surface-3">#{s.order_no}</Link>)}
        </div>)}
    </Empty></Card>
  );
}

function LineCard({ ln, onUpdated }: { ln: any; onUpdated: (p?: any) => void }) {
  const nav = useNavigate();
  const [editing, setEditing] = useState(false);
  const live = ln.status === "live";
  const q = ln.quantities || {};
  const eta = ln.eta;
  return (
    <>
      <section className={cx("card overflow-hidden border-l-4", live ? "border-l-good" : "border-l-critical")}>
        <div className="flex flex-wrap items-start justify-between gap-4 p-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-[26px] font-semibold tracking-tight tabular">Order #{ln.order_no}</h2>
              <StatusPill status={ln.status} size="lg" />
              {ln.urgent && <Badge tone="warning"><AlertTriangle className="size-3" /> {ln.priority}</Badge>}
              {ln.overdue_days > 0 && <Badge tone="critical">Overdue by {ln.overdue_days} day{ln.overdue_days > 1 ? "s" : ""}</Badge>}
            </div>
            <p className="mt-2 text-[15px] text-ink"><span className="font-semibold">{live ? ln.stage : "Completed"}:</span> {ln.activity}</p>
            <p className="mt-1 text-[13px] text-muted">{ln.customer}{ln.customer_code ? ` (${ln.customer_code})` : ""} · {ln.item}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button icon={<ClipboardEdit className="size-4" />} onClick={() => setEditing(true)}>Update progress</Button>
            <Button icon={<FileSpreadsheet className="size-4" />} onClick={() => nav(`/annexure/${ln.order_no}`)}>Annexure</Button>
            <Button icon={<Printer className="size-4" />} onClick={() => nav(`/annexure/${ln.order_no}?doc=route`)}>Route card</Button>
          </div>
        </div>

        <Stepper stages={ln.stages} live={live} />

        <div className="grid gap-px border-t border-line bg-line sm:grid-cols-2 xl:grid-cols-4">
          <Info icon={<CalendarClock className="size-4" />} label="Order date" value={fmtDate(ln.order_date)} />
          <Info icon={<CalendarClock className="size-4" />} label="Due date (ETD)" value={fmtDate(ln.due_date)} hint={ln.due_date && live ? relDays(ln.due_date) : undefined} />
          <Info icon={<Truck className="size-4" />} label={live ? "Expected completion (ML)" : "Despatched on"}
            value={live ? (eta ? fmtDate(eta.expected) : "—") : fmtDate(ln.despatch_date)}
            hint={live && eta ? <>80% by {fmtDate(eta.p80)} · <RiskTag risk={eta.late_risk} /></> : undefined} />
          <Info icon={<Package className="size-4" />} label="Customer PO" value={ln.customer_po ?? "—"} hint={ln.hardness ? `Hardness ${ln.hardness}` : undefined} />
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
        <Card title="Quantities" subtitle="From the order book">
          <QtyBars q={q} />
        </Card>
        <Card className="min-w-0" title="Job work & operations" subtitle={`${ln.job_work.length} annexure entr${ln.job_work.length === 1 ? "y" : "ies"} linked to this order`}
          actions={ln.job_work.length > 0 && <Button size="sm" icon={<FileText className="size-4" />} onClick={() => nav(`/annexure/${ln.order_no}`)}>Print annexure</Button>}>
          {ln.job_work.length ? <JobWork entries={ln.job_work} /> : <Empty icon={<Factory className="size-5" />} title="No job-work DCs yet">Operations sent to vendors appear here as soon as they are entered in the annexure ledger.</Empty>}
        </Card>
      </div>

      <Card title="All recorded details" subtitle={`Source: ${ln.source?.file ?? ""} › ${ln.source?.sheet ?? ""}, row ${ln.row_no || "added in app"}`}>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(ln.record).map(([k, v]) => (
            <div key={k} className="min-w-0"><dt className="text-[12px] text-muted">{k}</dt><dd className="truncate text-[13.5px] font-medium" title={String(v)}>{String(v)}</dd></div>
          ))}
        </dl>
      </Card>
      <ProgressModal open={editing} onClose={() => setEditing(false)} ln={ln} onSaved={onUpdated} />
    </>
  );
}

function RiskTag({ risk }: { risk: string }) {
  return <span className={cx("font-medium", risk === "high" ? "text-critical" : risk === "medium" ? "text-warning" : "text-good")}>{risk} late risk</span>;
}

function Info({ icon, label, value, hint }: { icon: React.ReactNode; label: string; value: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="bg-surface px-5 py-3.5">
      <div className="flex items-center gap-1.5 text-[12px] text-muted">{icon}{label}</div>
      <div className="mt-0.5 text-[15px] font-semibold tabular">{value}</div>
      {hint && <div className="text-[12px] text-muted">{hint}</div>}
    </div>
  );
}

function Stepper({ stages, live }: { stages: any[]; live: boolean }) {
  return (
    <ol className="flex flex-col gap-0 border-t border-line px-5 py-5 md:flex-row md:items-start">
      {stages.map((s, i) => {
        const done = s.state === "done";
        const cur = s.state === "current";
        const skipped = s.state === "skipped";
        return (
          <li key={s.key} className="relative flex flex-1 gap-3 pb-5 md:flex-col md:items-center md:pb-0 md:text-center">
            {i < stages.length - 1 && (
              <span className={cx("absolute left-[15px] top-8 h-[calc(100%-24px)] w-0.5 md:left-[calc(50%+18px)] md:top-[15px] md:h-0.5 md:w-[calc(100%-36px)]",
                done ? (live ? "bg-good" : "bg-critical") : "bg-line")} aria-hidden />
            )}
            <span className={cx("relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border-2 text-[13px] font-semibold",
              done && (live ? "border-good bg-good text-white" : "border-critical bg-critical text-white"),
              cur && "live-dot border-good bg-good-soft text-good",
              !done && !cur && "border-line bg-surface text-muted", skipped && "border-dashed")}>
              {done ? <Check className="size-4" /> : i + 1}
            </span>
            <div className="min-w-0 md:mt-2">
              <div className={cx("text-[13.5px] font-semibold", cur ? "text-good" : done ? "text-ink" : "text-muted")}>{s.label}</div>
              <div className="text-[12px] text-muted">
                {cur ? "In progress" : skipped ? "Not required" : done ? (s.date ? fmtDate(s.date) : "Done") : "Pending"}
                {s.qty != null && (done || cur) ? ` · ${fmtNum(s.qty)} pcs` : ""}
              </div>
              {s.detail && (cur || s.key === "job_work") && <div className="text-[11.5px] text-muted">{s.detail}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function QtyBars({ q }: { q: Record<string, number | null> }) {
  const base = q.order_qty || q.issued_qty || 1;
  const rows = [
    ["order_qty", "Ordered"], ["issued_qty", "Issued"], ["coating_qty", "Coated / finished"],
    ["reject_qty", "Rejected"], ["despatch_qty", "Despatched"], ["stock_qty", "Balance stock"],
  ].filter(([k]) => k in q);
  if (!rows.length) return <Empty title="No quantity columns mapped" />;
  return (
    <div className="space-y-3">
      {rows.map(([k, label]) => {
        const v = q[k] ?? 0;
        return (
          <div key={k}>
            <div className="mb-1 flex justify-between text-[13px]"><span className="text-ink-2">{label}</span><span className="font-semibold tabular">{q[k] == null ? "—" : fmtNum(v)}</span></div>
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div className={cx("h-full rounded-full", k === "reject_qty" ? "bg-warning" : "bg-primary")} style={{ width: `${Math.min(100, (100 * Math.max(0, v)) / base)}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function JobWork({ entries }: { entries: any[] }) {
  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="w-full min-w-[900px] text-[13px] [&_td]:whitespace-nowrap">
        <thead className="border-y border-line bg-surface-2 text-left text-[12px] text-muted">
          <tr><th className="px-5 py-2">DC No.</th><th className="px-2">Issue date</th><th className="px-2">Operation</th><th className="px-2">Vendor</th>
            <th className="px-2 text-right">Qty</th><th className="px-2 text-right">Unit cost</th><th className="px-2">HRC spec / checked</th><th className="px-2">Inward</th><th className="px-5">State</th></tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id} className="border-b border-line last:border-0">
              <td className="px-5 py-2.5 font-medium tabular">{e.doc_no}</td>
              <td className="px-2 tabular">{fmtDate(e.issue_date)}</td>
              <td className="px-2">{e.operation}</td>
              <td className="max-w-[220px] truncate px-2 text-ink-2" title={e.vendor}>{e.vendor}</td>
              <td className="px-2 text-right tabular">{fmtNum(e.qty)}</td>
              <td className="px-2 text-right tabular">{fmtMoney(e.unit_cost)}</td>
              <td className="px-2">
                <span className="tabular">{e.hrc_spec || "—"}</span>{e.hrc_checked && <span className="tabular text-ink-2"> / {e.hrc_checked}</span>}
                {e.hrc_result === "ok" && <Badge tone="good" className="ml-1.5">OK</Badge>}
                {e.hrc_result === "out_of_spec" && <Badge tone="critical" className="ml-1.5">Out of spec</Badge>}
              </td>
              <td className="px-2 tabular">{fmtDate(e.inward_date)}</td>
              <td className="px-5">{e.state === "at_vendor"
                ? <Badge tone="good"><span className="live-dot inline-block size-1.5 rounded-full bg-good" /> At vendor</Badge>
                : <Badge>Returned</Badge>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProgressModal({ open, onClose, ln, onSaved }: { open: boolean; onClose: () => void; ln: any; onSaved: (p?: any) => void }) {
  const toast = useToast();
  const fields = EDITABLE.filter((f) => ln.fields?.[f.role]);
  const initial = () => Object.fromEntries(fields.map((f) => [f.role, String(ln.record[ln.fields[f.role]] ?? "")]));
  const [vals, setVals] = useState<Record<string, string>>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setVals(initial()); setErr(null); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const changed = Object.fromEntries(Object.entries(vals).filter(([r, v]) => v !== String(ln.record[ln.fields[r]] ?? "")));
      if (!Object.keys(changed).length) { onClose(); return; }
      const p = await api(`/api/orders/line/${ln.id}`, { method: "PATCH", json: { values: changed } });
      toast(`Order ${ln.order_no} updated`);
      onSaved(p?.lines ? p : undefined);
      onClose();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  const today = new Date().toISOString().slice(0, 10);
  return (
    <Modal open={open} onClose={onClose} title={`Update progress · Order #${ln.order_no}`} width="max-w-xl"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save} icon={<ArrowRight className="size-4" />}>Save changes</Button></>}>
      {err && <div className="mb-3"><ErrorBox message={err} /></div>}
      <p className="mb-4 text-[13px] text-muted">Changes are written to the order book (with an audit trail) and the live status is recalculated instantly.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => (
          <Field key={f.role} label={f.label} hint={<span>Column “{ln.fields[f.role]}”</span>}>
            <div className="flex gap-1.5">
              <Input type={f.type === "date" ? "date" : f.type === "number" ? "number" : "text"} min={f.type === "number" ? 0 : undefined}
                value={vals[f.role] ?? ""} onChange={(e) => setVals((v) => ({ ...v, [f.role]: e.target.value }))} />
              {f.type === "date" && <Button type="button" size="sm" variant="ghost" className="h-9" onClick={() => setVals((v) => ({ ...v, [f.role]: today }))}>Today</Button>}
            </div>
          </Field>
        ))}
      </div>
    </Modal>
  );
}
