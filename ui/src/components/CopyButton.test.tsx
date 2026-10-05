import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toaster } from "@/components/ui/sonner";
import { renderWithApp } from "@/test/render";
import { CopyButton } from "./CopyButton";

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

async function renderButton(onParentClick = () => {}) {
  await renderWithApp(
    <>
      <div onClick={onParentClick}>
        <CopyButton value="abcdef" label="Copy info hash" />
      </div>
      <Toaster />
    </>,
  );
}

describe("CopyButton", () => {
  it.each<[string | undefined, string]>([
    [undefined, "Copy"],
    ["Copy magnet", "Copy magnet"],
  ])("is labelled %j as %s", async (label, name) => {
    await renderWithApp(<CopyButton value="x" label={label} />);
    expect(screen.getByRole("button", { name })).toBeInTheDocument();
  });

  it("copies the value and says so, without clicking what's behind it", async () => {
    const writeText = vi.fn(async () => {});
    stubClipboard(writeText);
    const onParentClick = vi.fn();
    await renderButton(onParentClick);
    await userEvent.click(screen.getByRole("button", { name: "Copy info hash" }));
    expect(writeText).toHaveBeenCalledWith("abcdef");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(onParentClick).not.toHaveBeenCalled();
  });

  it("explains when the value can't be copied", async () => {
    stubClipboard(async () => Promise.reject(new Error("Write permission denied")));
    await renderButton();
    await userEvent.click(screen.getByRole("button", { name: "Copy info hash" }));
    const [title] = await screen.findAllByText("Couldn't copy");
    expect(title!.closest("[data-sonner-toast]")).toHaveTextContent("Write permission denied");
    expect(screen.getByRole("button", { name: "Copy info hash" })).toBeInTheDocument();
  });
});
