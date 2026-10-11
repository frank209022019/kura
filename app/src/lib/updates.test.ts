import { describe, expect, it } from "vitest";
import { whatsNew } from "./updates";

describe("whatsNew", () => {
  it("lists each entry once, joining the lines the changelog wraps", () => {
    const notes = [
      "### Added",
      "- Scanning: add your anime folders and Kura reads every",
      "  video in them.",
      "- A downloads page with every version.",
      "",
      "### Fixed",
      "- The update card shows what changed.",
    ].join("\n");

    expect(whatsNew(notes)).toEqual([
      "Scanning: add your anime folders and Kura reads every video in them.",
      "A downloads page with every version.",
      "The update card shows what changed.",
    ]);
  });

  it("turns links, bold and code into plain text", () => {
    expect(
      whatsNew("- See [the page](https://example.com) for **every** `kura export` option."),
    ).toEqual(["See the page for every kura export option."]);
  });

  it("has nothing to say when a release has no notes", () => {
    expect(whatsNew(null)).toEqual([]);
    expect(whatsNew("Just a sentence.")).toEqual([]);
  });

  it("reads notes saved with Windows line endings", () => {
    expect(whatsNew("- One\r\n  line.\r\n- Two.")).toEqual(["One line.", "Two."]);
  });
});
