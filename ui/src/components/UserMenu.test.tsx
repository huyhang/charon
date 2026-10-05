import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Principal } from "@/api/types";
import { ADMIN, CLIENT } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { UserMenu } from "./UserMenu";

const ANONYMOUS: Principal = {
  name: "anonymous",
  role: "admin",
  key_id: null,
  auth_enabled: false,
};

async function openMenu(principal: Principal) {
  await renderWithApp(<UserMenu className="w-full" />, { principal });
  await userEvent.click(screen.getByRole("button", { name: "Account and settings" }));
  return screen.findByRole("menu");
}

describe("UserMenu", () => {
  afterEach(() => document.documentElement.classList.remove("dark"));

  it.each<[Principal, string, string]>([
    [ADMIN, "B", "admin"],
    [CLIENT, "P", "client"],
  ])("shows who is signed in: %j", async (principal, initial, role) => {
    await renderWithApp(<UserMenu />, { principal });
    const trigger = screen.getByRole("button", { name: "Account and settings" });
    expect(trigger).toHaveTextContent(`${initial}${principal.name}${role}`);
    await userEvent.click(trigger);
    expect(await screen.findByRole("menu")).toHaveTextContent(`${principal.name}${role}`);
  });

  it.each<["Light" | "Dark" | "System", boolean]>([
    ["Dark", true],
    ["Light", false],
    ["System", false],
  ])("switches to the %s theme", async (label, dark) => {
    await openMenu(ADMIN);
    const option = screen.getByRole("button", { name: label });
    await userEvent.click(option);
    expect(option).toHaveAttribute("aria-pressed", "true");
    const others = screen.getAllByRole("button", { pressed: false });
    expect(others.map((button) => button.textContent)).not.toContain(label);
    expect(document.documentElement.classList.contains("dark")).toBe(dark);
  });

  it("starts on the system theme", async () => {
    await openMenu(ADMIN);
    expect(screen.getByRole("button", { name: "System" })).toHaveAttribute("aria-pressed", "true");
  });

  it.each<[string, Principal, boolean]>([
    ["admin", ADMIN, true],
    ["client", CLIENT, true],
    ["auth disabled", ANONYMOUS, false],
  ])("%s: offers sign-out=%s", async (_label, principal, offered) => {
    await openMenu(principal);
    expect(screen.queryByRole("menuitem", { name: "Sign out" }) !== null).toBe(offered);
  });

  it("signs out", async () => {
    await openMenu(ADMIN);
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(screen.queryByTestId("signed-in")).not.toBeInTheDocument());
  });
});
