import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CheckCircle2, Download, FileSpreadsheet, FileText, History, Printer, Search, Send } from "lucide-react";
import { api, download } from "../lib/api";
import { useApi } from "../lib/hooks";
import { fmtDateTime, fmtMoney, fmtNum } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Input, Loading, Modal, PageHeader, Pagination, Tabs, cx, useToast } from "../components/ui";

type Doc = "annexure" | "route";

export default function Annexure() {
  const { orderNo } = useParams();
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const [tab, setTab] = useState<"print" | "history">(sp.get("tab") === "history" ? "history" : "print");
  const doc: Doc = sp.get("doc") === "route" ? "route" : "annexure";
  const [q, setQ] = useState(orderNo || "");
  useEffect(() => setQ(orderNo || ""), [orderNo]);

  return (
    <>
      <PageHeader title="Annexure & Print" subtitle="Generate the annexure (job-work details) or route card for an order, download it, and submit it to the printer." />
      <Tabs tabs={[{ key: "print", label: <span className="inline-flex items-center gap-1.5"><Printer className="size-4" />Prepare & print</span> },
        { key: "history", label: <span className="inline-flex items-center gap-1.5"><History className="size-4" />Print history</span> }]}
        value={tab} onChange={setTab} />
      {tab === "history" ? <PrintHistory /> : (
        <>
          <form className="card mb-4 flex flex-wrap items-center gap-3 p-3" onSubmit={(e) => { e.preventDefault(); if (q.trim()) nav(`/annexure/${encodeURIComponent(q.trim())}${doc === "route" ? "?doc=route" : ""}`); }}>
            <div className="relative min-w-[220px] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Order number" className="pl-9" aria-label="Order number" />
            </div>
            <div className="inline-flex rounded-lg border border-line p-0.5">
              {(["annexure", "route"] as Doc[]).map((d) => (
                <button type="button" key={d} onClick={() => { const p = new URLSearchParams(sp); d === "route" ? p.set("doc", "route") : p.delete("doc"); setSp(p, { replace: true }); }}
                  className={cx("rounded-md px-3 py-1.5 text-[13px] font-medium", doc === d ? "bg-primary text-on-primary" : "text-ink-2 hover:bg-surface-3")}>
                  {d === "annexure" ? "Annexure" : "Route card"}
                </button>))}
            </div>
            <Button type="submit" variant="primary">Load</Button>
          </form>
          {!orderNo ? <Card><Empty icon={<FileText className="size-6" />} title="Enter an order number">The document is built from the order book and every annexure (job-work) entry linked to that order.</Empty></Card>
            : doc === "annexure" ? <AnnexureDoc orderNo={orderNo} /> : <RouteCardDoc orderNo={orderNo} />}
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------ annexure
function AnnexureDoc({ orderNo }: { orderNo: string }) {
  const toast = useToast();
  const { data, error, loading } = useApi<any>(`/api/annexure/${encodeURIComponent(orderNo)}`);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [copies, setCopies] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState<any>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (data) {
      setSelected(new Set(data.rows.map((r: any) => r.id)));
      setCopies(data.company.copies.slice(0, 1));
      setSubmitted(null);
    }
  }, [data]);

  const view = useMemo(() => {
    if (!data) return null;
    const src = submitted?.payload || data;
    const rows = submitted ? src.rows : src.rows.filter((r: any) => selected.has(r.id)).map((r: any, i: number) => ({ ...r, sl: i + 1 }));
    const totals = { qty: rows.reduce((a: number, r: any) => a + (r.qty || 0), 0), amount: rows.reduce((a: number, r: any) => a + (r.amount || 0), 0),
      value_of_goods: rows.reduce((a: number, r: any) => a + (r.value_of_goods || 0), 0) };
    return { ...src, rows, totals };
  }, [data, selected, submitted]);

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data || !view) return null;

  const ids = [...selected].join(",");
  const allSelected = selected.size === data.rows.length;
  const dl = (fmt: "pdf" | "xlsx") => download(`/api/annexure/${encodeURIComponent(orderNo)}/download?format=${fmt}&copies=${copies.length > 1 ? "all" : "original"}${allSelected ? "" : `&entries=${ids}`}`,
    `Annexure-${orderNo}.${fmt}`).catch((e) => toast(e.message, "critical"));

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api(`/api/annexure/${encodeURIComponent(orderNo)}/submit`, { method: "POST", json: { entry_ids: allSelected ? null : [...selected], copies } });
      setSubmitted(r);
      setConfirm(false);
      toast(`Submitted as ${r.doc_no}. Sending to printer…`);
      setTimeout(() => window.print(), 350);
    } catch (e: any) {
      toast(e.message, "critical");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-4 2xl:grid-cols-[340px_1fr]">
      <div className="grid content-start gap-4 md:grid-cols-3 2xl:grid-cols-1 no-print">
        <Card title="Entries to include" subtitle={`${selected.size} of ${data.rows.length} job-work entries`}>
          {data.rows.length === 0 ? <p className="text-[13px] text-muted">No annexure entries are linked to this order yet. The annexure will print with order details only.</p> : (
            <div className="max-h-[260px] space-y-1 overflow-y-auto">
              <label className="flex items-center gap-2 border-b border-line pb-2 text-[13px] font-medium">
                <input type="checkbox" checked={allSelected} disabled={!!submitted} onChange={() => setSelected(allSelected ? new Set() : new Set(data.rows.map((r: any) => r.id)))} /> Select all
              </label>
              {data.rows.map((r: any) => (
                <label key={r.id} className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-1.5 text-[13px] hover:bg-surface-2">
                  <input type="checkbox" className="mt-0.5" disabled={!!submitted} checked={selected.has(r.id)}
                    onChange={() => setSelected((s) => { const n = new Set(s); n.has(r.id) ? n.delete(r.id) : n.add(r.id); return n; })} />
                  <span className="min-w-0"><span className="font-medium">DC {r.doc_no}</span> · {r.operation}<br />
                    <span className="text-[12px] text-muted">{r.issue_date} · {r.vendor}</span></span>
                </label>))}
            </div>)}
        </Card>
        <Card title="Copies" subtitle="From your delivery-challan template">
          <div className="space-y-1.5">
            {data.company.copies.map((c: string) => (
              <label key={c} className="flex items-center gap-2 text-[13px]">
                <input type="checkbox" disabled={!!submitted} checked={copies.includes(c)} onChange={() => setCopies((x) => x.includes(c) ? x.filter((y) => y !== c) : data.company.copies.filter((y: string) => y === c || x.includes(y)))} /> {c}
              </label>))}
          </div>
        </Card>
        <Card>
          <div className="space-y-2">
            {submitted ? (
              <>
                <div className="flex items-center gap-2 rounded-lg bg-good-soft px-3 py-2 text-[13px] text-good"><CheckCircle2 className="size-4" /> Submitted as <b>{submitted.doc_no}</b></div>
                <Button variant="primary" className="w-full" icon={<Printer className="size-4" />} onClick={() => window.print()}>Print again</Button>
                <Button className="w-full" icon={<Download className="size-4" />} onClick={() => download(submitted.pdf_url, `${submitted.doc_no}.pdf`)}>Download submitted PDF</Button>
                <Button variant="ghost" className="w-full" onClick={() => setSubmitted(null)}>Start a new annexure</Button>
              </>
            ) : (
              <>
                <Button variant="primary" className="w-full" icon={<Send className="size-4" />} disabled={!copies.length} onClick={() => setConfirm(true)}>Submit & print</Button>
                <div className="grid grid-cols-2 gap-2">
                  <Button icon={<FileText className="size-4" />} onClick={() => dl("pdf")}>PDF</Button>
                  <Button icon={<FileSpreadsheet className="size-4" />} onClick={() => dl("xlsx")}>Excel</Button>
                </div>
                <p className="text-[12px] text-muted">Submit assigns a document number, records it in the print history and opens the printer dialog.</p>
              </>
            )}
          </div>
        </Card>
      </div>

      <div className="print-area min-w-0 overflow-x-auto">
        {(submitted?.payload.print_copies || copies.length ? (submitted?.payload.print_copies || copies) : [data.company.copies[0]]).map((c: string, i: number, arr: string[]) => (
          <Fragment key={c}>
            <AnnexurePaper p={view} copy={c} docNo={submitted?.doc_no} />
            {i < arr.length - 1 && <div className="page-break h-4" />}
          </Fragment>))}
      </div>

      <Modal open={confirm} onClose={() => setConfirm(false)} title="Submit annexure to printer"
        footer={<><Button variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button><Button variant="primary" loading={busy} icon={<Printer className="size-4" />} onClick={submit}>Submit & print</Button></>}>
        <p className="text-[13.5px] text-ink-2">Order <b>#{data.order_no}</b> · {selected.size} entr{selected.size === 1 ? "y" : "ies"} · {copies.length} cop{copies.length === 1 ? "y" : "ies"} ({copies.join(", ")}).</p>
        <p className="mt-2 text-[13px] text-muted">A new annexure number will be issued and logged. Choose your printer in the dialog that opens next.</p>
      </Modal>
    </div>
  );
}

