import { DownloadIcon, KeyRoundIcon, RssIcon, WorkflowIcon, type LucideIcon } from "lucide-react";
import type { Principal } from "@/api/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/downloads", label: "Downloads", icon: DownloadIcon },
  { to: "/feeds", label: "Feeds", icon: RssIcon },
  { to: "/rules", label: "Rules", icon: WorkflowIcon },
  { to: "/keys", label: "API keys", icon: KeyRoundIcon, adminOnly: true },
];

/** Key management is for admins, and only means something when auth is on. */
export function canManageKeys(principal: Principal): boolean {
  return principal.role === "admin" && principal.auth_enabled;
}

export function navItemsFor(principal: Principal): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.adminOnly || canManageKeys(principal));
}

/** The count shown next to a nav item, e.g. unseen feed items; nothing when zero. */
export function badgeLabel(count: number | undefined): string | null {
  if (!count) return null;
  return count > 99 ? "99+" : String(count);
}
