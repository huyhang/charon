import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import type { Principal } from "@/api/types";
import { AuthProvider } from "@/auth/AuthProvider";
import { memoryStore } from "@/lib/storage";
import { createFakeClient } from "@/test/fakeClient";
import { SignInPage } from "./SignInPage";

const unauthorized = () => new ApiError(401, { code: "unauthorized", message: "invalid API key" });

/** Renders the page signed out: the first key check is rejected. */
function renderSignIn(me: () => Promise<Principal>, hint?: string) {
  const client = createFakeClient({ me });
  render(
    <AuthProvider client={client} keys={memoryStore()}>
      <SignInPage hint={hint} />
    </AuthProvider>,
  );
  return client;
}

describe("SignInPage", () => {
  it.each<[string | undefined]>([["Dev stack: the admin key is dev-key"], [undefined]])(
    "shows the sign-in hint %j when there is one",
    async (hint) => {
      renderSignIn(async () => Promise.reject(unauthorized()), hint);
      await screen.findByLabelText("API key");
      if (hint) expect(screen.getByText(hint)).toBeInTheDocument();
      else expect(screen.queryByText(/dev-key/)).not.toBeInTheDocument();
    },
  );

  it.each([[""], ["   "]])("won't sign in with the key %j", async (key) => {
    const client = renderSignIn(async () => Promise.reject(unauthorized()));
    const input = await screen.findByLabelText("API key");
    await waitFor(() => expect(client.me).toHaveBeenCalledTimes(1));
    if (key) await userEvent.type(input, key);
    expect(screen.getByRole("button", { name: /sign in/i })).toBeDisabled();
    // Even a submit that gets past the disabled button is ignored.
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    expect(client.me).toHaveBeenCalledTimes(1);
  });

  it("is busy while the key is checked", async () => {
    let answer: (principal: Principal) => void = () => {};
    const me = vi
      .fn<() => Promise<Principal>>()
      .mockRejectedValueOnce(unauthorized())
      .mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)));
    renderSignIn(me);
    await userEvent.type(await screen.findByLabelText("API key"), "dev-key");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(screen.getByRole("button", { name: /sign in/i })).toBeDisabled();
    answer({ name: "admin", role: "admin", key_id: null, auth_enabled: true });
    await waitFor(() => expect(me).toHaveBeenCalledTimes(2));
  });

  it("marks the key field when the key was rejected", async () => {
    renderSignIn(async () => Promise.reject(unauthorized()));
    await userEvent.type(await screen.findByLabelText("API key"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    const input = screen.getByLabelText("API key");
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "true"));
    expect(input).toHaveAttribute("aria-describedby", "api-key-error");
    expect(screen.getByRole("alert")).toHaveTextContent("invalid API key");
  });
});