function AnnexurePaper({ p, copy, docNo }: { p: any; copy: string; docNo?: string }) {
  const co = p.company;
  return (
    <div className="paper card mx-auto min-w-[980px] max-w-[1180px] p-8 text-[12px]">
      <div className="flex items-start justify-between border-b-2 border-slate-900 pb-3">
        <div>
          <div className="text-[18px] font-bold text-slate-900">{co.name}</div>
          {co.address.map((a: string) => <div key={a} className="text-[11.5px] text-slate-600">{a}</div>)}
          {co.gstin && <div className="text-[11.5px] text-slate-600">GSTIN: {co.gstin}</div>}
        </div>
        <div className="text-right text-[11.5px] font-semibold text-slate-600">
          <div className="text-slate-900">{copy}</div>
          <div>Generated: {p.generated_on}</div>
          {docNo ? <div>Doc No: <span className="text-slate-900">{docNo}</span></div> : <div className="font-normal italic text-slate-400">Draft — not yet submitted</div>}
        </div>
      </div>
      <h3 className="my-3 text-center text-[14px] font-bold tracking-wide text-slate-900">{p.title}</h3>
      <table className="mb-4 w-full border-collapse text-[11.5px]">
        <tbody>
          {chunk(Object.entries(p.order), 3).map((row, i) => (
            <tr key={i}>{row.map(([k, v]) => (
              <Fragment key={k}><th className="w-[12%] border border-slate-300 bg-slate-100 px-2 py-1 text-left font-semibold text-slate-800">{k}</th>
                <td className="w-[21%] border border-slate-300 px-2 py-1 text-slate-900">{String(v)}</td></Fragment>))}</tr>))}
        </tbody>
      </table>
      <table className="w-full border-collapse text-[11px]">
        <thead><tr>{p.columns.map((c: any) => <th key={c.key} className="border border-slate-400 bg-slate-200 px-1.5 py-1 text-left font-semibold text-slate-900">{c.label.replace("(Rs.)", "(₹)")}</th>)}</tr></thead>
        <tbody>
          {p.rows.length === 0 && <tr><td colSpan={p.columns.length} className="border border-slate-300 px-2 py-3 text-center text-slate-500">No job-work (annexure) entries recorded for this order.</td></tr>}
          {p.rows.map((r: any) => (
            <tr key={r.id}>{p.columns.map((c: any) => {
              const v = r[c.key];
              const money = ["unit_cost", "amount", "value_of_goods"].includes(c.key);
              return <td key={c.key} className={cx("border border-slate-300 px-1.5 py-1 align-top text-slate-900", money && "text-right tabular",
                c.key === "hrc_result" && v === "OUT OF SPEC" && "bg-red-100 font-semibold text-red-700", c.key === "hrc_result" && v === "OK" && "font-semibold text-green-700", ["issue_date", "inward_date", "doc_no"].includes(c.key) && "whitespace-nowrap")}>
                {money ? (v == null ? "" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2 })) : v ?? ""}</td>;
            })}</tr>))}
          <tr className="bg-slate-100 font-semibold">{p.columns.map((c: any) => (
            <td key={c.key} className={cx("border border-slate-300 px-1.5 py-1 text-slate-900", ["amount", "value_of_goods", "qty"].includes(c.key) && "text-right tabular")}>
              {c.key === "description" ? "TOTAL" : c.key === "qty" ? fmtNum(p.totals.qty) : c.key === "amount" ? fmtMoney(p.totals.amount) : c.key === "value_of_goods" ? fmtMoney(p.totals.value_of_goods) : ""}</td>))}</tr>
        </tbody>
      </table>
      <div className="mt-14 grid grid-cols-3 gap-8 text-[11.5px] text-slate-600">
        {["Prepared by", "Checked by (QC / HRC)", "Authorised Signatory"].map((s) => <div key={s} className="border-t border-slate-500 pt-1.5">{s}</div>)}
      </div>
    </div>
  );
}

