import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Route, Routes } from "react-router";
import { AppShell } from "@/components/shell/app-shell";
import { sections } from "@/components/shell/sections";
import { HomePage } from "@/features/home/home-page";
import { NotBuiltPage } from "@/features/not-built-page";
import { EngineProvider } from "@/lib/engine";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <EngineProvider>
        <HashRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<HomePage />} />
              {sections
                .filter((section) => section.path !== "/")
                .map((section) => (
                  <Route
                    key={section.path}
                    path={section.path}
                    element={<NotBuiltPage section={section} />}
                  />
                ))}
            </Route>
          </Routes>
        </HashRouter>
      </EngineProvider>
    </QueryClientProvider>
  );
}
