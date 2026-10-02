import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlarmClock, AlertTriangle, CheckCircle2, Clock4, Database, Factory, Flame, RefreshCw, TrendingUp, Upload } from "lucide-react";
import { useApi } from "../lib/hooks";
import { fmtBytes, fmtCompactMoney, fmtDate, fmtMoney, fmtNum, monthLabel, relDays } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, Stat, StatusPill, cx } from "../components/ui";
import { HBarChart, TrendChart } from "../components/charts";

function ChartOrTable({ chart, table }: { chart: React.ReactNode; table: React.ReactNode }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <div>
      <div className="mb-2 flex justify-end">
        <div className="inline-flex rounded-md border border-line p-0.5 text-[12px]">
          {(["chart", "table"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} className={cx("rounded px-2 py-0.5 capitalize", view === v ? "bg-surface-3 font-medium text-ink" : "text-muted")}>{v}</button>
          ))}
        </div>
      </div>
      {view === "chart" ? chart : table}
    </div>
  );
}

export default function Dashboard() {
  const nav = useNavigate();
  const { data, error, loading, reload } = useApi<any>("/api/dashboard", { poll: 60000 });
  const { data: storage } = useApi<any>("/api/storage");

  if (loading && !data) return <Loading label="Building dashboard…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={() => reload()} />;
  if (!data) return null;
  const k = data.kpi;

  if (!k.total_lines) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <Card><Empty icon={<Database className="size-6" />} title="No order data yet"
          action={<Button variant="primary" icon={<Upload className="size-4" />} onClick={() => nav("/data")}>Upload data sheets</Button>}>
          Upload your order sheet and annexure workbooks. The engine will detect the tables and columns automatically.
        </Empty></Card>
      </>
    );
  }

  const go = (qs: string) => nav(`/orders?${qs}`);
  return (
    <>
      <PageHeader title="Dashboard" subtitle={`${fmtNum(k.total_orders)} orders · ${fmtNum(k.total_lines)} order lines across all loaded order books`}
        actions={<Button icon={<RefreshCw className="size-4" />} onClick={() => reload()}>Refresh</Button>} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Stat label="Live order lines" value={fmtNum(k.live)} tone="good" icon={<span className="live-dot inline-block size-2 rounded-full bg-good" />} hint="Work in progress" onClick={() => go("status=live")} />
        <Stat label="Completed" value={fmtNum(k.completed)} tone="critical" icon={<CheckCircle2 className="size-4" />} hint="Despatched / closed" onClick={() => go("status=completed")} />
        <Stat label="Overdue" value={fmtNum(k.overdue)} icon={<AlarmClock className="size-4" />} hint="Live and past due date" onClick={() => go("status=overdue")} />
        <Stat label="Due in 7 days" value={fmtNum(k.due_7d)} icon={<Clock4 className="size-4" />} hint="Live, due this week" onClick={() => go("status=live&sort=due_date&dir=asc")} />
        <Stat label="Urgent open" value={fmtNum(k.urgent_open)} icon={<Flame className="size-4" />} hint="Emergency requests" onClick={() => go("status=live&priority=Emergency")} />
        <Stat label="At vendors" value={fmtNum(k.at_vendor)} icon={<Factory className="size-4" />} hint="Open job-work DCs" />
        <Stat label="Predicted late" value={fmtNum(k.high_risk)} icon={<TrendingUp className="size-4" />} hint="ML forecast, not yet due" onClick={() => go("risk=high")} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Order intake vs despatch" subtitle="Order lines received and despatched per month">
          <ChartOrTable
            chart={<TrendChart data={data.monthly} xKey="month" xFormat={monthLabel}
              series={[{ key: "received", label: "Received", color: "var(--series-1)" }, { key: "despatched", label: "Despatched", color: "var(--series-2)" }]} />}
            table={<SimpleTable cols={["Month", "Received", "Despatched", "Still live"]} rows={data.monthly.map((m: any) => [monthLabel(m.month), m.received, m.despatched, m.live])} />} />
        </Card>
        <Card title="Live lines by stage" subtitle="Where open work is right now">
          {data.stages.length ? <HBarChart data={data.stages} labelKey="stage" valueKey="count" valueLabel="order lines"
            onSelect={(r) => go(`status=live&stage=${encodeURIComponent(r.stage)}`)} /> : <Empty title="Nothing live" />}
          <p className="mt-2 text-[12px] text-muted">Click a bar to open those orders.</p>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Live lines by customer" subtitle="Top customers with open work">
          <HBarChart data={data.top_customers} labelKey="customer" valueKey="live" valueLabel="live lines"
            onSelect={(r) => go(`status=live&customer=${encodeURIComponent(r.customer)}`)} />
        </Card>
        <Card title="Job-work spend by operation" subtitle="Unit cost × quantity, all annexure entries">
          <HBarChart data={data.operations} labelKey="operation" valueKey="spend" valueLabel="spend" format={fmtCompactMoney} />
        </Card>
        <Card title="Open at vendors" subtitle="Job-work entries not yet received back">
          {data.vendors_open.length ? <HBarChart data={data.vendors_open} labelKey="vendor" valueKey="open" valueLabel="open entries" /> : <Empty title="Nothing at vendors" />}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="At risk of missing the due date" subtitle="Live, not yet due — ETA forecast by the gradient-boosting model"
          actions={<Link to="/orders?risk=high" className="text-[13px] font-medium text-primary hover:underline">View all</Link>}>
          {data.at_risk.length ? (
            <OrderMiniTable rows={data.at_risk} extra={(r) => (
              <span className="text-[12px]">ETA <b className="tabular">{fmtDate(r.eta?.expected, false)}</b> vs due {fmtDate(r.due_date, false)}</span>)} />
          ) : <Empty title="No orders at risk" />}
        </Card>
        <Card title="Latest orders" actions={<Link to="/orders" className="text-[13px] font-medium text-primary hover:underline">All orders</Link>}>
          <OrderMiniTable rows={data.recent} extra={(r) => <span className="text-[12px] text-muted">{fmtDate(r.order_date)}</span>} />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Cost anomalies" subtitle={data.models.anomaly?.algorithm}
          actions={<Link to="/insights" className="text-[13px] font-medium text-primary hover:underline">Review</Link>}>
          {data.anomalies.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="text-left text-[12px] text-muted"><tr><th className="py-1.5 pr-3">DC</th><th className="pr-3">Order</th><th className="pr-3">Operation</th><th className="pr-3">Vendor</th><th className="pr-3 text-right">Unit cost</th><th>Why</th></tr></thead>
                <tbody>{data.anomalies.map((a: any) => (
                  <tr key={a.id} className="border-t border-line">
                    <td className="py-2 pr-3 tabular">{a.doc_no}</td>
                    <td className="pr-3">{a.refs.map((r: string) => <Link key={r} className="mr-1 text-primary hover:underline" to={`/track/${r}`}>#{r}</Link>)}</td>
                    <td className="pr-3">{a.operation}</td><td className="max-w-[180px] truncate pr-3 text-ink-2">{a.vendor}</td>
                    <td className="pr-3 text-right font-medium tabular">{fmtMoney(a.unit_cost)}</td>
                    <td className="text-[12px] text-ink-2">typical {fmtMoney(a.typical_unit_cost)}</td></tr>))}</tbody>
              </table>
            </div>) : <Empty title="No anomalies detected" />}
        </Card>
        <Card title="Storage" subtitle="Data sheets, database and models">
          {storage && <StorageMeter s={storage} />}
          <div className="mt-4 space-y-1.5 text-[13px]">
            <Row k="Despatched this month" v={fmtNum(k.despatched_this_month)} />
            <Row k="Orders this month" v={fmtNum(k.orders_this_month)} />
            <Row k="Job-work spend this month" v={fmtMoney(k.jobwork_spend_month)} />
            <Row k="ETA model error (CV)" v={data.models.eta?.trained ? `±${data.models.eta.cv_mae_days} days` : "not trained"} />
          </div>
        </Card>
      </div>
    </>
  );
}

