import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { NavRail } from "./nav-rail";

/** The tiles lit while `page` is open. */
function litOn(page: string): string[] {
  render(
    <MemoryRouter initialEntries={[page]}>
      <NavRail />
    </MemoryRouter>,
  );
  return screen
    .getAllByRole("link")
    .filter((tile) => tile.getAttribute("aria-current") === "page")
    .map((tile) => tile.textContent ?? "");
}

describe("NavRail", () => {
  it.each([
    ["/", "Home"],
    ["/scan", "Home"],
    ["/franchises/1", "Home"],
    ["/titles/7", "Home"],
    ["/match?title=7", "Home"],
    ["/match", "Tidy up"],
    ["/tidy", "Tidy up"],
    ["/convert", "Convert"],
    ["/convert/queue", "Convert"],
    ["/history", "History"],
    ["/settings/about", "Settings"],
  ])("keeps the place of %s lit: %s", (page, tile) => {
    expect(litOn(page)).toEqual([tile]);
  });
});
