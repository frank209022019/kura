import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "@/lib/engine";
import { fakeEngine, READY } from "@/test/engine";
import { AppShell } from "./app-shell";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    minimize: vi.fn(),
    toggleMaximize: vi.fn(),
    close: vi.fn(),
    isMaximized: async () => false,
    onResized: async () => () => {},
  }),
}));

describe("AppShell", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("scrolls a long page as a whole, every part of it at its full height", async () => {
    shell.invoke.mockImplementation(async (command: string) =>
      command === "engine_status" ? READY : undefined,
    );
    fakeEngine({ "/records": () => Response.json(null) });
    const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queries}>
        <EngineProvider>
          <MemoryRouter initialEntries={["/"]}>
            <Routes>
              <Route element={<AppShell />}>
                <Route index element={<p>The home page</p>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </EngineProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("The home page")).toBeInTheDocument();
    const page = screen.getByRole("main");
    expect(page).toHaveClass("overflow-y-auto");
    // Otherwise a part that clips its corners, as the queue's "Now converting" does, gives way
    // to the rest of a long page, down to a thin strip.
    expect(page).toHaveClass("*:shrink-0");
  });
});
