import { describe, expect, it } from "vitest";
import type { FranchiseSummary, Job, TitleSummary } from "@/lib/engine";
import { convertible } from "@/test/convert";
import {
  episodeCode,
  gpuTime,
  jobGroups,
  nights,
  open,
  playTime,
  retryIn,
  sizeClass,
  totals,
  tree,
} from "./convert";

function franchise(id: number, name: string, titles: [number, string][]): FranchiseSummary {
  return {
    id,
    name,
    titles: titles.map(([titleId, title]) => ({ id: titleId, name: title }) as TitleSummary),
  } as FranchiseSummary;
}

describe("tree", () => {
  it("groups files by franchise, title and season, unmatched files last", () => {
    const files = [
      convertible(1),
      convertible(2, { season: 2 }),
      convertible(3, { titleId: 2, title: "Dragon Ball GT" }),
      convertible(4, { titleId: 3, title: "Naruto" }),
      convertible(5, { titleId: null, title: null, season: null }),
    ];
    const franchises = [
      franchise(1, "Dragon Ball", [
        [1, "Dragon Ball Z"],
        [2, "Dragon Ball GT"],
      ]),
      franchise(3, "Naruto", [[3, "Naruto"]]),
    ];

    const groups = tree(files, franchises);

    expect(groups.map((group) => [group.name, group.titles.map((t) => t.name)])).toEqual([
      ["Dragon Ball", ["Dragon Ball Z", "Dragon Ball GT"]],
      ["Naruto", ["Naruto"]],
      ["Not matched yet", ["Not matched yet"]],
    ]);
    expect(groups[0]?.titles[0]?.seasons.map((season) => season.label)).toEqual([
      "Season 1",
      "Season 2",
    ]);
    expect(groups[2]?.titles[0]?.seasons.map((season) => season.label)).toEqual(["The film"]);
  });
});

describe("totals", () => {
  it("adds up a choice for one way of converting", () => {
    const files = [convertible(1), convertible(2, { height: 720, aspect: "16:9", drive: "F:" })];

    const found = totals(files, "best");

    expect(found).toMatchObject({
      files: 2,
      seconds: 2880,
      gpuSeconds: 7200,
      sizeBefore: 466_000_000,
      sizeAfter: 900_000_000,
      byDrive: { "D:": 450_000_000, "F:": 450_000_000 },
      sources: "SD 480p · 4:3, 720p · 16:9",
    });
  });

  it("leaves out files that won't play or wait in the queue already", () => {
    const files = [
      convertible(1),
      convertible(2, { broken: true }),
      convertible(3, { waiting: true }),
    ];

    expect(open(files).map((file) => file.fileId)).toEqual([1]);
  });
});

describe("words", () => {
  it("says GPU time the way the boards do", () => {
    expect(gpuTime(180)).toBe("3 min");
    expect(gpuTime(720)).toBe("12 min");
    expect(gpuTime(3500)).toBe("58 min");
    expect(gpuTime(3600)).toBe("1 h");
    expect(gpuTime(35 * 3600)).toBe("35 h");
    expect(gpuTime(12 * 24 * 3600)).toBe("12 days");
  });

  it("counts nights of eight hours", () => {
    expect(nights(35 * 3600)).toBe("about 5 nights");
    expect(nights(9 * 3600)).toBe("about 2 nights");
    expect(nights(3600)).toBe("less than a night");
  });

  it("says how long video plays", () => {
    expect(playTime(35 * 1440)).toBe("14 h 0 min");
    expect(playTime(1440)).toBe("24 min");
  });

  it("names a picture's size class", () => {
    expect([sizeClass(480), sizeClass(576), sizeClass(720), sizeClass(2160)]).toEqual([
      "SD 480p",
      "SD 576p",
      "720p",
      "4K",
    ]);
  });
});

describe("the queue's groups", () => {
  const job = (id: number, more: Partial<Job> = {}): Job =>
    ({
      id,
      title: "Dragon Ball Z",
      titleId: 1,
      season: 1,
      episode: id,
      path: `D:\\Anime\\Dragon Ball Z (1989) - S01E0${id}.mkv`,
      ...more,
    }) as Job;

  it("runs a title's season together, in the queue's order", () => {
    const groups = jobGroups([job(1), job(2), job(3, { season: 2 }), job(4)]);

    expect(groups.map((group) => [group.label, group.jobs.length])).toEqual([
      ["Dragon Ball Z · Season 1", 2],
      ["Dragon Ball Z · Season 2", 1],
      ["Dragon Ball Z · Season 1", 1],
    ]);
  });

  it("codes an episode, or names a film's file", () => {
    expect(episodeCode(job(6))).toBe("S01E06");
    expect(episodeCode(job(7, { season: null, episode: null, path: "D:\\Akira.mkv" }))).toBe(
      "Akira.mkv",
    );
  });
});

describe("retryIn", () => {
  it("says when Kura tries again, in whole minutes", () => {
    const now = Date.parse("2026-10-11T10:00:00+02:00");
    expect(retryIn("2026-10-11T10:05:00+02:00", now)).toBe("in 5 minutes");
    expect(retryIn("2026-10-11T08:01:30+00:00", now)).toBe("in 2 minutes");
    expect(retryIn("2026-10-11T10:00:30+02:00", now)).toBe("in a minute");
    expect(retryIn("2026-10-11T09:59:00+02:00", now)).toBe("in a moment");
  });
});
