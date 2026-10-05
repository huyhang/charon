import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "@/api/errors";
import type { CharonClient } from "@/api/client";
import { Toaster } from "@/components/ui/sonner";
import { createFakeClient } from "@/test/fakeClient";
import { makeJob, makeRule } from "@/test/factories";
import { renderWithApp } from "@/test/render";
import { MagnetBar } from "./MagnetBar";

const MAGNET = "magnet:?xt=urn:btih:abc&dn=Show.S01E01.1080p.mkv";

function setup(overrides: Partial<CharonClient> = {}, bar = <MagnetBar />) {
  const client = createFakeClient({
    listRules: async () => [makeRule({ id: "tv", name: "TV" })],
    previewRule: async () => ({
      rule_id: "tv",
      new_name: "Show.S01E01.mkv",
      final_path: `/library/tv/Show.S01E01.mkv`,
    }),
    submitDownload: async () => makeJob({ name: "Show.S01E01.1080p.mkv" }),
    ...overrides,
  });
  return renderWithApp(
    <>
      {bar}
      <Toaster />
    </>,
    { client },
  );
}

/** The toast with this title. Sonner briefly renders a second copy while it animates in. */
async function findToast(title: string): Promise<HTMLElement> {
  const [toastTitle] = await screen.findAllByText(title);
  return toastTitle!.closest("[data-sonner-toast]") as HTMLElement;
}

describe("MagnetBar", () => {
  it("previews which rule a magnet will match", async () => {
    const { client } = await setup();
    await userEvent.type(screen.getByLabelText("Magnet link"), MAGNET);
    expect(await screen.findByLabelText("New name")).toHaveTextContent("Show.S01E01.mkv");
    expect(screen.getByText(/Matches rule/)).toHaveTextContent("Matches rule TV");
    expect(screen.getByText("/library/tv")).toBeInTheDocument();
    expect(client.previewRule).toHaveBeenLastCalledWith({
      name: "Show.S01E01.1080p.mkv",
      rule_id: null,
    });
  });

  it.each([
    ["https://example.com/file", /doesn.t look like a magnet/],
    ["magnet:?xt=urn:btih:abc", /doesn.t include a name/],
  ])("explains %s", async (text, expected) => {
    await setup();
    await userEvent.type(screen.getByLabelText("Magnet link"), text);
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });

  it("submits the magnet and clears the field", async () => {
    const { client } = await setup();
    const input = screen.getByLabelText("Magnet link");
    await userEvent.type(input, `${MAGNET}{Enter}`);
    await waitFor(() => expect(client.submitDownload).toHaveBeenCalledWith(MAGNET, null));
    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("finds a magnet inside pasted text", async () => {
    const { client } = await setup();
    await userEvent.click(screen.getByLabelText("Magnet link"));
    await userEvent.paste(`here you go: ${MAGNET} enjoy`);
    await userEvent.click(screen.getByRole("button", { name: /download/i }));
    await waitFor(() => expect(client.submitDownload).toHaveBeenCalledWith(MAGNET, null));
  });

  it("disables submit without a magnet", async () => {
    await setup();
    expect(screen.getByRole("button", { name: /download/i })).toBeDisabled();
  });

  it("submits with the rule picked, then goes back to auto-matching", async () => {
    const { client } = await setup();
    await userEvent.type(screen.getByLabelText("Magnet link"), MAGNET);
    await userEvent.click(screen.getByRole("combobox", { name: "Rule" }));
    await userEvent.click(await screen.findByRole("option", { name: "TV" }));
    expect(screen.getByRole("combobox", { name: "Rule" })).toHaveTextContent("TV");
    await userEvent.click(screen.getByRole("button", { name: /download/i }));
    await waitFor(() => expect(client.submitDownload).toHaveBeenCalledWith(MAGNET, "tv"));
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Rule" })).toHaveTextContent("Auto-match rule"),
    );
  });

  it.each<[string, string | null, string, string | null]>([
    ["Download Station's name", "From.Station.mkv", MAGNET, "From.Station.mkv"],
    ["the magnet's name", null, MAGNET, "Show.S01E01.1080p.mkv"],
    ["nothing when neither has one", null, "magnet:?xt=urn:btih:abc", null],
  ])("confirms the download with %s", async (_label, name, magnet, description) => {
    await setup({ submitDownload: async () => makeJob({ name }) });
    await userEvent.type(screen.getByLabelText("Magnet link"), `${magnet}{Enter}`);
    const toast = await findToast("Download started");
    if (description) expect(toast).toHaveTextContent(description);
    else expect(toast).toHaveTextContent(/^Download started$/);
  });

  it("is busy while the download is submitted", async () => {
    await setup({ submitDownload: () => new Promise(() => {}) });
    await userEvent.type(screen.getByLabelText("Magnet link"), `${MAGNET}{Enter}`);
    await waitFor(() => expect(screen.getByRole("button", { name: /download/i })).toBeDisabled());
  });

  it("ignores a submit without a magnet, even past the disabled button", async () => {
    const { client } = await setup();
    const input = screen.getByLabelText("Magnet link");
    await userEvent.type(input, "not a magnet");
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    expect(client.submitDownload).not.toHaveBeenCalled();
  });

  it("explains a failed submission and keeps the magnet", async () => {
    await setup({
      submitDownload: async () =>
        Promise.reject(
          new ApiError(502, { code: "backend_error", message: "Download Station is down" }),
        ),
    });
    const input = screen.getByLabelText("Magnet link");
    await userEvent.type(input, `${MAGNET}{Enter}`);
    expect(await findToast("Couldn't start the download")).toHaveTextContent(
      "Download Station is down",
    );
    expect(input).toHaveValue(MAGNET);
  });

  it.each<[string, { initialMagnet?: string; focusSignal?: number }, string, boolean]>([
    ["prefills and focuses a magnet passed in", { initialMagnet: MAGNET }, MAGNET, true],
    ["focuses when asked to", { focusSignal: 1 }, "", true],
    ["leaves focus alone otherwise", {}, "", false],
  ])("%s", async (_label, props, value, focused) => {
    await setup({}, <MagnetBar {...props} />);
    const input = screen.getByLabelText("Magnet link");
    await waitFor(() => expect(input).toHaveValue(value));
    if (focused) expect(input).toHaveFocus();
    else expect(input).not.toHaveFocus();
  });
});
