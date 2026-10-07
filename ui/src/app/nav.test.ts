import type { Principal } from "@/api/types";
import { ADMIN, CLIENT } from "@/test/factories";
import { badgeLabel, canManageKeys, navItemsFor } from "./nav";

const ANONYMOUS: Principal = {
  name: "anonymous",
  role: "admin",
  key_id: null,
  auth_enabled: false,
};

describe("navItemsFor", () => {
  it.each<[string, Principal, string[], boolean]>([
    ["admin", ADMIN, ["Downloads", "Feeds", "Rules", "API keys"], true],
    ["client", CLIENT, ["Downloads", "Feeds", "Rules"], false],
    ["auth disabled", ANONYMOUS, ["Downloads", "Feeds", "Rules"], false],
  ])("%s", (_, principal, labels, manage) => {
    expect(navItemsFor(principal).map((item) => item.label)).toEqual(labels);
    expect(canManageKeys(principal)).toBe(manage);
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
