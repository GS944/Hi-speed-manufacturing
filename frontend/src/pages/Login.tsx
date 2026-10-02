import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Lock, ShieldCheck, UserPlus } from "lucide-react";
import { useAuth } from "../lib/auth";
import { API_BASE, api, backendStatus } from "../lib/api";
import { Button, ErrorBox, Field, Input, Notice } from "../components/ui";

type SignupStatus = { allowed: boolean; first_account: boolean };

/** Polls the backend until it is reachable and reports whether sign-ups are open. */
function useServer() {
  const [server, setServer] = useState<"checking" | "ok" | "starting" | "down">("checking");
  const [signup, setSignup] = useState<SignupStatus | null>(null);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      const s = await backendStatus();
      if (!alive) return;
      setServer(s);
      if (s !== "down") api<SignupStatus>("/api/auth/signup-status").then((st) => alive && setSignup(st)).catch(() => {});
      if (s !== "ok") timer = setTimeout(check, 5000);   // keep checking while a sleeping server wakes up
    };
    check();
    return () => { alive = false; clearTimeout(timer); };
  }, []);
  return { server, signup };
}

function ServerNotice({ server }: { server: string }) {
  if (server === "down") {
    return <ErrorBox message={`Cannot reach the application server${API_BASE ? ` (${API_BASE})` : ""}. A free server can take up to a minute to wake up - retrying automatically.`} />;
  }
  if (server === "starting") return <Notice>The server is waking up and loading its models. You can continue - the first screens may take a few seconds.</Notice>;
  return null;
}

function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden overflow-hidden bg-[#0f2a52] p-12 text-white lg:flex lg:flex-col">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" className="size-9" alt="" />
          <span className="text-lg font-semibold">OrderTrack Pro</span>
        </div>
        <div className="mt-auto max-w-md">
          <h1 className="text-3xl font-semibold leading-tight">Every order, every operation, live.</h1>
          <p className="mt-3 text-[15px] text-white/75">
            Track orders from booking to despatch, follow job work at every vendor, and print annexures and route cards from your own data sheets.
          </p>
          <ul className="mt-8 space-y-3 text-[14px] text-white/85">
            {["Live status by order number with stage timeline", "Annexure & route card printing with document numbering",
              "Private by design: sign-in required for every page and file"].map((t) => (
              <li key={t} className="flex items-center gap-2.5"><ShieldCheck className="size-4 text-emerald-300" /> {t}</li>
            ))}
          </ul>
        </div>
        <div className="pointer-events-none absolute -right-24 -top-24 size-96 rounded-full bg-white/5" />
        <div className="pointer-events-none absolute -bottom-32 right-24 size-80 rounded-full bg-white/5" />
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden"><img src="/favicon.svg" className="size-8" alt="" /><span className="text-lg font-semibold">OrderTrack Pro</span></div>
          {children}
        </div>
      </div>
    </div>
  );
}

function PasswordInput({ value, onChange, autoComplete, label = "Password" }: {
  value: string; onChange: (v: string) => void; autoComplete: string; label?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <Field label={label}>
      <div className="relative">
        <Input type={show ? "text" : "password"} autoComplete={autoComplete} value={value} onChange={(e) => onChange(e.target.value)} required className="pr-10" />
        <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:text-ink" aria-label={show ? "Hide password" : "Show password"}>
          {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
    </Field>
  );
}

// ------------------------------------------------------------------ Sign in
export default function Login() {
  const { username, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const { server, signup } = useServer();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (username) return <Navigate to={loc.state?.from || "/"} replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await login(u.trim(), p);
      nav(loc.state?.from || "/", { replace: true });
    } catch (ex: any) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout>
      <form onSubmit={submit}>
        <div className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-primary-soft px-2.5 py-1 text-[12px] font-medium text-primary"><Lock className="size-3.5" /> Secure sign-in</div>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight">Sign in</h2>
        <p className="mt-1 text-[13.5px] text-muted">Welcome back. Enter your username and password.</p>
        <div className="mt-7 space-y-4">
          <ServerNotice server={server} />
          {signup?.first_account && <Notice>No accounts exist yet. <Link to="/signup" className="font-medium text-primary underline">Create the first account</Link> to get started.</Notice>}
          {err && <ErrorBox message={err} />}
          <Field label="Username"><Input autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required maxLength={80} /></Field>
          <PasswordInput value={p} onChange={setP} autoComplete="current-password" />
          <Button type="submit" variant="primary" loading={busy} disabled={server === "down"} className="h-10 w-full">Sign in</Button>
        </div>
        {signup?.allowed !== false && (
          <p className="mt-6 text-center text-[13.5px] text-muted">
            Don't have an account? <Link to="/signup" className="font-medium text-primary hover:underline">Create an account</Link>
          </p>
        )}
        <p className="mt-6 text-center text-[12px] text-muted">Sessions are secured with signed, expiring tokens. Repeated wrong passwords lock the account temporarily.</p>
      </form>
    </AuthLayout>
  );
}

// ------------------------------------------------------------------ Create account
export function Signup() {
  const { username, signup: register } = useAuth();
  const nav = useNavigate();
  const { server, signup } = useServer();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [p2, setP2] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (username) return <Navigate to="/" replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (p !== p2) return setErr("The two passwords do not match.");
    setBusy(true);
    try {
      await register(u.trim(), p);
      nav("/", { replace: true });
    } catch (ex: any) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  };

  const closed = signup?.allowed === false;
  return (
    <AuthLayout>
      <form onSubmit={submit}>
        <div className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-primary-soft px-2.5 py-1 text-[12px] font-medium text-primary"><UserPlus className="size-3.5" /> New account</div>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight">Create an account</h2>
        <p className="mt-1 text-[13.5px] text-muted">Choose any username and password. Use them to sign in on every future visit.</p>
        <div className="mt-7 space-y-4">
          <ServerNotice server={server} />
          {closed && <ErrorBox message="New sign-ups are turned off for this workspace. Ask an existing user to create an account for you." />}
          {err && <ErrorBox message={err} />}
          <Field label="Username"><Input autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required maxLength={80} disabled={closed} /></Field>
          <PasswordInput value={p} onChange={setP} autoComplete="new-password" />
          <PasswordInput value={p2} onChange={setP2} autoComplete="new-password" label="Confirm password" />
          <StrengthHint password={p} />
          <Button type="submit" variant="primary" loading={busy} disabled={server === "down" || closed} className="h-10 w-full"
            icon={<UserPlus className="size-4" />}>Create account</Button>
        </div>
        <p className="mt-6 text-center text-[13.5px] text-muted">
          Already have an account? <Link to="/login" className="font-medium text-primary hover:underline">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}

/** Advisory only - any password is accepted. */
export function StrengthHint({ password }: { password: string }) {
  if (!password) return null;
  const score = [password.length >= 8, password.length >= 12, /[a-z]/.test(password) && /[A-Z]/.test(password),
    /\d/.test(password), /[^A-Za-z0-9]/.test(password)].filter(Boolean).length;
  const label = score <= 1 ? "Weak" : score <= 3 ? "Fair" : "Strong";
  const color = score <= 1 ? "bg-critical" : score <= 3 ? "bg-warning" : "bg-good";
  return (
    <div aria-live="polite">
      <div className="flex gap-1">{[0, 1, 2, 3, 4].map((i) => <span key={i} className={`h-1 flex-1 rounded-full ${i < score ? color : "bg-surface-3"}`} />)}</div>
      <p className="mt-1 text-[12px] text-muted">Strength: {label}{score <= 3 ? " - longer passwords are harder to guess (your choice)." : ""}</p>
    </div>
  );
}
