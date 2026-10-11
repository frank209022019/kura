/** How Kura writes sizes, times, codecs, languages and lists, on every screen. */

/** A path's file name and its folder. */
export function split(path: string): [string, string] {
  const at = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return [path.slice(at + 1), path.slice(0, at)];
}

/** 24:10, or 1:32:05 past an hour. */
export function clockTime(seconds: number): string {
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = String(whole % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/** "1 h 32 min", or "24 min". */
export function clockLength(minutes: number): string {
  const whole = Math.round(minutes);
  return whole >= 60 ? `${Math.floor(whole / 60)} h ${whole % 60} min` : `${whole} min`;
}

/** "233 MB", or "1.1 GB" from a billion bytes. */
export function size(bytes: number): string {
  if (bytes >= 1e10) return `${Math.round(bytes / 1e9)} GB`; // "931 GB", "16 GB"
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

const CODECS: Record<string, string> = {
  h264: "H.264",
  hevc: "HEVC",
  av1: "AV1",
  mpeg2video: "MPEG-2",
  mpeg4: "MPEG-4",
  vp9: "VP9",
};

export function codecName(codec: string): string {
  return CODECS[codec] ?? codec.toUpperCase();
}

const LANGUAGES: Record<string, string> = {
  jpn: "Japanese",
  eng: "English",
  ger: "German",
  deu: "German",
  fre: "French",
  fra: "French",
  spa: "Spanish",
  ita: "Italian",
  por: "Portuguese",
  rus: "Russian",
  chi: "Chinese",
  zho: "Chinese",
  kor: "Korean",
  ara: "Arabic",
  unknown: "unnamed",
};

export function languages(codes: string[]): string {
  if (codes.length === 0) return "none";
  return codes.map((code) => LANGUAGES[code] ?? code.toUpperCase()).join(", ");
}

export function listed(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

/** A path inside a library folder, written from that folder: "TV\Trigun (1998)\Season 01". */
export function within(path: string, root: string): string {
  const folder = root.replace(/[\\/]+$/, "");
  const inside = path.slice(0, folder.length).toLowerCase() === folder.toLowerCase();
  return inside ? path.slice(folder.length).replace(/^[\\/]+/, "") : path;
}
