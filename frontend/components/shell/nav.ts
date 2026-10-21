import {
  Bell,
  Briefcase,
  ClipboardList,
  FileText,
  FolderKanban,
  LayoutDashboard,
  type LucideIcon,
  Scale,
  Search,
  Settings,
  ShieldCheck,
  SquarePen,
  User,
  Users,
  Wallet,
} from "lucide-react";
import type { Role } from "@/lib/types";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Other path prefixes that should highlight this item. */
  match?: string[];
  /** Exact match only (used where a deeper route has its own item). */
  exact?: boolean;
}

export const NAV: Record<Role, NavItem[]> = {
  STUDENT: [
    { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
    { href: "/projects", label: "Find Projects", icon: Search },
    { href: "/applications", label: "My Applications", icon: FileText },
    { href: "/assignments", label: "My Work", icon: Briefcase },
    { href: "/payments", label: "Earnings", icon: Wallet },
    { href: "/notifications", label: "Notifications", icon: Bell },
    { href: "/profile", label: "My Profile", icon: User },
    { href: "/settings", label: "Settings", icon: Settings },
  ],
  CLIENT: [
    { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
    { href: "/projects", label: "My Projects", icon: FolderKanban },
    { href: "/projects/new", label: "Post a Project", icon: SquarePen, exact: true },
    { href: "/applications", label: "Applications", icon: ClipboardList },
    { href: "/assignments", label: "Assignments", icon: Briefcase },
    { href: "/payments", label: "Payments", icon: Wallet },
    { href: "/notifications", label: "Notifications", icon: Bell },
    { href: "/profile", label: "Profile", icon: User },
    { href: "/settings", label: "Settings", icon: Settings },
  ],
  ADMIN: [
    { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
    { href: "/admin/users", label: "Users", icon: Users },
    { href: "/projects", label: "Projects", icon: FolderKanban },
    { href: "/applications", label: "Applications", icon: ClipboardList },
    { href: "/admin/verification", label: "Verification", icon: ShieldCheck },
    { href: "/admin/disputes", label: "Disputes", icon: Scale },
    { href: "/settings", label: "Settings", icon: Settings },
  ],
};

export function isActive(item: NavItem, pathname: string, items: NavItem[]) {
  if (item.exact) return pathname === item.href;
  const prefixes = [item.href, ...(item.match ?? [])];
  const hit = prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (!hit) return false;
  // Defer to a more specific exact item (e.g. /projects/new).
  return !items.some((other) => other !== item && other.exact && pathname === other.href);
}
