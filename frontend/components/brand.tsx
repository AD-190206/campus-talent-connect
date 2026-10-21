"use client";

import Link from "next/link";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemePreference } from "@/lib/theme";
import { cn } from "@/lib/format";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("h-7 w-7", className)}>
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <path
        d="M20.5 11.2a6.5 6.5 0 1 0 0 9.6"
        fill="none"
        strokeWidth="2.6"
        strokeLinecap="round"
        className="stroke-on-primary"
      />
      <circle cx="21.6" cy="16" r="1.9" className="fill-on-primary" />
    </svg>
  );
}

export function Logo({ href = "/", compact }: { href?: string; compact?: boolean }) {
  return (
    <Link href={href} className="flex items-center gap-2.5 rounded-md" aria-label="Campus Talent Connect home">
      <LogoMark />
      {!compact && (
        <span className="whitespace-nowrap text-[14.5px] font-semibold tracking-tight text-fg">
          Campus Talent<span className="text-muted"> Connect</span>
        </span>
      )}
    </Link>
  );
}

/** One-click light/dark switch. */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolved, toggle } = useTheme();
  const dark = resolved === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-fg",
        className
      )}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Light theme" : "Dark theme"}
    >
      {/* Both icons render; CSS picks one so SSR and client markup match. */}
      <Sun className="hidden h-[18px] w-[18px] dark:block" aria-hidden />
      <Moon className="h-[18px] w-[18px] dark:hidden" aria-hidden />
    </button>
  );
}

const THEME_OPTIONS: Array<{ value: ThemePreference; label: string; icon: typeof Sun }> = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

/** Light / dark / system selector for the settings page. */
export function ThemeSelector() {
  const { preference, setPreference } = useTheme();
  return (
    <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-3">
      {THEME_OPTIONS.map(({ value, label, icon: Icon }) => {
        const checked = preference === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={checked}
            onClick={() => setPreference(value)}
            className={cn(
              "flex flex-col items-center gap-2 rounded-xl border px-3 py-4 text-sm transition-colors",
              checked ? "border-primary bg-accent text-accent-fg" : "border-line text-muted hover:bg-surface-2 hover:text-fg"
            )}
          >
            <Icon className="h-5 w-5" aria-hidden />
            {label}
          </button>
        );
      })}
    </div>
  );
}
