import type { ReactNode } from "react";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-rule/60 ${className}`} />;
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <h2 className="text-lg font-semibold text-ink">{children}</h2>
      {right}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="panel p-8 text-center">
      <p className="text-lg font-medium text-ink">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-md text-muted">{children}</div>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="panel border-alert/40 bg-alertbg p-5 text-alert">
      <p className="font-medium">Something went wrong.</p>
      <p className="mt-1 text-sm">{message}</p>
    </div>
  );
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  queued: { label: "Queued", cls: "bg-paper text-muted border-rule" },
  processing: { label: "Processing", cls: "bg-okbg text-navy border-navy/30" },
  ready: { label: "Ready", cls: "bg-surface text-ink border-rule" },
  degraded: { label: "Scanned — check", cls: "bg-warnbg text-warn border-warn/40" },
  failed: { label: "Failed", cls: "bg-alertbg text-alert border-alert/40" },
  unsupported: { label: "Not supported", cls: "bg-alertbg text-alert border-alert/40" },
};

export function StatusPill({ status }: { status: string }) {
  const m = STATUS_META[status] ?? { label: status, cls: "bg-paper text-muted border-rule" };
  return <span className={`inline-block rounded border px-2 py-0.5 text-sm font-medium ${m.cls}`}>{m.label}</span>;
}

export function SummaryStat({
  label,
  value,
  tone = "default",
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: "default" | "alert" | "warn";
  hint?: string;
}) {
  const toneCls =
    tone === "alert" ? "text-alert" : tone === "warn" ? "text-warn" : "text-ink";
  return (
    <div className="panel px-4 py-3">
      <div className="text-sm text-muted">{label}</div>
      <div className={`mt-1 text-3xl font-bold tnum ${toneCls}`}>{value}</div>
      {hint && <div className="mt-0.5 text-sm text-faint">{hint}</div>}
    </div>
  );
}
