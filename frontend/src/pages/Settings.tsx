import { useEffect, useState } from "react";
import { KeyRound, LogOut, Save, UserPlus } from "lucide-react";
import { API_BASE, api, apiUrl } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/hooks";
import { fmtDateTime } from "../lib/format";
import { Badge, Button, Card, ConfirmDialog, ErrorBox, Field, Input, Loading, Modal, PageHeader, Pagination, Tabs, useToast } from "../components/ui";
import { StrengthHint } from "./Login";
import { StorageMeter } from "./Dashboard";

type Tab = "company" | "account" | "admins" | "audit" | "system";

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("company");
  return (
    <>
      <PageHeader title="Settings" subtitle="Company details for printed documents, accounts, and the audit trail." />
      <Tabs tabs={[{ key: "company", label: "Company & documents" }, { key: "account", label: "Your account" }, { key: "admins", label: "Users" }, { key: "audit", label: "Audit log" }, { key: "system", label: "System" }]} value={tab} onChange={setTab} />
      {tab === "company" && <Company />}
      {tab === "account" && <Account />}
      {tab === "admins" && <Administrators />}
      {tab === "audit" && <Audit />}
      {tab === "system" && <System />}
    </>
  );
}

function Company() {
  const toast = useToast();
  const { data, loading, error } = useApi<any>("/api/settings");
  const [c, setC] = useState<any>(null);
  const [t, setT] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) { setC({ ...data.company, address: (data.company.address || []).join("\n") }); setT({ ...data.annexure_template, copies: (data.annexure_template.copies || []).join("\n") }); } }, [data]);
  if (loading || !c) return error ? <ErrorBox message={error} /> : <Loading />;
  const save = async () => {
    setBusy(true);
    try {
      await api("/api/settings", { method: "PUT", json: {
        company: { ...c, address: c.address.split("\n") },
        annexure_template: { ...t, copies: t.copies.split("\n") } } });
      toast("Settings saved");
    } catch (e: any) { toast(e.message, "critical"); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Company" subtitle="Pre-filled from your delivery-challan template; printed on every document.">
        <div className="space-y-4">
          <Field label="Company name"><Input value={c.name || ""} onChange={(e) => setC({ ...c, name: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Short name" hint="Used in route-card titles"><Input value={c.short_name || ""} onChange={(e) => setC({ ...c, short_name: e.target.value })} /></Field>
            <Field label="GSTIN"><Input value={c.gstin || ""} onChange={(e) => setC({ ...c, gstin: e.target.value.toUpperCase() })} /></Field>
          </div>
          <Field label="Address" hint="One line per row"><textarea rows={4} value={c.address} onChange={(e) => setC({ ...c, address: e.target.value })}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" /></Field>
        </div>
      </Card>
      <Card title="Annexure / challan" subtitle="Copies printed when an annexure is submitted" actions={<Button variant="primary" loading={busy} icon={<Save className="size-4" />} onClick={save}>Save</Button>}>
        <div className="space-y-4">
          <Field label="Delivery challan title"><Input value={t.title || ""} onChange={(e) => setT({ ...t, title: e.target.value })} /></Field>
          <Field label="Tariff / SAC code"><Input value={t.tariff_code || ""} onChange={(e) => setT({ ...t, tariff_code: e.target.value })} /></Field>
          <Field label="Copy labels" hint="One per line, e.g. ORIGINAL (VENDOR COPY)"><textarea rows={4} value={t.copies} onChange={(e) => setT({ ...t, copies: e.target.value })}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" /></Field>
        </div>
      </Card>
    </div>
  );
}

function Account() {
  const toast = useToast();
  const { username, applySession, logout } = useAuth();
  const [name, setName] = useState(username || "");
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [nw2, setNw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (nw && nw !== nw2) return setErr("The new passwords do not match.");
    setBusy(true);
    try {
      const r = await api("/api/auth/account", { method: "PUT", json: {
        current_password: cur, new_username: name.trim() !== username ? name : null, new_password: nw || null } });
      applySession(r);
      setCur(""); setNw(""); setNw2("");
      toast(nw ? "Account updated. Your other sessions have been signed out." : "Username updated.");
    } catch (ex: any) { setErr(ex.message); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Your account" subtitle="Change your username and/or password. Use any username and password you like - there are no format rules.">
        <form onSubmit={submit} className="space-y-4">
          {err && <ErrorBox message={err} />}
          <Field label="Username"><Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} autoComplete="username" /></Field>
          <Field label="New password" hint="Leave empty to keep your current password."><Input type="password" autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} /></Field>
          {nw && <><Field label="Confirm new password"><Input type="password" autoComplete="new-password" value={nw2} onChange={(e) => setNw2(e.target.value)} required /></Field><StrengthHint password={nw} /></>}
          <Field label="Current password" hint="Required to confirm any change."><Input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required /></Field>
          <Button type="submit" variant="primary" loading={busy} icon={<KeyRound className="size-4" />}>Save changes</Button>
        </form>
      </Card>
      <Card title="Sessions" subtitle="Sign-in sessions expire automatically after a few hours.">
        <p className="text-[13.5px] text-ink-2">Lost a device or signed in on a shared computer? Sign out of every browser where your account is signed in, including this one.</p>
        <Button className="mt-4" icon={<LogOut className="size-4" />} onClick={() => logout(true)}>Sign out everywhere</Button>
      </Card>
    </div>
  );
}

function Administrators() {
  const toast = useToast();
  const { username } = useAuth();
  const { data, loading, error, reload } = useApi<{ signup_allowed: boolean; users: any[] }>("/api/users");
  const [savingSwitch, setSavingSwitch] = useState(false);
  const toggleSignup = async () => {
    setSavingSwitch(true);
    try {
      const r = await api("/api/auth/signup-setting", { method: "PUT", json: { allowed: !data?.signup_allowed } });
      toast(r.allowed ? "New sign-ups are on: anyone with the link can create an account." : "New sign-ups are off. Only existing users can sign in.");
      reload(true);
    } catch (ex: any) { toast(ex.message, "critical"); } finally { setSavingSwitch(false); }
  };
  const [open, setOpen] = useState(false);
  const [nu, setNu] = useState("");
  const [np, setNp] = useState("");
  const [busy, setBusy] = useState(false);
  const [del, setDel] = useState<any | null>(null);
  const add = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    try {
      await api("/api/users", { method: "POST", json: { username: nu, password: np } });
      toast(`User "${nu.trim()}" added`);
      setOpen(false); setNu(""); setNp("");
      reload(true);
    } catch (ex: any) { toast(ex.message, "critical"); } finally { setBusy(false); }
  };
  const remove = async () => {
    try { await api(`/api/users/${del.id}`, { method: "DELETE" }); toast(`Removed "${del.username}"`); setDel(null); reload(true); }
    catch (ex: any) { toast(ex.message, "critical"); setDel(null); }
  };
  const unlock = async (u: any) => {
    try { await api(`/api/users/${u.id}/unlock`, { method: "POST" }); toast(`"${u.username}" unlocked`); reload(true); }
    catch (ex: any) { toast(ex.message, "critical"); }
  };
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  return (
    <div className="space-y-4">
    <Card title="New sign-ups" subtitle="Controls the Create account page.">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-2xl text-[13.5px] text-ink-2">
          {data?.signup_allowed
            ? <>Sign-ups are <b className="text-good">on</b>: anyone who opens the site can create an account and see all order data. Turn this off once everyone on your team has an account.</>
            : <>Sign-ups are <b className="text-critical">off</b>: only the users below can sign in. You can still add people here with “Add user”.</>}
        </div>
        <button role="switch" aria-checked={!!data?.signup_allowed} aria-label="Allow new sign-ups" disabled={savingSwitch} onClick={toggleSignup}
          className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${data?.signup_allowed ? "bg-good" : "bg-line-strong"}`}>
          <span className={`absolute top-1 size-5 rounded-full bg-white shadow transition-all ${data?.signup_allowed ? "left-6" : "left-1"}`} />
        </button>
      </div>
    </Card>
    <Card title="Users" subtitle="Everyone listed here can sign in and manage all data."
      actions={<Button variant="primary" icon={<UserPlus className="size-4" />} onClick={() => setOpen(true)}>Add user</Button>} bodyClass="p-0">
      <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-[13px]">
        <thead className="bg-surface-2 text-left text-[12px] text-muted"><tr><th className="px-5 py-2.5">Username</th><th className="px-4">Added</th><th className="px-4">Last sign-in</th><th className="px-5" /></tr></thead>
        <tbody>{(data?.users || []).map((u: any) => (
          <tr key={u.id} className="border-t border-line">
            <td className="px-5 py-2.5 font-medium">{u.username} {u.username === username && <Badge tone="info" className="ml-1">you</Badge>}</td>
            <td className="px-4 tabular">{fmtDateTime(u.created_at)}</td>
            <td className="px-4 tabular">{u.last_login ? fmtDateTime(u.last_login) : "-"}</td>
            <td className="space-x-2 px-5 text-right">
              <Button size="sm" variant="ghost" onClick={() => unlock(u)} title="Clear a lock caused by wrong passwords">Unlock</Button>
              {u.username !== username && <Button size="sm" variant="ghost" className="hover:text-critical" onClick={() => setDel(u)}>Remove</Button>}
            </td>
          </tr>))}</tbody></table></div>
      <Modal open={open} onClose={() => setOpen(false)} title="Add user"
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => add()}>Add</Button></>}>
        <form onSubmit={add} className="space-y-4">
          <Field label="Username"><Input value={nu} onChange={(e) => setNu(e.target.value)} required maxLength={80} autoComplete="off" /></Field>
          <Field label="Password" hint="Share it with them privately; they can change it under Settings > Your account."><Input type="password" value={np} onChange={(e) => setNp(e.target.value)} required autoComplete="new-password" /></Field>
          <StrengthHint password={np} />
          <button type="submit" className="hidden" />
        </form>
      </Modal>
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} danger confirmLabel="Remove" title="Remove user?"
        message={`"${del?.username}" will no longer be able to sign in. Their past actions stay in the audit log.`} />
    </Card>
    </div>
  );
}

function Audit() {
  const [page, setPage] = useState(1);
  const { data, loading } = useApi<any>(`/api/audit?page=${page}&size=30`);
  if (loading && !data) return <Loading />;
  if (!data) return null;
  return (
    <Card bodyClass="p-0">
      <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-[13px]">
        <thead className="bg-surface-2 text-left text-[12px] text-muted"><tr><th className="px-4 py-2.5">When</th><th className="px-4">User</th><th className="px-4">Action</th><th className="px-4">Target</th><th className="px-4">Details</th></tr></thead>
        <tbody>{data.rows.map((a: any) => (
          <tr key={a.id} className="border-t border-line align-top">
            <td className="whitespace-nowrap px-4 py-2.5 tabular">{fmtDateTime(a.at)}</td><td className="px-4">{a.user}</td>
            <td className="px-4"><Badge>{a.action.replace(/_/g, " ")}</Badge></td><td className="px-4 text-ink-2">{a.entity} {a.entity_id}</td>
            <td className="max-w-[520px] px-4 py-2.5 font-mono text-[11.5px] text-muted"><div className="line-clamp-2 break-all">{Object.keys(a.detail || {}).length ? JSON.stringify(a.detail) : ""}</div></td>
          </tr>))}</tbody></table></div>
      <Pagination page={page} size={30} total={data.total} onPage={setPage} />
    </Card>
  );
}

function System() {
  const { data } = useApi<any>("/api/storage");
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Storage">{data ? <>
        <StorageMeter s={data} />
        <dl className="mt-4 space-y-1.5 text-[13px]">
          {[["Uploaded workbooks", data.files_bytes], ["Database", data.database_bytes], ["Trained models", data.models_bytes]].map(([k, v]) => (
            <div key={k as string} className="flex justify-between"><dt className="text-muted">{k}</dt><dd className="tabular">{(Number(v) / 1048576).toFixed(1)} MB</dd></div>))}
        </dl></> : <Loading />}
      </Card>
      <Card title="About">
        <dl className="space-y-1.5 text-[13px]">
          <div className="flex justify-between"><dt className="text-muted">Application</dt><dd>OrderTrack Pro 1.0</dd></div>
          <div className="flex justify-between"><dt className="text-muted">Authentication</dt><dd>JWT (HS256), admin only</dd></div>
          <div className="flex justify-between"><dt className="text-muted">AI / ML</dt><dd>On-premise (scikit-learn), no external APIs</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">Backend</dt><dd className="truncate">{API_BASE || window.location.origin}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">API documentation</dt><dd><a className="text-primary hover:underline" href={apiUrl("/api/docs")} target="_blank" rel="noreferrer">/api/docs</a> <span className="text-muted">(development only)</span></dd></div>
        </dl>
      </Card>
    </div>
  );
}
