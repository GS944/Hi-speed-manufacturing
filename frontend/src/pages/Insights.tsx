import { useState } from "react";
import { Link } from "react-router-dom";
import { Activity, BrainCircuit, GitMerge, MessageSquareText, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { api } from "../lib/api";
import { useApi } from "../lib/hooks";
import { fmtDate, fmtMoney, fmtNum } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, cx, useToast } from "../components/ui";

export default function Insights() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<any>("/api/insights");
  const { data: quality } = useApi<any[]>("/api/quality");
  const [busy, setBusy] = useState(false);

  const retrain = async () => {
    setBusy(true);
    try { await api("/api/insights/retrain", { method: "POST" }); toast("Models retrained"); reload(true); }
    catch (e: any) { toast(e.message, "critical"); } finally { setBusy(false); }
  };

  if (loading && !data) return <Loading label="Loading models…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const cm = data.column_model, eta = data.eta, an = data.anomaly;
  return (
    <>
      <PageHeader title="Intelligence" subtitle="Every model runs on this server - no external AI service and no data leaves your premises."
        actions={<Button loading={busy} icon={<RefreshCw className="size-4" />} onClick={retrain}>Retrain all models</Button>} />

      <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-4">
        <ModelCard icon={<BrainCircuit className="size-5" />} title="Column understanding" algo={cm.architecture}
          what="Reads each column's header and values to decide what it means (order number, due date, operation…), so any sheet layout works."
          metrics={[["Hold-out accuracy", `${(cm.holdout_accuracy * 100).toFixed(1)}%`], ["Training columns", fmtNum(cm.n_train)], ["Admin corrections learned", fmtNum(cm.n_feedback)], ["Last trained", cm.trained_at?.replace("T", " ")]]} />
        <ModelCard icon={<Activity className="size-5" />} title="Completion-date forecast" algo={eta.algorithm || "Gradient boosting"}
          what="Learns real lead times from completed orders to predict when each live order will be despatched and flag likely-late ones."
          metrics={eta.trained ? [["Mean error (5-fold CV)", `±${eta.cv_mae_days} days`], ["Naive baseline error", `±${eta.baseline_mae_days} days`], ["Improvement", `${eta.improvement_pct}%`], ["Trained on", `${fmtNum(eta.samples)} orders`]] : [["Status", eta.reason]]} />
        <ModelCard icon={<TriangleAlert className="size-5" />} title="Cost anomaly detection" algo={an.algorithm || "Isolation Forest"}
          what="Flags job-work entries whose unit cost is far from what that operation normally costs - typos, wrong rates or price changes."
          metrics={an.trained ? [["Entries analysed", fmtNum(an.entries)], ["Flagged", fmtNum(an.flagged)], ["Operations profiled", fmtNum(an.operations)]] : [["Status", an.reason]]} />
        <ModelCard icon={<MessageSquareText className="size-5" />} title="Plain-English search" algo={data.nlq.algorithm}
          what="Understands questions typed in the top bar and turns them into filters over live data."
          metrics={[["Intents", String(data.nlq.intents.length)], ["Examples", "“emergency orders pending for taegutec”"]]} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Unusual job-work costs" subtitle="Review and correct these in the annexure ledger if they are entry errors">
          {data.anomalies.length === 0 ? <Empty title="No anomalies" /> : (
            <div className="max-h-[520px] overflow-auto">
              <table className="w-full min-w-[760px] text-[13px]">
                <thead className="sticky top-0 bg-surface text-left text-[12px] text-muted"><tr><th className="py-2 pr-3">DC</th><th className="pr-3">Date</th><th className="pr-3">Order</th><th className="pr-3">Operation</th><th className="pr-3">Vendor</th><th className="pr-3 text-right">Unit cost</th><th className="pr-3 text-right">Typical</th><th className="text-right">Deviation</th></tr></thead>
                <tbody>{data.anomalies.map((a: any) => (
                  <tr key={a.id} className="border-t border-line">
                    <td className="py-2 pr-3 tabular"><Link className="text-primary hover:underline" to={`/data/tables/${a.table_id}`}>{a.doc_no}</Link></td>
                    <td className="whitespace-nowrap pr-3 tabular">{fmtDate(a.issue_date)}</td>
                    <td className="pr-3">{a.refs.map((r: string) => <Link key={r} to={`/track/${r}`} className="mr-1 text-primary hover:underline">#{r}</Link>)}</td>
                    <td className="pr-3">{a.operation}</td>
                    <td className="max-w-[180px] truncate pr-3 text-ink-2">{a.vendor}</td>
                    <td className="pr-3 text-right font-semibold tabular">{fmtMoney(a.unit_cost)}</td>
                    <td className="pr-3 text-right tabular text-ink-2">{fmtMoney(a.typical_unit_cost)}</td>
                    <td className="text-right"><Badge tone={a.robust_z > 0 ? "critical" : "warning"}>{a.robust_z > 0 ? "▲" : "▼"} {Math.abs(a.robust_z).toFixed(1)}σ</Badge></td>
                  </tr>))}</tbody>
              </table>
            </div>)}
        </Card>
        <div className="space-y-4">
          <Card title="Data quality" subtitle="Validation of every loaded order book and ledger">
            {!quality ? <Loading /> : quality.length === 0 ? <Empty title="No tables checked yet" /> : (
              <div className="divide-y divide-line">
                {quality.map((q) => (
                  <Link key={q.table_id} to={`/data/tables/${q.table_id}`} className="flex items-center gap-3 py-2.5 hover:bg-surface-2">
                    <ShieldCheck className={cx("size-4", q.score >= 95 ? "text-good" : q.score >= 80 ? "text-warning" : "text-critical")} />
                    <div className="min-w-0 flex-1"><div className="truncate text-[13px] font-medium">{q.title}</div><div className="truncate text-[12px] text-muted">{q.file}</div></div>
                    <span className="font-semibold tabular">{q.score}</span>
                  </Link>))}
              </div>)}
          </Card>
          <Card title="Merged spelling variants" subtitle="Entity resolution (union-find over fuzzy matches)">
            <div className="max-h-[300px] space-y-3 overflow-y-auto">
              {Object.entries(data.canonical_groups).flatMap(([role, groups]: [string, any]) => groups.map((g: any) => (
                <div key={role + g.canonical} className="text-[13px]">
                  <div className="flex items-center gap-1.5 font-medium"><GitMerge className="size-3.5 text-primary" />{g.canonical} <span className="text-[11.5px] font-normal text-muted">({role.replace(/_/g, " ")})</span></div>
                  <div className="ml-5 text-[12px] text-muted">{g.variants.join(" · ")}</div>
                </div>)))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function ModelCard({ icon, title, algo, what, metrics }: { icon: React.ReactNode; title: string; algo: string; what: string; metrics: [string, string][] }) {
  return (
    <section className="card flex flex-col p-5">
      <div className="flex items-center gap-2.5"><span className="rounded-lg bg-primary-soft p-2 text-primary">{icon}</span><h3 className="font-semibold">{title}</h3></div>
      <p className="mt-2 text-[13px] text-ink-2">{what}</p>
      <p className="mt-2 text-[12px] text-muted">{algo}</p>
      <dl className="mt-auto space-y-1.5 pt-4 text-[13px]">
        {metrics.map(([k, v]) => <div key={k} className="flex justify-between gap-3"><dt className="text-muted">{k}</dt><dd className="text-right font-medium tabular">{v}</dd></div>)}
      </dl>
    </section>
  );
}
