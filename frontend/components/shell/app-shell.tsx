"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Bell, ChevronsLeft, ChevronsRight, LogOut, Menu, Search, Settings, User, X } from "lucide-react";
import { api } from "@/lib/api";
import { ROLE_LABEL, useAuth, useUser } from "@/lib/auth";
import { cn, initials } from "@/lib/format";
import { Logo, LogoMark, ThemeToggle } from "@/components/brand";
import { isActive, NAV, type NavItem } from "./nav";

const COLLAPSE_KEY = "ctc.sidebar-collapsed";

function useUnreadCount(enabled: boolean) {
  const [count, setCount] = useState<number | null>(null);
  const pathname = usePathname();
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    api.notifications
      .list({ unread: "true", page_size: 1 })
      .then((r) => !cancelled && setCount(r.pagination.total))
      .catch(() => !cancelled && setCount(null));
    return () => {
      cancelled = true;
    };
  }, [enabled, pathname]);
  return count;
}

function NavLinks({
  items,
  collapsed,
  onNavigate,
}: {
  items: NavItem[];
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const active = isActive(item, pathname, items);
        const Icon = item.icon;
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              title={collapsed ? item.label : undefined}
              className={cn(
                "group flex h-9 items-center gap-3 rounded-lg px-2.5 text-[13.5px] font-medium transition-colors",
                active ? "bg-accent text-accent-fg" : "text-muted hover:bg-surface-2 hover:text-fg",
                collapsed && "justify-center px-0"
              )}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
              <span className={cn(collapsed && "sr-only")}>{item.label}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function UserMenu() {
  const user = useUser();
  const { logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const signOut = async () => {
    setOpen(false);
    await logout();
    router.replace("/login");
  };

  const item = "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-fg hover:bg-surface-2";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex h-9 items-center gap-2 rounded-lg pl-1 pr-1 hover:bg-surface-2 sm:pr-2.5"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-accent-fg">
          {initials(user.email)}
        </span>
        <span className="hidden max-w-40 truncate text-[13px] font-medium sm:block">{user.email}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-60 animate-fade-in rounded-xl border border-line bg-surface p-1.5 shadow-pop"
        >
          <div className="px-2.5 py-2">
            <p className="truncate text-sm font-medium">{user.email}</p>
            <p className="text-xs text-muted">{ROLE_LABEL[user.role]}</p>
          </div>
          <div className="my-1 h-px bg-line" />
          {user.role !== "ADMIN" && (
            <Link role="menuitem" href="/profile" className={item} onClick={() => setOpen(false)}>
              <User className="h-4 w-4 text-muted" aria-hidden />
              Profile
            </Link>
          )}
          <Link role="menuitem" href="/settings" className={item} onClick={() => setOpen(false)}>
            <Settings className="h-4 w-4 text-muted" aria-hidden />
            Settings
          </Link>
          <button role="menuitem" type="button" onClick={signOut} className={item}>
            <LogOut className="h-4 w-4 text-muted" aria-hidden />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function TopSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        router.push(`/projects?query=${encodeURIComponent(query.trim())}`);
      }}
      className="relative hidden w-full max-w-sm md:block"
    >
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search projects"
        aria-label="Search projects"
        className="h-9 w-full rounded-lg border border-transparent bg-surface-2 pl-9 pr-3 text-sm placeholder:text-muted focus:border-line focus:bg-surface focus:outline-none"
      />
    </form>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const user = useUser();
  const items = NAV[user.role];
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const unread = useUnreadCount(user.role !== "ADMIN");

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      // Default to expanded.
    }
  }, []);

  useEffect(() => setDrawer(false), [pathname]);

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [drawer]);

  const toggleCollapsed = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1");
      } catch {
        // Not persisted.
      }
      return !c;
    });
  };

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface px-3 py-2 focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200 lg:flex",
          collapsed ? "w-[68px]" : "w-60"
        )}
      >
        <div className={cn("flex h-16 items-center", collapsed ? "justify-center" : "px-5")}>
          {collapsed ? (
            <Link href="/dashboard" aria-label="Overview">
              <LogoMark />
            </Link>
          ) : (
            <Logo href="/dashboard" />
          )}
        </div>
        <nav aria-label="Main" className={cn("flex-1 overflow-y-auto pb-4", collapsed ? "px-2.5" : "px-3")}>
          {!collapsed && <p className="label-caps mb-2 px-2.5 pt-2">{ROLE_LABEL[user.role]}</p>}
          <NavLinks items={items} collapsed={collapsed} />
        </nav>
        <div className={cn("border-t border-line p-3", collapsed && "flex justify-center")}>
          <button
            type="button"
            onClick={toggleCollapsed}
            className={cn(
              "flex h-9 items-center gap-3 rounded-lg px-2.5 text-[13px] text-muted hover:bg-surface-2 hover:text-fg",
              !collapsed && "w-full"
            )}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronsRight className="h-4 w-4" aria-hidden />
            ) : (
              <>
                <ChevronsLeft className="h-4 w-4" aria-hidden />
                Collapse
              </>
            )}
          </button>
        </div>
      </aside>

      {/* Mobile drawer */}
      <div className={cn("fixed inset-0 z-40 lg:hidden", drawer ? "" : "pointer-events-none")} aria-hidden={!drawer}>
        <div
          className={cn("absolute inset-0 bg-black/40 transition-opacity", drawer ? "opacity-100" : "opacity-0")}
          onClick={() => setDrawer(false)}
        />
        <aside
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
          className={cn(
            "absolute inset-y-0 left-0 flex w-72 max-w-[85%] flex-col bg-surface shadow-pop transition-transform duration-200",
            drawer ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <div className="flex h-16 items-center justify-between px-5">
            <Logo href="/dashboard" />
            <button
              type="button"
              onClick={() => setDrawer(false)}
              className="rounded-lg p-2 text-muted hover:bg-surface-2"
              aria-label="Close navigation"
              tabIndex={drawer ? 0 : -1}
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 pb-6">
            <p className="label-caps mb-2 px-2.5 pt-2">{ROLE_LABEL[user.role]}</p>
            <NavLinks items={items} onNavigate={() => setDrawer(false)} />
          </nav>
        </aside>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur sm:px-6 lg:px-8">
          <button
            type="button"
            onClick={() => setDrawer(true)}
            className="-ml-1 rounded-lg p-2 text-muted hover:bg-surface-2 lg:hidden"
            aria-label="Open navigation"
            aria-expanded={drawer}
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="lg:hidden">
            <Logo href="/dashboard" compact />
          </div>
          <div className="flex flex-1 items-center">{user.role === "STUDENT" && <TopSearch />}</div>
          <div className="flex items-center gap-1">
            {user.role !== "ADMIN" && (
              <Link
                href="/notifications"
                className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-fg"
                aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
              >
                <Bell className="h-[18px] w-[18px]" aria-hidden />
                {!!unread && (
                  <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-on-primary">
                    {unread > 9 ? "9+" : unread}
                  </span>
                )}
              </Link>
            )}
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
