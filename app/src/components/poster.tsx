import { type TitleSummary, usePoster } from "@/lib/engine";
import { cn } from "@/lib/utils";

/**
 * A title's poster, or in its place the boards' placeholder: the featured blue with its orange
 * orb, and the title's first letters.
 */
export function Poster({ title, className }: { title: TitleSummary; className?: string }) {
  const address = usePoster(title.id, title.hasPoster);
  return (
    <div
      aria-hidden="true"
      className={cn("relative aspect-[2/3] overflow-hidden rounded-14 bg-featured", className)}
    >
      {address ? (
        <img src={address} alt="" className="absolute inset-0 size-full object-cover" />
      ) : (
        <>
          <span className="-right-[22%] -top-[12%] absolute aspect-square w-[76%] rounded-full bg-featured-orb" />
          <span className="absolute right-2.5 bottom-3 left-3 font-extrabold text-36 text-white leading-none tracking-[-0.03em]">
            {initials(title.name)}
          </span>
        </>
      )}
    </div>
  );
}

/** "Dragon Ball Z" is "DBZ"; one word gives its first four letters. */
function initials(name: string): string {
  const words = name.split(/[\s:·\-–]+/).filter(Boolean);
  if (words.length === 1) return (words[0] ?? "").slice(0, 4);
  return words
    .slice(0, 3)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}
