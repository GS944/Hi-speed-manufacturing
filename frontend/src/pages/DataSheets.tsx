import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Archive, ArchiveRestore, ChevronDown, ChevronRight, Download, FileSpreadsheet, Loader2, RefreshCw, Table2, Trash2, UploadCloud } from "lucide-react";
import { api, download, upload } from "../lib/api";
import { useApi } from "../lib/hooks";
import { fmtBytes, fmtDateTime } from "../lib/format";
import { Badge, Button, Card, ConfirmDialog, Empty, ErrorBox, Field, Loading, Modal, Notice, PageHeader, Select, cx, useToast } from "../components/ui";
import { StorageMeter } from "./Dashboard";

const ROLE_TONE: Record<string, "good" | "info" | "warning" | "neutral"> = { orders: "good", job_work_ledger: "info", document_template: "warning" };

export default function DataSheets() {
  const toast = useToast();
  const { data: files, error, loading, reload } = useApi<any[]>("/api/files");
  const { data: storage, reload: reloadStorage } = useApi<any>("/api/storage");
  const processing = files?.some((f) => f.status === "processing");
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(() => { reload(true); reloadStorage(true); }, 2500);
    return () => clearInterval(t);
  }, [processing, reload, reloadStorage]);

  const [confirm, setConfirm] = useState<{ kind: "delete" | "archive"; file: any } | null>(null);
  const [busy, setBusy] = useState(false);

  const act = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      if (confirm.kind === "delete") await api(`/api/files/${confirm.file.id}`, { method: "DELETE" });
      else await api(`/api/files/${confirm.file.id}/archive`, { method: "POST" });
      toast(confirm.kind === "delete" ? "File deleted" : "File archived - its data is no longer used");
      setConfirm(null);
      reload(true);
      reloadStorage(true);
    } catch (e: any) { toast(e.message, "critical"); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Data Sheets" subtitle="Upload the workbooks your team maintains. Tables, columns and their meaning are detected automatically - nothing is hard-coded." />
      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <Uploader files={files || []} onDone={() => { reload(true); reloadStorage(true); }} />
        <Card title="Storage">{storage ? <StorageMeter s={storage} /> : <Loading />}
          {storage && <p className="mt-3 text-[12px] text-muted">Quota is configurable (STORAGE_QUOTA_GB). Max upload {storage.max_upload_mb} MB per file.</p>}
        </Card>
      </div>
      <div className="mt-4 space-y-3">
        {error && <ErrorBox message={error} onRetry={() => reload()} />}
        {loading && !files && <Loading />}
        {files && files.length === 0 && <Card><Empty icon={<FileSpreadsheet className="size-6" />} title="No data sheets yet">Upload the order sheet and annexure workbooks to get started.</Empty></Card>}
        {files?.map((f) => <FileCard key={f.id} f={f} onChanged={() => { reload(true); reloadStorage(true); }} onAsk={(kind) => setConfirm({ kind, file: f })} />)}
      </div>
      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} busy={busy} danger={confirm?.kind === "delete"}
        title={confirm?.kind === "delete" ? "Delete file permanently?" : "Archive file?"}
        confirmLabel={confirm?.kind === "delete" ? "Delete" : "Archive"} onConfirm={act}
        message={confirm?.kind === "delete"
          ? <>“{confirm?.file.name}” and all rows, edits and mappings derived from it will be removed. This cannot be undone.</>
          : <>“{confirm?.file.name}” will stop feeding the dashboard and tracker. You can restore it later.</>} />
    </>
  );
}

