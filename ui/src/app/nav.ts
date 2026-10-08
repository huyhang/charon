import {
  DownloadIcon,
  KeyRoundIcon,
  RssIcon,
  SettingsIcon,
  WorkflowIcon,
  type LucideIcon,
} from "lucide-react";
import type { Principal } from "@/api/types";
import { canChangeSettings, canManageKeys } from "@/auth/permissions";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Who sees it; everyone if not given. */
  allowed?: (principal: Principal) => boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/downloads", label: "Downloads", icon: DownloadIcon },
  { to: "/feeds", label: "Feeds", icon: RssIcon },
  { to: "/rules", label: "Rules", icon: WorkflowIcon },
  { to: "/keys", label: "API keys", icon: KeyRoundIcon, allowed: canManageKeys },
  { to: "/settings", label: "Settings", icon: SettingsIcon, allowed: canChangeSettings },
];

export function navItemsFor(principal: Principal): NavItem[] {
  return NAV_ITEMS.filter((item) => item.allowed?.(principal) ?? true);
}

/** The count shown next to a nav item, e.g. unseen feed items; nothing when zero. */
export function badgeLabel(count: number | undefined): string | null {
  if (!count) return null;
  return count > 99 ? "99+" : String(count);
}
