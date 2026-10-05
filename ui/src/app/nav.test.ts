import type { Principal } from "@/api/types";
import { ADMIN, CLIENT } from "@/test/factories";
import { canManageKeys, navItemsFor } from "./nav";

const ANONYMOUS: Principal = {
  name: "anonymous",
  role: "admin",
  key_id: null,
  auth_enabled: false,
};

describe("navItemsFor", () => {
  it.each<[string, Principal, string[], boolean]>([
    ["admin", ADMIN, ["Downloads", "Rules", "API keys"], true],
    ["client", CLIENT, ["Downloads", "Rules"], false],
    ["auth disabled", ANONYMOUS, ["Downloads", "Rules"], false],
  ])("%s", (_, principal, labels, manage) => {
    expect(navItemsFor(principal).map((item) => item.label)).toEqual(labels);
    expect(canManageKeys(principal)).toBe(manage);
  });
});
