const UNITS = ["B", "KB", "MB", "GB", "TB"];
const DASH = "—";

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || bytes < 0) return DASH;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit++;
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)} ${UNITS[unit]}`;
}

export function formatSpeed(bps: number | null | undefined): string {
  return bps ? `${formatBytes(bps)}/s` : DASH;
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return DASH;
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${String(m % 60).padStart(2, "0")}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

export function formatPercent(percent: number): string {
  return `${Math.floor(Math.min(Math.max(percent, 0), 100))}%`;
}

export function formatRelative(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const seconds = Math.round((now.getTime() - date.getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
