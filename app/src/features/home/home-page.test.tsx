import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EngineProvider, type EngineStatus, type Health } from "@/lib/engine";
import { HomePage } from "./home-page";

const shell = vi.hoisted(() => ({ invoke: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));

const health: Health = {
  status: "ok",
  version: "0.1.0",
  dataDir: "C:\\Users\\you\\AppData\\Local\\Kura",
  schemaVersion: 1,
};

function renderHome(engine: EngineStatus) {
  shell.invoke.mockImplementation(async (command: string) =>
    command === "engine_status" ? engine : undefined,
  );
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <EngineProvider>
        <HomePage />
      </EngineProvider>
    </QueryClientProvider>,
  );
}

describe("HomePage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(async () => Response.json(health)),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    shell.invoke.mockReset();
  });

  it("shows an empty shelf and where the data lives once the engine runs", async () => {
    renderHome({ state: "ready", url: "http://127.0.0.1:5000", token: "secret" });

    expect(screen.getByRole("heading", { name: "Your shelf is empty" })).toBeInTheDocument();
    expect(await screen.findByText("Running · version 0.1.0")).toBeInTheDocument();
    expect(screen.getByText(health.dataDir)).toBeInTheDocument();
    expect(screen.getByText("Ready · schema version 1")).toBeInTheDocument();
  });

  it("says when the engine didn't start, and offers to try again", async () => {
    renderHome({ state: "failed", message: "It stopped at once.", details: "Traceback…" });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Kura's engine didn't start. It stopped at once.");
    expect(alert).toHaveTextContent("Nothing in your folders was touched.");

    screen.getByRole("button", { name: "Try again" }).click();

    expect(shell.invoke).toHaveBeenCalledWith("restart_engine");
  });
});
