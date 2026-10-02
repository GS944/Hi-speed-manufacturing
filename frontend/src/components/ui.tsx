import { createContext, useCallback, useContext, useEffect, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes,
  type ReactNode, type SelectHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Info, Loader2, X, XCircle } from "lucide-react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// ------------------------------------------------------------------ Button
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
};
export function Button({ variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest }: BtnProps) {
  const base = "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap select-none";
  const sizes = { sm: "h-8 px-3 text-[13px]", md: "h-9 px-3.5 text-sm" };
  const variants = {
    primary: "bg-primary text-on-primary hover:bg-primary-hover shadow-sm",
    secondary: "bg-surface text-ink border border-line hover:bg-surface-3",
    ghost: "text-ink-2 hover:bg-surface-3 hover:text-ink",
    danger: "bg-critical text-white hover:opacity-90",
  };
  return (
    <button className={cx(base, sizes[size], variants[variant], className)} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

// ------------------------------------------------------------------ Card
export function Card({ title, subtitle, actions, children, className, bodyClass }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={cx("card", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4 pb-3">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx(title || actions ? "px-5 pb-5" : "p-5", bodyClass)}>{children}</div>
    </section>
  );
}

// ------------------------------------------------------------------ Badges / status
export function Badge({ tone = "neutral", children, className }: { tone?: "neutral" | "good" | "critical" | "warning" | "info"; children: ReactNode; className?: string }) {
  const tones = {
    neutral: "bg-surface-3 text-ink-2 border-line",
    good: "bg-good-soft text-good border-transparent",
    critical: "bg-critical-soft text-critical border-transparent",
    warning: "bg-warning-soft text-warning border-transparent",
    info: "bg-primary-soft text-primary border-transparent",
  };
  return <span className={cx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[12px] font-medium leading-4", tones[tone], className)}>{children}</span>;
}

/** Green = live / in progress; red = completed. Always icon + label, never color alone. */
export function StatusPill({ status, size = "md" }: { status: "live" | "completed" | string; size?: "md" | "lg" }) {
  const live = status === "live";
  const lg = size === "lg";
  return (
    <span className={cx("inline-flex items-center gap-2 rounded-full font-semibold tracking-wide",
      lg ? "px-3.5 py-1.5 text-[13px]" : "px-2.5 py-0.5 text-[11.5px]",
      live ? "bg-good-soft text-good" : "bg-critical-soft text-critical")}>
      {live
        ? <span className={cx("live-dot rounded-full bg-good", lg ? "size-2.5" : "size-2")} aria-hidden />
        : <CheckCircle2 className={lg ? "size-4" : "size-3.5"} aria-hidden />}
      {live ? "LIVE" : "COMPLETED"}
    </span>
  );
}

// ------------------------------------------------------------------ Inputs
export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx("h-9 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-muted outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20", className)} {...rest} />;
}
export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx("h-9 rounded-lg border border-line bg-surface px-2.5 text-sm text-ink outline-none focus:border-primary focus:ring-2 focus:ring-primary/20", className)} {...rest}>{children}</select>;
}
export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1.5 block text-[13px] font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-muted">{hint}</span>}
    </label>
  );
}

// ------------------------------------------------------------------ Feedback
export const Spinner = ({ className }: { className?: string }) => <Loader2 className={cx("size-5 animate-spin text-muted", className)} />;

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted"><Spinner /> {label}</div>;
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && <div className="mb-3 rounded-full bg-surface-3 p-3 text-muted">{icon}</div>}
      <p className="font-semibold text-ink">{title}</p>
      {children && <div className="mt-1 max-w-md text-[13px] text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-critical/30 bg-critical-soft px-4 py-3 text-[13px] text-critical">
      <XCircle className="mt-0.5 size-4 shrink-0" />
      <div className="flex-1">{message}</div>
      {onRetry && <button className="font-medium underline" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warning"; children: ReactNode }) {
  return (
    <div className={cx("flex items-start gap-2.5 rounded-lg px-3.5 py-2.5 text-[13px]",
      tone === "info" ? "bg-primary-soft text-ink-2" : "bg-warning-soft text-ink-2")}>
      {tone === "info" ? <Info className="mt-0.5 size-4 shrink-0 text-primary" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />}
      <div>{children}</div>
    </div>
  );
}

// ------------------------------------------------------------------ Page header
export function PageHeader({ title, subtitle, actions, back }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {back}
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-[13.5px] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ Tabs
export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: ReactNode }[]; value: T; onChange: (k: T) => void }) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}
          className={cx("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            value === t.key ? "border-primary text-primary" : "border-transparent text-muted hover:text-ink")}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ Pagination
export function Pagination({ page, size, total, onPage }: { page: number; size: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  const from = total ? (page - 1) * size + 1 : 0;
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5 text-[13px] text-muted">
      <span className="tabular">{from.toLocaleString()}–{Math.min(total, page * size).toLocaleString()} of {total.toLocaleString()}</span>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page"><ChevronLeft className="size-4" /></Button>
        <span className="tabular px-2">Page {page} of {pages}</span>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page"><ChevronRight className="size-4" /></Button>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Modal
export function Modal({ open, onClose, title, children, footer, width = "max-w-lg" }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; width?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>("input,select,textarea,button")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  // portal: ancestors with transforms/backdrop filters would otherwise trap position:fixed
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-[8vh] no-print" onMouseDown={onClose}>
      <div ref={ref} role="dialog" aria-modal className={cx("card fade-in w-full", width)} style={{ boxShadow: "var(--shadow-lg)" }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h3 className="text-[15px] font-semibold">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-surface-3 hover:text-ink" aria-label="Close"><X className="size-4" /></button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

// ------------------------------------------------------------------ Toasts
type Toast = { id: number; tone: "good" | "critical" | "info"; text: string };
const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "good") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, tone, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex w-[min(380px,calc(100vw-32px))] flex-col gap-2 no-print" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className="card fade-in flex items-start gap-2.5 px-4 py-3 text-[13px]" style={{ boxShadow: "var(--shadow-lg)" }}>
            {t.tone === "good" ? <CheckCircle2 className="mt-0.5 size-4 text-good" /> : t.tone === "critical" ? <XCircle className="mt-0.5 size-4 text-critical" /> : <Info className="mt-0.5 size-4 text-primary" />}
            <span className="flex-1 text-ink">{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

// ------------------------------------------------------------------ KPI tile
export function Stat({ label, value, hint, tone, icon, onClick }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: "good" | "critical" | "warning"; icon?: ReactNode; onClick?: () => void;
}) {
  const toneCls = tone === "good" ? "text-good" : tone === "critical" ? "text-critical" : tone === "warning" ? "text-warning" : "text-ink";
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} className={cx("card flex flex-col gap-1 px-4 py-3.5 text-left", onClick && "transition hover:border-line-strong hover:shadow-md")}>
      <div className="flex items-center justify-between gap-2 text-[12.5px] font-medium text-muted">
        <span>{label}</span>
        {icon && <span className="text-muted">{icon}</span>}
      </div>
      <div className={cx("text-[26px] font-semibold leading-tight tracking-tight", toneCls)}>{value}</div>
      {hint && <div className="text-[12px] text-muted">{hint}</div>}
    </Tag>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel = "Confirm", danger, onConfirm, onClose, busy }: {
  open: boolean; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void; onClose: () => void; busy?: boolean;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant={danger ? "danger" : "primary"} loading={busy} onClick={onConfirm}>{confirmLabel}</Button></>}>
      <div className="text-sm text-ink-2">{message}</div>
    </Modal>
  );
}
