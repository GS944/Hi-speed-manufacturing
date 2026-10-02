import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowDown, ArrowUp, Download, FilterX, Search } from "lucide-react";
import { download } from "../lib/api";
import { useApi, useDebounced } from "../lib/hooks";
import { fmtDate, fmtNum } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Input, Loading, PageHeader, Pagination, Select, StatusPill, cx, useToast } from "../components/ui";

const COLS: { key: string; label: string; sortable?: boolean; className?: string }[] = [
  { key: "order_no", label: "Order", sortable: true },
  { key: "status", label: "Status", sortable: true },
  { key: "stage", label: "Stage / activity", sortable: true },
  { key: "customer", label: "Customer", sortable: true },
  { key: "item", label: "Item" },
  { key: "order_qty", label: "Qty", sortable: true, className: "text-right" },
  { key: "order_date", label: "Ordered", sortable: true },
  { key: "due_date", label: "Due", sortable: true },
  { key: "eta", label: "ETA (ML)" },
];

export default function Orders() {
  const nav = useNavigate();
  const toast = useToast();
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState(sp.get("q") || "");
  const dq = useDebounced(q, 300);
  const { data: facets } = useApi<any>("/api/orders/facets");
  const page = Number(sp.get("page") || 1);
  const sort = sp.get("sort") || "order_date";
  const dir = sp.get("dir") || "desc";

  const query = useMemo(() => {
    const p = new URLSearchParams(sp);
    if (dq) p.set("q", dq); else p.delete("q");
    p.set("size", "50");
    return p.toString();
  }, [sp, dq]);
  const { data, error, loading, reload } = useApi<any>(`/api/orders?${query}`);

  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(sp);
    if (v) p.set(k, v); else p.delete(k);
    if (k !== "page") p.delete("page");
    setSp(p, { replace: true });
  };
  const toggleSort = (k: string) => {
    const p = new URLSearchParams(sp);
    p.set("sort", k);
    p.set("dir", sort === k && dir === "desc" ? "asc" : "desc");
    p.delete("page");
    setSp(p, { replace: true });
  };
  const active = ["status", "customer", "priority", "category", "stage", "risk"].filter((k) => sp.get(k));

  return (
    <>
      <PageHeader title="Orders" subtitle="Every order line with its computed live status. Click a row to open the live tracker."
        actions={<Button icon={<Download className="size-4" />} onClick={() => download(`/api/orders/export?${query}`, "orders.csv").catch((e) => toast(e.message, "critical"))}>Export CSV</Button>} />
      <Card bodyClass="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search order no., item, customer, PO…" className="pl-9" aria-label="Search orders" />
          </div>
          <Select value={sp.get("status") || ""} onChange={(e) => set("status", e.target.value)} aria-label="Status">
            <option value="">All statuses</option><option value="live">Live</option><option value="completed">Completed</option><option value="overdue">Overdue</option>
          </Select>
          <Select value={sp.get("customer") || ""} onChange={(e) => set("customer", e.target.value)} aria-label="Customer" className="max-w-[200px]">
            <option value="">All customers</option>{facets?.customers.map((c: string) => <option key={c}>{c}</option>)}
          </Select>
          <Select value={sp.get("priority") || ""} onChange={(e) => set("priority", e.target.value)} aria-label="Priority">
            <option value="">All priorities</option>{facets?.priorities.map((c: string) => <option key={c}>{c}</option>)}
          </Select>
          <Select value={sp.get("category") || ""} onChange={(e) => set("category", e.target.value)} aria-label="Category" className="max-w-[180px]">
            <option value="">All categories</option>{facets?.categories.map((c: string) => <option key={c}>{c}</option>)}
          </Select>
          <Select value={sp.get("stage") || ""} onChange={(e) => set("stage", e.target.value)} aria-label="Stage">
            <option value="">All stages</option>{facets?.stages.map((c: string) => <option key={c}>{c}</option>)}
          </Select>
          <Select value={sp.get("risk") || ""} onChange={(e) => set("risk", e.target.value)} aria-label="Late risk">
            <option value="">Any risk</option><option value="high">High late risk</option><option value="medium">Medium late risk</option><option value="low">Low late risk</option>
          </Select>
          {(active.length > 0 || q) && <Button variant="ghost" icon={<FilterX className="size-4" />} onClick={() => { setQ(""); setSp(new URLSearchParams(), { replace: true }); }}>Clear</Button>}
        </div>
        {error && <div className="p-4"><ErrorBox message={error} onRetry={() => reload()} /></div>}
        {loading && !data ? <Loading /> : data && (
          data.rows.length === 0 ? <Empty title="No orders match these filters" /> : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1100px] text-[13px]">
                  <thead className="sticky top-0 bg-surface-2 text-left text-[12px] text-muted">
                    <tr>{COLS.map((c) => (
                      <th key={c.key} className={cx("px-4 py-2.5 font-medium", c.className)}>
                        {c.sortable ? (
                          <button onClick={() => toggleSort(c.key)} className="inline-flex items-center gap-1 hover:text-ink">
                            {c.label}{sort === c.key && (dir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
                          </button>) : c.label}
                      </th>))}</tr>
                  </thead>
                  <tbody className={cx(loading && "opacity-60")}>
                    {data.rows.map((r: any) => (
                      <tr key={r.id} onClick={() => nav(`/track/${r.order_no}`)} className="cursor-pointer border-t border-line hover:bg-surface-2">
                        <td className="px-4 py-2.5 font-semibold tabular">#{r.order_no}</td>
                        <td className="px-4"><StatusPill status={r.status} /></td>
                        <td className="max-w-[300px] px-4">
                          <div className="truncate font-medium">{r.stage}</div>
                          <div className="truncate text-[12px] text-muted" title={r.activity}>{r.activity}</div>
                        </td>
                        <td className="px-4">{r.customer}</td>
                        <td className="max-w-[240px] truncate px-4 text-ink-2" title={r.item}>{r.item}
                          {r.urgent && <Badge tone="warning" className="ml-1.5">{r.priority}</Badge>}</td>
                        <td className="px-4 text-right tabular">{fmtNum(r.order_qty)}</td>
                        <td className="px-4 tabular">{fmtDate(r.order_date)}</td>
                        <td className="px-4 tabular">
                          {fmtDate(r.due_date)}
                          {r.overdue_days > 0 && <div className="text-[11.5px] font-medium text-critical">{r.overdue_days}d overdue</div>}
                        </td>
                        <td className="px-4 tabular">{r.eta ? <span className={cx(r.eta.late_risk === "high" ? "text-critical" : r.eta.late_risk === "medium" ? "text-warning" : "")}>{fmtDate(r.eta.expected, false)}</span> : <span className="text-muted">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} size={data.size} total={data.total} onPage={(p) => set("page", String(p))} />
            </>
          ))}
      </Card>
    </>
  );
}
