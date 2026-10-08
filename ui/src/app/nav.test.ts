import type { Principal } from "@/api/types";
import { ADMIN, ANONYMOUS_ADMIN, CLIENT } from "@/test/factories";
import { canChangeSettings, canManageKeys } from "@/auth/permissions";
import { badgeLabel, navItemsFor } from "./nav";

describe("navItemsFor", () => {
  it.each<[string, Principal, string[], boolean, boolean]>([
    ["admin", ADMIN, ["Downloads", "Feeds", "Rules", "API keys", "Settings"], true, true],
    ["client", CLIENT, ["Downloads", "Feeds", "Rules"], false, false],
    ["auth disabled", ANONYMOUS_ADMIN, ["Downloads", "Feeds", "Rules", "Settings"], false, true],
  ])("%s", (_, principal, labels, manageKeys, changeSettings) => {
    expect(navItemsFor(principal).map((item) => item.label)).toEqual(labels);
    expect(canManageKeys(principal)).toBe(manageKeys);
    expect(canChangeSettings(principal)).toBe(changeSettings);
  });
});

describe("badgeLabel", () => {
  it.each<[number | undefined, string | null]>([
    [undefined, null],
    [0, null],
    [7, "7"],
    [99, "99"],
    [140, "99+"],
  ])("%s -> %s", (count, expected) => {
    expect(badgeLabel(count)).toBe(expected);
  });
});
