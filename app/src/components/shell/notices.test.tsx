import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { Notices } from "./notices";

type Handler = (event: { payload: unknown }) => void;
const shell = vi.hoisted(() => ({ handlers: new Map<string, Handler>() }));

vi.mock("@tauri-apps/api/event", () => ({
  listen: async (name: string, handler: Handler) => {
    shell.handlers.set(name, handler);
    return () => shell.handlers.delete(name);
  },
}));

describe("Notices", () => {
  it("shows what the engine tells while the window is open, leading where it says", async () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route index element={<Notices />} />
          <Route path="/titles/:id" element={<p>A title</p>} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(shell.handlers.has("notice")).toBe(true));

    act(() =>
      shell.handlers.get("notice")?.({
        payload: {
          title: "Trigun, season 1 is done",
          body: "26 episodes · all checked · 6.1 GB → 11.7 GB",
          link: "/titles/12",
        },
      }),
    );

    const note = await screen.findByRole("status");
    expect(note).toHaveTextContent("Trigun, season 1 is done");
    expect(note).toHaveTextContent("26 episodes · all checked · 6.1 GB → 11.7 GB");
    screen.getByRole("button", { name: "View" }).click();
    expect(await screen.findByText("A title")).toBeInTheDocument();
  });
});