const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (
  <div className="flex justify-between gap-3"><span className="text-muted">{k}</span><span className="font-medium tabular">{v}</span></div>
);

export function StorageMeter({ s }: { s: any }) {
  const pct = Math.min(100, s.used_pct);
  return (
    <div>
      <div className="flex items-end justify-between">
        <span className="text-[22px] font-semibold tabular">{fmtBytes(s.used_bytes)}</span>
        <span className="text-[13px] text-muted">of {s.quota_gb} GB</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-3" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Storage used">
        <div className={cx("h-full rounded-full", pct > 90 ? "bg-critical" : "bg-primary")} style={{ width: `${Math.max(pct, 0.8)}%` }} />
      </div>
      <div className="mt-2 text-[12px] text-muted">{fmtBytes(s.available_bytes)} available · disk free {fmtBytes(s.disk_free_bytes)}</div>
    </div>
  );
}

function OrderMiniTable({ rows, extra }: { rows: any[]; extra: (r: any) => React.ReactNode }) {
  const nav = useNavigate();
  return (
    <div className="divide-y divide-line">
      {rows.map((r) => (
        <button key={r.id} onClick={() => nav(`/track/${r.order_no}`)} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-surface-2">
          <span className="w-14 shrink-0 font-semibold tabular">#{r.order_no}</span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] text-ink">{r.item}</div>
            <div className="truncate text-[12px] text-muted">{r.customer} · {r.stage}{r.due_date && r.status === "live" ? ` · due ${relDays(r.due_date)}` : ""}</div>
          </div>
          {r.urgent && <Badge tone="warning"><AlertTriangle className="size-3" />{r.priority}</Badge>}
          <div className="hidden shrink-0 sm:block">{extra(r)}</div>
          <StatusPill status={r.status} />
        </button>
      ))}
    </div>
  );
}

function SimpleTable({ cols, rows }: { cols: string[]; rows: any[][] }) {
  return (
    <div className="max-h-[260px] overflow-auto">
      <table className="w-full text-[13px]"><thead className="sticky top-0 bg-surface text-left text-[12px] text-muted"><tr>{cols.map((c) => <th key={c} className="py-1.5 pr-3">{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-line">{r.map((v, j) => <td key={j} className="py-1.5 pr-3 tabular">{v}</td>)}</tr>)}</tbody></table>
    </div>
  );
}
