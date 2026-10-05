import { DownloadIcon, KeyRoundIcon, WorkflowIcon, type LucideIcon } from "lucide-react";
import type { Principal } from "@/api/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/downloads", label: "Downloads", icon: DownloadIcon },
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
