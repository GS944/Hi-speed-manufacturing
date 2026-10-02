const TOKEN_KEY = "ot-token";

/** Backend origin. Empty = same origin (backend serves the UI, or the Vite dev proxy).
 *  Set VITE_API_URL at build time when the UI is hosted separately (e.g. Vercel + Render). */
export const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) || "").trim().replace(/\/+$/, "");
export const apiUrl = (path: string) => (path.startsWith("http") ? path : API_BASE + path);

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

type Session = { token: string; expiresAt: string; username: string };

export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    if (new Date(s.expiresAt).getTime() <= Date.now()) {
      localStorage.removeItem(TOKEN_KEY);
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export function setSession(s: Session | null) {
  try {
    if (s) localStorage.setItem(TOKEN_KEY, JSON.stringify(s));
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

function messageFrom(body: any, status: number): string {
  const d = body?.detail;
  if (typeof d === "string") return d;
  if (d?.message) return d.message;
  if (Array.isArray(d) && d[0]?.msg) return `${d[0].loc?.slice(-1)[0] ?? "Field"}: ${d[0].msg}`;
  return status >= 500 ? "The server ran into a problem. Please try again." : `Request failed (${status})`;
}

/** Ping the backend; used by the sign-in page to explain connection problems. */
export async function backendStatus(): Promise<"ok" | "starting" | "down"> {
  try {
    const r = await fetch(apiUrl("/api/health"), { cache: "no-store" });
    if (!r.ok) return "down";
    const b = await r.json();
    return b.ready ? "ok" : "starting";
  } catch {
    return "down";
  }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const s = getSession();
  const headers = new Headers(opts.headers);
  if (s) headers.set("Authorization", `Bearer ${s.token}`);
  let body = opts.body;
  if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  }
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { ...opts, headers, body });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that the backend is running.");
  }
  if (res.status === 401 && !path.endsWith("/auth/login")) {
    setSession(null);
    onUnauthorized?.();
  }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json().catch(() => null) : null;
  if (!res.ok) throw new ApiError(res.status, messageFrom(data, res.status), data?.detail);
  return data as T;
}

/** Download an authenticated file (PDF / XLSX / CSV) and save it with the server-provided name. */
export async function download(path: string, fallbackName: string) {
  const s = getSession();
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { headers: s ? { Authorization: `Bearer ${s.token}` } : {} });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that the backend is running.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, messageFrom(body, res.status));
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const m = /filename="?([^"]+)"?/.exec(cd);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = m?.[1] || fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

export async function upload(path: string, form: FormData, onProgress?: (pct: number) => void): Promise<any> {
  const s = getSession();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl(path));
    if (s) xhr.setRequestHeader("Authorization", `Bearer ${s.token}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((100 * e.loaded) / e.total));
    xhr.onload = () => {
      const body = (() => { try { return JSON.parse(xhr.responseText); } catch { return null; } })();
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(xhr.status, messageFrom(body, xhr.status), body?.detail));
    };
    xhr.onerror = () => reject(new ApiError(0, "Upload failed - connection lost."));
    xhr.send(form);
  });
}