function Uploader({ files, onDone }: { files: any[]; onDone: () => void }) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [replace, setReplace] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [version, setVersion] = useState<{ file: File; detail: any } | null>(null);

  const sendOne = async (file: File, opts: { replaceId?: string; keepBoth?: boolean } = {}) => {
    const form = new FormData();
    form.append("file", file);
    if (opts.replaceId) form.append("replace_file_id", opts.replaceId);
    if (opts.keepBoth) form.append("keep_both", "true");
    try {
      setProgress(0);
      await upload("/api/files", form, setProgress);
      toast(`${file.name} uploaded - analysing…`);
    } catch (e: any) {
      if (e.status === 409 && e.detail?.code === "possible_new_version") setVersion({ file, detail: e.detail });
      else setErr(`${file.name}: ${e.message}`);
    }
  };

  const send = async (fl: FileList | null) => {
    if (!fl?.length) return;
    setErr(null);
    for (const file of Array.from(fl)) await sendOne(file, { replaceId: replace || undefined });
    setProgress(null);
    setReplace("");
    if (input.current) input.current.value = "";
    onDone();
  };

  const active = files.filter((f) => f.status !== "archived");
  return (
    <Card title="Upload workbook" subtitle=".xlsx, .xls, .xlsm or .csv">
      <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); send(e.dataTransfer.files); }}
        onClick={() => progress === null && input.current?.click()} role="button" tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        className={cx("flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-9 text-center transition-colors",
          drag ? "border-primary bg-primary-soft" : "border-line-strong hover:border-primary hover:bg-surface-2")}>
        {progress === null ? <UploadCloud className="mb-2 size-8 text-primary" /> : <Loader2 className="mb-2 size-8 animate-spin text-primary" />}
        <p className="font-medium">{progress === null ? "Drop files here or click to browse" : `Uploading… ${progress}%`}</p>
        <p className="mt-1 text-[12.5px] text-muted">Each sheet is segmented into tables, classified by a neural network and indexed for live tracking.</p>
        {progress !== null && <div className="mt-3 h-1.5 w-64 overflow-hidden rounded-full bg-surface-3"><div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} /></div>}
        <input ref={input} type="file" multiple accept=".xlsx,.xls,.xlsm,.csv" className="hidden" onChange={(e) => send(e.target.files)} />
      </div>
      {active.length > 0 && (
        <Field className="mt-4" label="This upload is a newer version of…" hint="The previous version is archived (kept for history) so data is never double-counted.">
          <Select value={replace} onChange={(e) => setReplace(e.target.value)} className="w-full">
            <option value="">— A new, separate workbook —</option>
            {active.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </Select>
        </Field>
      )}
      {err && <div className="mt-3"><ErrorBox message={err} /></div>}
      <Modal open={!!version} onClose={() => setVersion(null)} title="New version of an existing workbook?"
        footer={<>
          <Button variant="ghost" onClick={() => setVersion(null)}>Cancel</Button>
          <Button onClick={async () => { const v = version!; setVersion(null); await sendOne(v.file, { keepBoth: true }); setProgress(null); onDone(); }}>Keep both</Button>
          <Button variant="primary" onClick={async () => { const v = version!; setVersion(null); await sendOne(v.file, { replaceId: String(v.detail.file_id) }); setProgress(null); onDone(); }}>Replace previous version</Button>
        </>}>
        <p className="text-[13.5px] text-ink-2">{version?.detail.message}</p>
        <p className="mt-2 text-[13px] text-muted">Replacing archives “{version?.detail.file_name}” so its orders are not counted twice. Keep both only if the files hold different orders (for example, different financial years).</p>
      </Modal>
    </Card>
  );
}

