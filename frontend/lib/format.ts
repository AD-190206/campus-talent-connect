// Presentation helpers. Amounts are always shown exactly as the API returns
// them; the frontend never computes an authoritative payment amount.

const CURRENCY = process.env.NEXT_PUBLIC_CURRENCY || "INR";

const money = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: CURRENCY,
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});

export function formatMoney(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? money.format(n) : String(value);
}

/** Sum decimal strings in integer paise to avoid float drift. */
export function sumMoney(values: string[]) {
  const paise = values.reduce((acc, v) => acc + Math.round(Number(v) * 100), 0);
  return (paise / 100).toFixed(2);
}

const dateFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
});

export function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  // Plain dates (YYYY-MM-DD) are calendar dates, not instants.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return Number.isNaN(d.getTime()) ? value : dateFmt.format(d);
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : dateTimeFmt.format(d);
}

export function relativeTime(value: string | null | undefined) {
  if (!value) return "";
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return formatDate(value);
}

/** Days until a YYYY-MM-DD deadline (negative when past). */
export function daysUntil(date: string) {
  const target = new Date(`${date}T00:00:00`).getTime();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target - today.getTime()) / 86400000);
}

export function deadlineLabel(date: string) {
  const days = daysUntil(date);
  if (days < 0) return `Ended ${formatDate(date)}`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days <= 30) return `${days} days left`;
  return `Due ${formatDate(date)}`;
}

export function shortId(id: string) {
  return id.slice(0, 8);
}

export function splitSkills(value: string | null | undefined) {
  return (value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function initials(text: string) {
  const parts = text.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
}

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const EVENT_LABELS: Record<string, string> = {
  PAYMENT_SUCCESS: "Payment succeeded",
  PAYMENT_FAILED: "Payment failed",
  PAYMENT_RELEASED: "Payment released",
  GENERAL: "Update",
};

/** Shorten raw UUIDs in backend-generated messages, e.g. "Payment 773dd29b…". */
export function tidyMessage(message: string) {
  return message.replace(/([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, "#$1");
}

export function eventLabel(event: string) {
  return EVENT_LABELS[event] || event.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}