const chunk = <T,>(a: T[], n: number) => Array.from({ length: Math.ceil(a.length / n) }, (_, i) => a.slice(i * n, i * n + n));

// ------------------------------------------------------------------ route card
function RouteCardDoc({ orderNo }: { orderNo: string }) {
  const toast = useToast();
  const { data, error, loading } = useApi<any>(`/api/route-card/${encodeURIComponent(orderNo)}`);
  const [docNo, setDocNo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setDocNo(null), [orderNo]);
  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const submit = async () => {
    setBusy(true);
    try {
      const r = await api(`/api/route-card/${encodeURIComponent(orderNo)}/submit`, { method: "POST" });
      setDocNo(r.doc_no);
      toast(`Submitted as ${r.doc_no}. Sending to printer…`);
      setTimeout(() => window.print(), 350);
    } catch (e: any) { toast(e.message, "critical"); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <div className="no-print flex flex-wrap gap-2">
        <Button variant="primary" loading={busy} icon={<Send className="size-4" />} onClick={submit}>Submit & print</Button>
        <Button icon={<FileText className="size-4" />} onClick={() => download(`/api/route-card/${encodeURIComponent(orderNo)}/download`, `RouteCard-${orderNo}.pdf`).catch((e) => toast(e.message, "critical"))}>Download PDF</Button>
        {docNo && <Badge tone="good"><CheckCircle2 className="size-3.5" /> {docNo}</Badge>}
      </div>
      <div className="print-area overflow-x-auto">
        {data.cards.map((c: any, i: number) => (
          <div key={i} className={cx("paper card mx-auto mb-4 min-w-[760px] max-w-[900px] p-8 text-[12px]", i < data.cards.length - 1 && "page-break")}>
            <div className="flex items-baseline justify-between border-b-2 border-slate-900 pb-2">
              <div className="text-[18px] font-bold text-slate-900">{data.title}</div>
              <div className="text-[11.5px] text-slate-600">{docNo ? `Doc No: ${docNo}` : "Draft"} · {data.generated_on}</div>
            </div>
            <table className="mt-3 w-full border-collapse text-[11.5px]"><tbody>
              {chunk([["Number", c.order_no], ["Type", c.type], ["Request", c.request], ["PO Date", c.po_date], ["Delivery Date", c.delivery_date],
                ["Customer Code", c.customer_code], ["Customer", c.customer], ["Customer PO", c.customer_po], ["Spares", c.spares], ["Material", c.material],
                ["Hardness", c.hardness], ["Item", c.item]], 3).map((row, j) => (
                <tr key={j}>{row.map(([k, v]) => <Fragment key={k as string}><th className="border border-slate-300 bg-slate-100 px-2 py-1 text-left text-slate-800">{k}</th><td className="border border-slate-300 px-2 py-1 text-slate-900">{v ?? ""}</td></Fragment>)}</tr>))}
            </tbody></table>
            <table className="mt-3 w-full border-collapse text-center text-[11.5px]"><thead><tr>{["Order Qty", "Issued", "Prod Rej", "Insp Rej", "Actual / Despatch"].map((h) => <th key={h} className="border border-slate-400 bg-slate-200 px-2 py-1 text-slate-900">{h}</th>)}</tr></thead>
              <tbody><tr className="h-9 text-[14px] text-slate-900">{[c.order_qty, c.issued_qty, c.reject_qty, null, c.despatch_qty].map((v, j) => <td key={j} className="border border-slate-300">{v ?? ""}</td>)}</tr></tbody></table>
            <table className="mt-3 w-full border-collapse text-[11.5px]"><thead><tr>{["Operation", "Vendor / Machine", "DC / Date", "Operator", "Supervisor", "Inspector", "Qty"].map((h) => <th key={h} className="border border-slate-400 bg-slate-200 px-2 py-1 text-left text-slate-900">{h}</th>)}</tr></thead>
              <tbody>{[...new Set(["Cutting", "Turn / BM / AM", "HT", "CG / SG", "PKT", ...c.operations.map((o: any) => o.operation).filter(Boolean)])].map((op) => {
                const o = c.operations.find((x: any) => x.operation === op);
                return <tr key={op} className="h-8 text-slate-900"><td className="border border-slate-300 px-2">{op}</td><td className="border border-slate-300 px-2">{o?.vendor ?? ""}</td><td className="border border-slate-300 px-2">{o ? `${o.dc} / ${o.date}` : ""}</td><td className="border border-slate-300" /><td className="border border-slate-300" /><td className="border border-slate-300" /><td className="border border-slate-300" /></tr>;
              })}</tbody></table>
            <div className="mt-3 h-16 border border-slate-300 p-2 text-slate-600">Remarks:</div>
          </div>))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ history
function PrintHistory() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const { data, loading, error } = useApi<any>(`/api/print-jobs?page=${page}&size=25${q ? `&q=${encodeURIComponent(q)}` : ""}`);
  return (
    <Card bodyClass="p-0">
      <div className="border-b border-line p-3"><Input placeholder="Filter by order no. or document no." value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="max-w-sm" /></div>
      {error && <div className="p-4"><ErrorBox message={error} /></div>}
      {loading && !data ? <Loading /> : data && (data.rows.length === 0 ? <Empty icon={<History className="size-6" />} title="Nothing printed yet">Submitted annexures and route cards appear here with their document numbers.</Empty> : (
        <>
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-[13px]">
            <thead className="bg-surface-2 text-left text-[12px] text-muted"><tr><th className="px-4 py-2.5">Document no.</th><th className="px-4">Type</th><th className="px-4">Order</th><th className="px-4 text-right">Entries</th><th className="px-4 text-right">Amount</th><th className="px-4">Submitted</th><th className="px-4">By</th><th className="px-4" /></tr></thead>
            <tbody>{data.rows.map((j: any) => (
              <tr key={j.id} className="border-t border-line">
                <td className="px-4 py-2.5 font-semibold tabular">{j.doc_no}</td>
                <td className="px-4"><Badge tone={j.kind === "annexure" ? "info" : "neutral"}>{j.kind === "annexure" ? "Annexure" : "Route card"}</Badge></td>
                <td className="px-4"><Link to={`/track/${j.order_no}`} className="text-primary hover:underline">#{j.order_no}</Link></td>
                <td className="px-4 text-right tabular">{j.entries}</td>
                <td className="px-4 text-right tabular">{j.amount != null ? fmtMoney(j.amount) : "—"}</td>
                <td className="px-4 tabular">{fmtDateTime(j.created_at)}</td><td className="px-4">{j.created_by}</td>
                <td className="px-4 text-right"><Button size="sm" icon={<Download className="size-3.5" />} onClick={() => download(`/api/print-jobs/${j.id}/pdf`, `${j.doc_no}.pdf`).catch((e) => toast(e.message, "critical"))}>Reprint PDF</Button></td>
              </tr>))}</tbody></table></div>
          <Pagination page={page} size={25} total={data.total} onPage={setPage} />
        </>))}
    </Card>
  );
}
