import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Route, Routes } from "react-router";
import { ScreenError } from "@/components/screen-error";
import { AppShell } from "@/components/shell/app-shell";
import { sections } from "@/components/shell/sections";
import { UpdateCard } from "@/components/shell/update-card";
import { FranchisePage } from "@/features/franchise/franchise-page";
import { HistoryPage } from "@/features/history/history-page";
import { HomePage } from "@/features/home/home-page";
import { MatchPage } from "@/features/match/match-page";
import { NotBuiltPage } from "@/features/not-built-page";
import { ScanPage } from "@/features/scan/scan-page";
import { SetupPage } from "@/features/setup/setup-page";
import { TidyPage } from "@/features/tidy/tidy-page";
import { TitlePage } from "@/features/title/title-page";
import { EngineProvider } from "@/lib/engine";

const queryClient = new QueryClient();

/** The sections with a screen of their own; the rest say they're coming. */
const BUILT = ["/", "/tidy", "/history"];

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <EngineProvider>
        <HashRouter>
          <Routes>
            <Route
              path="/setup"
              element={
                <ScreenError>
                  <SetupPage />
                </ScreenError>
              }
            />
            <Route element={<AppShell />}>
              <Route index element={<HomePage />} />
              <Route path="/scan" element={<ScanPage />} />
              <Route path="/match" element={<MatchPage />} />
              <Route path="/titles/:id" element={<TitlePage />} />
              <Route path="/franchises/:id" element={<FranchisePage />} />
              <Route path="/tidy" element={<TidyPage />} />
              <Route path="/history" element={<HistoryPage />} />
              {sections
                .filter((section) => !BUILT.includes(section.path))
                .map((section) => (
                  <Route
                    key={section.path}
                    path={section.path}
                    element={<NotBuiltPage section={section} />}
                  />
                ))}
            </Route>
          </Routes>
          <SetupUpdates />
        </HashRouter>
      </EngineProvider>
    </QueryClientProvider>
  );
}

/** The update card lives in the shell; setup has its own frame, so it shows the card itself. */
function SetupUpdates() {
  return (
    <Routes>
      <Route path="/setup" element={<UpdateCard />} />
      <Route path="*" element={null} />
    </Routes>
  );
}
