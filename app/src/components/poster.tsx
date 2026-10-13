import { type TitleSummary, useCover, usePoster } from "@/lib/engine";
import { cn } from "@/lib/utils";

/**
 * A title's poster, or in its place the boards' placeholder: the featured blue with its orange
 * orb, and the title's first letters.
 */
export function Poster({ title, className }: { title: TitleSummary; className?: string }) {
  const address = usePoster(title.id, title.hasPoster);
  return <Frame name={title.name} address={address} className={className} />;
}

/** AniList's cover of a title the library doesn't have, as a poster. */
export function Cover(props: { name: string; cover: string | null; className?: string }) {
  const address = useCover(props.cover);
  return <Frame name={props.name} address={address} className={props.className} />;
}

function Frame(props: { name: string; address: string | null; className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "relative aspect-[2/3] overflow-hidden rounded-14 bg-featured",
        props.className,
      )}
    >
      {props.address ? (
        <img src={props.address} alt="" className="absolute inset-0 size-full object-cover" />
      ) : (
        <>
          <span className="-right-[22%] -top-[12%] absolute aspect-square w-[76%] rounded-full bg-featured-orb" />
          <span className="absolute right-2.5 bottom-3 left-3 font-extrabold text-36 text-white leading-none tracking-[-0.03em]">
            {initials(props.name)}
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
