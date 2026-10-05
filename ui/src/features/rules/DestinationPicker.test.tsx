import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ApiError } from "@/api/errors";
import { createFakeClient } from "@/test/fakeClient";
import { renderWithApp } from "@/test/render";
import { DestinationPicker } from "./DestinationPicker";

function Harness({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <DestinationPicker id="dest" value={value} onChange={setValue} />
      <output data-testid="value">{value}</output>
    </>
  );
}

const notFound = () => new ApiError(404, { code: "folder_not_found", message: "missing" });

const client = () =>
  createFakeClient({
    destinationRoots: async () => ["/library"],
    destinationFolders: async (path) => {
      if (path === "/library")
        return { path, parent: null, folders: [{ name: "tv", path: "/library/tv" }] };
      if (path === "/library/tv") return { path, parent: "/library", folders: [] };
      throw notFound();
    },
  });

describe("DestinationPicker", () => {
  it.each([
    ["/library/tv", "Folder exists."],
    ["/library/new", "New folder: it will be created on the first move."],
    ["/etc", "Must be inside /library."],
    ["library", "Use an absolute path, starting with /."],
  ])("describes %s", async (initial, message) => {
    await renderWithApp(<Harness initial={initial} />, { client: client() });
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it.each<[string[], string, string]>([
    [[], "/library/tv", "Must be inside a configured root."],
    [["/library", "/media"], "/etc", "Must be inside /library or /media."],
  ])("with roots %j describes %s", async (roots, initial, message) => {
    const client = createFakeClient({ destinationRoots: async () => roots });
    await renderWithApp(<Harness initial={initial} />, { client });
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("says when no roots are configured", async () => {
    const client = createFakeClient({ destinationRoots: async () => [] });
    await renderWithApp(<Harness />, { client });
    await userEvent.click(screen.getByRole("button", { name: /browse/i }));
    expect(await screen.findByText(/No roots configured/)).toHaveTextContent("CHARON_RULE_ROOTS");
  });

  it("moves between several roots", async () => {
    const client = createFakeClient({
      destinationRoots: async () => ["/library", "/media"],
      destinationFolders: async (path) => ({ path, parent: null, folders: [] }),
    });
    await renderWithApp(<Harness />, { client });
    await userEvent.click(screen.getByRole("button", { name: /browse/i }));
    await userEvent.click(await screen.findByRole("button", { name: "/media" }));
    const trail = await screen.findByRole("navigation", { name: "Folder path" });
    await userEvent.click(within(trail).getByRole("button", { name: "roots" }));
    expect(await screen.findByText("Allowed locations")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "/library" })).toBeInTheDocument();
  });

  it("starts at the typed folder and climbs back up its path", async () => {
    await renderWithApp(<Harness initial="/library/tv" />, { client: client() });
    await userEvent.click(screen.getByRole("button", { name: /browse/i }));
    expect(await screen.findByText("No subfolders.")).toBeInTheDocument();
    const trail = screen.getByRole("navigation", { name: "Folder path" });
    await userEvent.click(within(trail).getByRole("button", { name: "/library" }));
    expect(await screen.findByRole("button", { name: "tv" })).toBeInTheDocument();
  });

  it.each<[string, ApiError, string]>([
    ["a folder that doesn't exist yet", notFound(), "This folder doesn't exist yet."],
    [
      "a folder Charon can't read",
      new ApiError(422, { code: "filesystem_error", message: "permission denied" }),
      "permission denied",
    ],
  ])("explains %s while browsing", async (_label, error, message) => {
    const failing = createFakeClient({
      destinationRoots: async () => ["/library"],
      destinationFolders: async () => Promise.reject(error),
    });
    await renderWithApp(<Harness initial="/library/new" />, { client: failing });
    await userEvent.click(screen.getByRole("button", { name: /browse/i }));
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("browses into a folder and picks it", async () => {
    await renderWithApp(<Harness />, { client: client() });
    await userEvent.click(screen.getByRole("button", { name: /browse/i }));
    await userEvent.click(await screen.findByRole("button", { name: "/library" }));
    await userEvent.click(await screen.findByRole("button", { name: "tv" }));
    expect(await screen.findByText("No subfolders.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use this folder" }));
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("/library/tv"));
  });
});
