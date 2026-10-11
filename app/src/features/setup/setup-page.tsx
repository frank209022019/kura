import { Check, Cpu, Database, Folder, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { TitleBar } from "@/components/shell/title-bar";
import { Button } from "@/components/ui/button";
import { useFolders, useHealth, useSettings, useSystem, useTools } from "@/lib/engine";
import { cn } from "@/lib/utils";
import { FoldersStep } from "./folders-step";
import { FolderChip, Footer, Panel, Row } from "./parts";
import { describe, StandardStep } from "./standard-step";
import { CardFound, megabytes, ToolsStep } from "./tools-step";

const STEPS = [
  { id: "data", label: "Your data" },
  { id: "folders", label: "Your folders" },
  { id: "standard", label: "Your standard" },
  { id: "tools", label: "Tools" },
] as const;

type Step = (typeof STEPS)[number]["id"];

const isStep = (value: string | null): value is Step => STEPS.some((step) => step.id === value);

/** First run: where the data lives, the anime folders, the standard, and the tools. */
export function SetupPage() {
  const [params] = useSearchParams();
  const asked = params.get("step");
  const [step, setStep] = useState<Step>(isStep(asked) ? asked : "data");
  const current = STEPS.findIndex((each) => each.id === step);
  const go = (to: Step) => setStep(to);
  // Everything the steps show, so one place can say when the engine couldn't give it.
  const queries = [useHealth(), useFolders(), useSettings(), useTools(), useSystem()];

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TitleBar title="Kura setup" />
      <div className="flex-1 overflow-y-auto">
        <main className="mx-auto flex w-full max-w-250 flex-col gap-7 px-6 pt-6 pb-16">
          <header className="flex animate-fade-up flex-col gap-2">
            <span className="type-eyebrow">First run</span>
            <h1 className="font-extrabold text-44 leading-[1.05] tracking-[-0.03em]">
              Welcome to Kura
            </h1>
            <p className="max-w-170 text-17 text-fg-muted">
              Four quick steps. You can change any of them later in Settings, and nothing in your
              folders changes until you review it.
            </p>
          </header>

          <EngineProblem queries={queries} />
          <Stepper current={current} />

          {STEPS.map((each, index) => {
            if (index < current) return <Done key={each.id} step={each.id} onChange={go} />;
            if (index > current) return <Upcoming key={each.id} step={each.id} />;
            return <Current key={each.id} step={each.id} go={go} />;
          })}

          <p className="text-13 text-fg-faint">
            Kura never uploads your files. It only goes online to look up titles and artwork, to
            fetch its tools, and to check for updates.
          </p>
        </main>
      </div>
    </div>
  );
}

function Stepper({ current }: { current: number }) {
  return (
    <ol
      aria-label="Setup steps"
      className="flex animate-fade-up flex-wrap items-center gap-2.5 font-bold text-13"
    >
      {STEPS.map((step, index) => (
        <li key={step.id} className="contents">
          {index > 0 && (
            <span
              aria-hidden="true"
              className={cn("h-0.5 w-7 rounded-2", index <= current ? "bg-accent" : "bg-line")}
            />
          )}
          <span
            aria-current={index === current ? "step" : undefined}
            className={cn(
              "inline-flex items-center gap-2",
              index === current && "text-accent-fg",
              index > current && "text-fg-faint",
            )}
          >
            <span
              className={cn(
                "inline-flex size-6.5 items-center justify-center rounded-full text-12",
                index < current && "bg-accent text-on-accent",
                index === current && "border-2 border-accent",
                index > current && "border-2 border-line-strong",
              )}
            >
              {index < current ? (
                <Check size={13} strokeWidth={3.4} aria-label="Done:" />
              ) : (
                index + 1
              )}
            </span>
            {step.label}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** A finished step, folded into one line. */
function Done({ step, onChange }: { step: Step; onChange: (step: Step) => void }) {
  const health = useHealth();
  const folders = useFolders();
  const settings = useSettings();

  switch (step) {
    case "data":
      return (
        <Row icon={<Database size={18} />} title="Where Kura keeps its data">
          <span className="font-mono text-12">{health.data?.dataDir ?? "…"}</span>
          <span className="text-13 text-fg-muted">
            One database file, artwork, backups and logs. Your anime files never go here.
          </span>
        </Row>
      );
    case "folders":
      return (
        <Row
          icon={<Folder size={18} />}
          title="Your anime folders"
          action={
            <Button size="sm" onClick={() => onChange("folders")}>
              Change
            </Button>
          }
        >
          <span className="flex flex-wrap gap-2">
            {folders.data?.map((folder) => (
              <FolderChip key={folder.id} path={folder.path} />
            ))}
          </span>
          <span className="text-13 text-fg-muted">
            A folder can hold many anime in any layout, even mixed together. Kura works out what is
            what.
          </span>
        </Row>
      );
    case "standard":
      return (
        <Row
          icon={<SlidersHorizontal size={18} />}
          title="Your standard"
          action={
            <Button size="sm" onClick={() => onChange("standard")}>
              Change
            </Button>
          }
        >
          <span className="text-13 text-fg-muted">
            {settings.data ? describe(settings.data) : "…"}
          </span>
        </Row>
      );
    case "tools":
      return null; // the last step: finishing it starts the scan
  }
}

/** A step still to come, as a dashed line. */
function Upcoming({ step }: { step: Step }) {
  const system = useSystem();
  const tools = useTools();
  const size = (tools.data ?? []).reduce((total, tool) => total + tool.size, 0);

  if (step === "folders") {
    return (
      <Row dashed title="Your folders" icon={<Folder size={18} />}>
        <span className="text-13">The folders your anime is in, in any layout.</span>
      </Row>
    );
  }
  if (step !== "tools") {
    return (
      <Row dashed title="Your standard" icon={<SlidersHorizontal size={18} />}>
        <span className="text-13">The size and format every file is brought to, and its name.</span>
      </Row>
    );
  }
  return (
    <Row
      dashed
      icon={<Cpu size={18} />}
      title="Tools"
      action={system.data?.graphicsCard && <CardFound name={system.data.graphicsCard} />}
    >
      <span className="text-13">
        ffmpeg{size ? `, about ${megabytes(size)}` : ""}, plus a quick graphics card check.
      </span>
    </Row>
  );
}

function Current({ step, go }: { step: Step; go: (step: Step) => void }) {
  switch (step) {
    case "data":
      return <DataStep onContinue={() => go("folders")} />;
    case "folders":
      return <FoldersStep onBack={() => go("data")} onContinue={() => go("standard")} />;
    case "standard":
      return <StandardStep onBack={() => go("folders")} onContinue={() => go("tools")} />;
    case "tools":
      return <ToolsStep onBack={() => go("standard")} />;
  }
}

function DataStep({ onContinue }: { onContinue: () => void }) {
  const health = useHealth();

  return (
    <Panel title="Where Kura keeps its data" labelledBy="data-title">
      <p className="text-14 text-fg-muted">
        One database file, artwork, backups and logs, in one folder on this PC. Your anime files
        never go here.
      </p>
      <p className="w-fit rounded-14 bg-white/6 px-3.5 py-2 font-mono text-13">
        {health.data?.dataDir ?? "…"}
      </p>
      <Footer note="Uninstalling offers to export it first, and keeps it unless you choose otherwise.">
        <Button variant="primary" onClick={onContinue}>
          Continue
        </Button>
      </Footer>
    </Panel>
  );
}
