// Run with: node --test "scripts/*.test.mjs"
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { markdown, renderPage, versions } from "./downloads-page.mjs";

function release(version, { draft = false, body = "### Added\n- Something new.", date = "2026-10-11T08:00:00Z" } = {}) {
  return {
    tag_name: `v${version}`,
    draft,
    prerelease: false,
    published_at: date,
    body,
    html_url: `https://github.com/frankgrobbelaar/kura/releases/tag/v${version}`,
    assets: [
      {
        name: `Kura_${version}_x64-setup.exe`,
        size: 19_110_590,
        digest: "sha256:9d127af3dd47fad7284dbd861bd5723fe9ab5b2eb77d78e6f7be22743b98ae2c",
        browser_download_url: `https://github.com/frankgrobbelaar/kura/releases/download/v${version}/Kura_${version}_x64-setup.exe`,
      },
      { name: "latest.json", size: 900, browser_download_url: "https://example.invalid/latest.json" },
    ],
  };
}

describe("downloads page", () => {
  it("says Kura is on its way until the first release", () => {
    const page = renderPage([]);

    assert.match(page, /Kura is on its way/);
    assert.doesNotMatch(page, /Download for Windows/);
  });

  it("offers the newest version first and keeps the earlier ones below", () => {
    const page = renderPage([release("0.9.0"), release("0.10.0", { date: "2026-11-02T08:00:00Z" }), release("0.11.0", { draft: true })]);

    assert.match(page, /<h1 id="latest">Kura 0\.10\.0<\/h1>/);
    assert.match(page, /Released 2 Nov 2026/);
    assert.match(page, /href="https:\/\/github\.com\/frankgrobbelaar\/kura\/releases\/download\/v0\.10\.0\/Kura_0\.10\.0_x64-setup\.exe">Download for Windows/);
    assert.match(page, /Kura_0\.10\.0_x64-setup\.exe · 19\.1 MB/);
    assert.match(page, /SHA-256 9d127af3dd47fad7284dbd861bd5723fe9ab5b2eb77d78e6f7be22743b98ae2c/);
    assert.match(page, /Earlier versions[\s\S]*Kura 0\.9\.0/);
    assert.doesNotMatch(page, /0\.11\.0/);
  });

  it("says before installing that Kura is for your own videos, never for piracy", () => {
    const page = renderPage([release("0.10.0")]);

    assert.match(page, /Before you install<\/h2>\s*<ul class="facts">\s*<li><strong>For your own videos\.<\/strong>/);
    assert.match(page, /never searches for, downloads or shares video\. It isn't for piracy in any form/);
  });

  it("leaves out drafts and tags that aren't versions", () => {
    const list = versions([release("0.1.0"), release("0.2.0", { draft: true }), { ...release("0.3.0"), tag_name: "nightly" }]);

    assert.deepEqual(
      list.map((each) => each.version),
      ["0.1.0"],
    );
  });

  it("shows what's new up front and folds every commit away", () => {
    const body = "### Added\n- Scanning.\n\n### Every change since 0.1.0\n\n- Scan folders ([abc1234](https://github.com/frankgrobbelaar/kura/commit/abc1234))\n";

    const page = renderPage([release("0.2.0", { body })]);

    assert.match(page, /What's new in 0\.2\.0<\/h2><h3>Added<\/h3>\n<ul><li>Scanning\.<\/li><\/ul><details><summary>Every change in 0\.2\.0<\/summary>/);
  });

  it("never lets release notes inject markup", () => {
    const page = renderPage([release("0.2.0", { body: '- <script>alert("x")</script>' })]);

    assert.doesNotMatch(page, /<script>alert/);
    assert.match(page, /&lt;script&gt;alert\(&quot;x&quot;\)&lt;\/script&gt;/);
  });
});

describe("markdown", () => {
  it("joins wrapped list lines, and renders headings, links, bold and code", () => {
    const html = markdown(
      "### Fixed\n- The update card no longer\n  hides behind dialogs.\n- See [the notes](https://example.com/notes) and `kura export`.\n\n**Full changelog**: https://example.com/compare",
    );

    assert.equal(
      html,
      [
        "<h3>Fixed</h3>",
        '<ul><li>The update card no longer hides behind dialogs.</li><li>See <a href="https://example.com/notes">the notes</a> and <code>kura export</code>.</li></ul>',
        '<p><strong>Full changelog</strong>: <a href="https://example.com/compare">https://example.com/compare</a></p>',
      ].join("\n"),
    );
  });

  it("only links web addresses", () => {
    assert.equal(markdown("[click](javascript:alert(1))"), "<p>[click](javascript:alert(1))</p>");
  });
});
