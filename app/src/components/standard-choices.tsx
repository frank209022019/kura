import { RadioGroup } from "radix-ui";
import { useId } from "react";
import { Segmented } from "@/components/ui/segmented";
import { Switch } from "@/components/ui/switch";
import type { Settings } from "@/lib/engine";

export const STANDARDS = [
  {
    value: "cinema-1080",
    name: "Cinema 1080p",
    recommended: true,
    spec: "1080p · HEVC 10-bit · MKV",
    text: "Original audio kept, lossless tracks become AAC. Subtitles and fonts kept.",
    size: "≈ 450 MB per episode",
  },
  {
    value: "compact-720",
    name: "Compact 720p",
    recommended: false,
    spec: "720p · HEVC 10-bit · MKV",
    text: "Same audio and subtitle rules. Still crisp on a laptop screen, about half the size.",
    size: "≈ 250 MB per episode",
  },
] as const;

// Clean names are the layout media servers read ("plex" in the settings, as before; "jellyfin"
// names files the same way).
export const NAMING = [
  { value: "plex", label: "Clean names" },
  { value: "keep", label: "Keep my names" },
] as const;

const EXAMPLES = [
  {
    from: "[Group] DBZ - 001 [480p].mkv",
    folder: "TV\\Dragon Ball Z (1989)\\Season 01\\",
    name: "Dragon Ball Z (1989) - S01E01 - The New Threat.mkv",
  },
  {
    from: "Broly the Legendary Super Saiyan.avi",
    folder: "Movies\\Dragon Ball Z - Broly - The Legendary Super Saiyan (1993)\\",
    name: "Dragon Ball Z - Broly - The Legendary Super Saiyan (1993).avi",
  },
];

/**
 * The library standard, how files are named, and the upscaling choices: chosen in setup, and
 * changed later in Settings. `onChange` hears each change as it's made.
 */
export function StandardChoices({
  settings,
  onChange: change,
}: {
  settings: Settings;
  onChange: (part: Partial<Settings>) => void;
}) {
  return (
    <>
      <RadioGroup.Root
        aria-label="Standard"
        value={settings.standard}
        onValueChange={(value) => change({ standard: value as Settings["standard"] })}
        className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-3"
      >
        {STANDARDS.map((standard) => (
          <RadioGroup.Item
            key={standard.value}
            value={standard.value}
            className="press group flex cursor-pointer flex-col gap-2.5 rounded-18 border-2 border-edge bg-glass p-4.5 text-left data-[state=checked]:border-accent data-[state=checked]:bg-accent/10"
          >
            <span className="flex w-full items-center justify-between gap-2">
              <span className="font-extrabold text-17">{standard.name}</span>
              <RadioRing />
            </span>
            {standard.recommended && (
              <span className="inline-flex h-5.5 w-fit items-center rounded-full bg-accent px-2 font-extrabold text-11 text-on-accent">
                Recommended
              </span>
            )}
            <span className="text-13 text-fg-soft">{standard.spec}</span>
            <span className="text-13 text-fg-muted">{standard.text}</span>
            <span className="font-mono text-12 text-fg-muted group-data-[state=checked]:text-accent-fg">
              {standard.size}
            </span>
          </RadioGroup.Item>
        ))}
        <div
          aria-disabled="true"
          className="flex flex-col gap-2.5 rounded-18 border-2 border-edge border-dashed p-4.5 text-fg-muted"
        >
          <span className="font-extrabold text-17 text-fg-soft">Custom</span>
          <span className="text-13">Pick every detail yourself</span>
          <span className="text-13">
            Resolution, codec and quality, which audio languages to keep, subtitle handling.
          </span>
          <span className="font-mono text-12">Not ready yet</span>
        </div>
      </RadioGroup.Root>

      <div className="flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="font-extrabold text-15">File names</span>
          <Segmented
            label="File names"
            value={settings.naming === "keep" ? "keep" : "plex"}
            options={NAMING}
            onChange={(naming) => change({ naming })}
          />
        </div>
        <NamePreview keep={settings.naming === "keep"} />
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3">
        <Toggle
          label="Upscale SD with AI"
          text="480p and 576p sources get the best quality model."
          checked={settings.upscaleSd}
          onChange={(upscaleSd) => change({ upscaleSd })}
        />
        <Toggle
          label="Fast upscale for 720p"
          text="A quicker model where the gain is smaller."
          checked={settings.upscale720}
          onChange={(upscale720) => change({ upscale720 })}
        />
      </div>
    </>
  );
}

function NamePreview({ keep }: { keep: boolean }) {
  return (
    <div className="flex flex-col gap-3 overflow-x-auto rounded-16 bg-inset px-4 py-3.5 font-mono text-12">
      {EXAMPLES.map((example) => (
        <div key={example.from} className="flex flex-col gap-1 whitespace-nowrap">
          <span className="text-fg-faint">{example.from}</span>
          <span className="text-fg">
            → {example.folder}
            {keep ? example.from : example.name}
          </span>
        </div>
      ))}
      {keep && (
        <span className="font-sans text-12 text-fg-muted">
          Files keep their names, and still go into a folder per show, season and movie.
        </span>
      )}
    </div>
  );
}

export function Toggle(props: {
  label: string;
  text: string;
  checked: boolean;
  onChange: (on: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-3.5 rounded-16 border border-edge bg-glass px-4 py-3.5">
      <Switch
        id={id}
        checked={props.checked}
        onCheckedChange={props.onChange}
        aria-describedby={`${id}-text`}
      />
      <span className="flex flex-col gap-0.5">
        <label htmlFor={id} className="cursor-pointer font-extrabold">
          {props.label}
        </label>
        <span id={`${id}-text`} className="text-13 text-fg-muted">
          {props.text}
        </span>
      </span>
    </div>
  );
}

function RadioRing() {
  return (
    <span
      aria-hidden="true"
      className="inline-flex size-5.5 items-center justify-center rounded-full border-2 border-control group-data-[state=checked]:border-accent"
    >
      <span className="size-2.5 rounded-full bg-accent opacity-0 group-data-[state=checked]:opacity-100" />
    </span>
  );
}
