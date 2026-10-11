import { getCurrentWindow } from "@tauri-apps/api/window";
import { Minus, Square, X } from "lucide-react";
import type { ReactNode } from "react";
import { KuraLogo } from "@/components/kura-logo";

/**
 * Kura draws its own title bar (the window has no Windows frame). Drag it to
 * move the window; double-click it to maximise.
 */
export function TitleBar({ title = "Kura" }: { title?: string }) {
  return (
    <header data-tauri-drag-region className="flex min-h-13 shrink-0 items-center pl-5 select-none">
      <div data-tauri-drag-region className="flex flex-1 items-center gap-2.5">
        <span className="pointer-events-none flex items-center gap-2.5">
          <KuraLogo />
          <span className="font-extrabold text-14">{title}</span>
        </span>
      </div>
      <div className="flex">
        <WindowButton label="Minimize" onClick={() => getCurrentWindow().minimize()}>
          <Minus size={14} strokeWidth={1.6} />
        </WindowButton>
        <WindowButton label="Maximize" onClick={() => getCurrentWindow().toggleMaximize()}>
          <Square size={12} strokeWidth={1.6} />
        </WindowButton>
        <WindowButton label="Close" onClick={() => getCurrentWindow().close()}>
          <X size={14} strokeWidth={1.6} />
        </WindowButton>
      </div>
    </header>
  );
}

function WindowButton(props: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={props.label}
      onClick={props.onClick}
      className="inline-flex h-13 w-11.5 cursor-pointer items-center justify-center text-fg transition-colors duration-120 hover:bg-white/8"
    >
      {props.children}
    </button>
  );
}
