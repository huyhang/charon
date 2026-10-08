import type { Principal } from "@/api/types";

/** Key management is for admins, and only means something when auth is on. */
export function canManageKeys(principal: Principal): boolean {
  return principal.role === "admin" && principal.auth_enabled;
}

/** Settings (e.g. TMDB's token) are for admins, which everyone is while auth is off. */
export function canChangeSettings(principal: Principal): boolean {
  return principal.role === "admin";
}