function FileCard({ f, onChanged, onAsk }: { f: any; onChanged: () => void; onAsk: (k: "delete" | "archive") => void }) {
  const toast = useToast();
  const [open, setOpen] = useState(f.status !== "archived");
  const tables = (f.tables || []) as any[];
  const main = tables.filter((t) => ["orders", "job_work_ledger", "document_template", "customer_master", "vendor_master", "price_list"].includes(t.role));
  const minor = tables.filter((t) => !main.includes(t));
  const restore = async () => { await api(`/api/files/${f.id}/archive?restore=true`, { method: "POST" }).catch((e) => toast(e.message, "critical")); onChanged(); };
  const reprocess = async () => { await api(`/api/files/${f.id}/reprocess`, { method: "POST" }).catch((e) => toast(e.message, "critical")); toast("Re-analysing file…", "info"); onChanged(); };

  return (
    <section className={cx("card", f.status === "archived" && "opacity-70")}>
      <div className="flex flex-wrap items-center gap-3 px-5 py-3.5">
        <button onClick={() => setOpen((o) => !o)} className="text-muted hover:text-ink" aria-label={open ? "Collapse" : "Expand"}>{open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</button>
        <FileSpreadsheet className="size-5 text-good" />
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold">{f.name}</div>
          <div className="text-[12px] text-muted">{fmtBytes(f.size_bytes)} · uploaded {fmtDateTime(f.uploaded_at)} by {f.uploaded_by} · {tables.length} tables detected</div>
        </div>
        {f.status === "processing" && <Badge tone="info"><Loader2 className="size-3 animate-spin" /> Analysing</Badge>}
        {f.status === "ready" && <Badge tone="good">Active</Badge>}
        {f.status === "archived" && <Badge>Archived</Badge>}
        {f.status === "error" && <Badge tone="critical">Failed</Badge>}
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" title="Download original" onClick={() => download(`/api/files/${f.id}/download`, f.name)}><Download className="size-4" /></Button>
          {f.status !== "archived" && <Button size="sm" variant="ghost" title="Re-analyse" onClick={reprocess}><RefreshCw className="size-4" /></Button>}
          {f.status === "archived"
            ? <Button size="sm" variant="ghost" title="Restore" onClick={restore}><ArchiveRestore className="size-4" /></Button>
            : <Button size="sm" variant="ghost" title="Archive" onClick={() => onAsk("archive")}><Archive className="size-4" /></Button>}
          <Button size="sm" variant="ghost" title="Delete" onClick={() => onAsk("delete")} className="hover:text-critical"><Trash2 className="size-4" /></Button>
        </div>
      </div>
      {f.status === "error" && <div className="px-5 pb-4"><ErrorBox message={f.error} /></div>}
      {open && tables.length > 0 && (
        <div className="border-t border-line">
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-[13px]">
            <thead className="bg-surface-2 text-left text-[12px] text-muted"><tr><th className="px-5 py-2">Table</th><th className="px-3">Detected as</th><th className="px-3 text-right">Rows</th><th className="px-3 text-right">Cols</th><th className="px-3">Data quality</th><th className="px-5" /></tr></thead>
            <tbody>
              {[...main, ...minor].map((t) => (
                <tr key={t.id} className={cx("border-t border-line", !main.includes(t) && "text-muted")}>
                  <td className="px-5 py-2.5"><div className="font-medium text-ink">{t.sheet}</div><div className="text-[12px] text-muted">Range {t.range}</div></td>
                  <td className="px-3"><Badge tone={ROLE_TONE[t.role] || "neutral"}>{t.role_label}</Badge>
                    {t.kind === "table" && !["lookup_list", "unknown"].includes(t.role) && <span className="ml-2 text-[12px] text-muted tabular" title="Classifier confidence">{Math.round(t.confidence * 100)}%</span>}</td>
                  <td className="px-3 text-right tabular">{t.kind === "form" ? "—" : t.rows.toLocaleString()}</td>
                  <td className="px-3 text-right tabular">{t.kind === "form" ? "—" : t.columns}</td>
                  <td className="px-3">{t.quality_score != null ? (
                    <span className="inline-flex items-center gap-2"><span className={cx("font-semibold tabular", t.quality_score >= 95 ? "text-good" : t.quality_score >= 80 ? "text-warning" : "text-critical")}>{t.quality_score}</span>
                      {t.issue_count > 0 && <span className="text-[12px] text-muted">{t.issue_count.toLocaleString()} flagged</span>}</span>) : <span className="text-muted">—</span>}</td>
                  <td className="px-5 text-right"><Link to={`/data/tables/${t.id}`} className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline"><Table2 className="size-4" /> Open</Link></td>
                </tr>))}
            </tbody></table></div>
          {f.status === "ready" && main.length === 0 && <div className="p-4"><Notice tone="warning">No order book or annexure ledger was recognised in this file. Open a table and set its type in the column mapping tab.</Notice></div>}
        </div>
      )}
    </section>
  );
}
