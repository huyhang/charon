import { screen } from "@testing-library/react";

/** The toast with this title. Sonner briefly renders a second copy while it animates in. */
export async function findToast(title: string | RegExp): Promise<HTMLElement> {
  const [toastTitle] = await screen.findAllByText(title);
  return toastTitle!.closest("[data-sonner-toast]") as HTMLElement;
}
