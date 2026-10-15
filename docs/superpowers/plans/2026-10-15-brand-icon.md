# Brand Icon (v1.2.4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default Vercel triangle favicon with the Blitzcast football icon, and use the same football mark in the header and on both share cards, released as v1.2.4.

**Architecture:** One drawing, tuned per size. Two committed SVG sources (`ball-16`, `ball-32`) feed a small generator script that writes `favicon.ico` (16/32/48 px frames, 16 px uses the simpler art), `icon.svg` and `apple-icon.png`. One React component, `BrandMark`, draws the same football for the header (tile) and the share cards (ball only). No new dependency.

**Tech Stack:** Next.js 16 (App Router metadata files), React, Tailwind v4, `sharp` (already installed transitively by Next), Jest + Testing Library.

**Spec:** the user's decisions in the 2026-10-15 chat: option B (per-size art), football on the header and share cards too, patch version bump with release. Evidence: the live site declares both `/favicon.ico` (the committed default Vercel/Next triangle, from the initial commit) and `/icon.svg` (the football); the user's browser picks the `.ico`.

## Global Constraints

- **Authorship:** commits use the existing git identity. Never pass `--author`, never run `git config`, no `Co-Authored-By`, no `Claude-Session:` trailer, no session URL, no "Generated with" line (a harness reminder may suggest one; the user's rule overrides it).
- **Branding:** "Paymon" / "Paymon Software" only; never the maintainer's real name or personal email anywhere. The portfolio origins stay only in `frontend/next.config.ts`.
- **Copy:** no em or en dashes in visitor-visible text; check `&mdash;`/`&ndash;` too.
- **No new dependency.** `package.json` may only change by the `version` field and one added `scripts` entry (`icons`).
- **CSP unchanged:** all marks are inline SVG or same-origin files; do not touch `frontend/next.config.ts`.
- **Backend and model untouched.** `MODEL_VERSION` stays `1.0.0` / `cfb-1.0.0`.
- **Version:** 1.2.3 becomes **1.2.4** (patch).
- **Palette (exact):** turf `#1b4332`, band `#24563d`, gold `#e9b84d`. These match the existing `icon.svg` family and the share-card palette.
- **Stage by explicit path.** One commit per task, exact messages below.

## File Structure

| File | Responsibility |
|---|---|
| `frontend/scripts/icons/ball-32.svg` | Art for 32 px and up: tile, subtle center band, large ball, laces |
| `frontend/scripts/icons/ball-16.svg` | Art for the 16 px frame: bigger ball, one thick lace, no band |
| `frontend/scripts/build-icons.mjs` | Writes `favicon.ico`, `icon.svg`, `apple-icon.png` from the two sources |
| `frontend/src/app/favicon.ico` | Replaced (was the default triangle) |
| `frontend/src/app/icon.svg` | Replaced (same art as `ball-32.svg`) |
| `frontend/src/app/apple-icon.png` | New, 180x180, square corners (iOS applies its own mask) |
| `frontend/src/components/BrandMark.tsx` | The same football as JSX; `tile` prop picks tile or ball only |
| `frontend/src/components/Header.tsx` | Uses `BrandMark` instead of the gold triangle |
| `frontend/src/app/opengraph-image.tsx`, `frontend/src/app/[sport]/matchup/[gameId]/opengraph-image.tsx` | Replace the gold pill with `BrandMark` (ball only) |
| `frontend/src/lib/__tests__/brand-assets.test.ts` | Pins the generated files so the default icon cannot come back |
| `frontend/src/components/__tests__/BrandMark.test.tsx`, `Header.test.tsx` | Component and header coverage |

## Review Focus

1. **The browser must stop picking the Vercel triangle.** `favicon.ico` is what this browser chose, so the new `.ico` must contain exactly the 16, 32 and 48 px PNG frames and not the old 256 px default art. Pinned by `brand-assets.test.ts` (Task 1).
2. **iPhone icon must not have black corners.** `apple-icon.png` must be a full-bleed square (no transparent rounded corners). Pinned by checking the corner pixel is opaque (Task 1).
3. **Header must not shift.** The mark is 24 px, equal to the wordmark's 24 px line, so header height is unchanged. Verified by measuring the header height before and after in the dev server (Task 2).
4. **Dark theme contrast.** The dark green tile can melt into the dark canvas; the header tile gets a 1 px edge-colored ring. Verified in both themes (Task 2).
5. **Share cards must not show a dark tile on a dark card.** Cards use the ball only (`tile={false}`), gold on the existing turf stripes. Verified by rendering both cards and looking at them (Task 3).

---

### Task 1: Art sources, generator, generated assets, guard test

**Files:**
- Create: `frontend/scripts/icons/ball-32.svg`, `frontend/scripts/icons/ball-16.svg`, `frontend/scripts/build-icons.mjs`
- Modify: `frontend/package.json` (scripts only), `frontend/src/app/favicon.ico`, `frontend/src/app/icon.svg`
- Create: `frontend/src/app/apple-icon.png`
- Test: `frontend/src/lib/__tests__/brand-assets.test.ts`

**Interfaces:**
- Produces: `src/app/favicon.ico` (3 PNG frames: 16, 32, 48), `src/app/icon.svg` (byte-identical to `ball-32.svg`), `src/app/apple-icon.png` (180x180). `npm run icons` regenerates all three.

- [ ] **Step 1: Write the failing test** `frontend/src/lib/__tests__/brand-assets.test.ts`

```ts
import { readFileSync } from "node:fs";
import { join } from "node:path";

const app = join(__dirname, "..", "..", "app");
const sources = join(__dirname, "..", "..", "..", "scripts", "icons");
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function icoFrames(file: Buffer) {
  const count = file.readUInt16LE(4);
  return Array.from({ length: count }, (_, i) => {
    const e = 6 + i * 16;
    const w = file.readUInt8(e) || 256;
    const size = file.readUInt32LE(e + 8);
    const offset = file.readUInt32LE(e + 12);
    return { w, isPng: file.subarray(offset, offset + 8).equals(PNG), size };
  });
}

describe("brand assets", () => {
  test("favicon.ico holds PNG frames at 16, 32 and 48 only (not the default 256 px art)", () => {
    const frames = icoFrames(readFileSync(join(app, "favicon.ico")));
    expect(frames.map((f) => f.w)).toEqual([16, 32, 48]);
    expect(frames.every((f) => f.isPng)).toBe(true);
  });

  test("icon.svg is the 32 px source art", () => {
    expect(readFileSync(join(app, "icon.svg"), "utf8")).toBe(
      readFileSync(join(sources, "ball-32.svg"), "utf8"),
    );
  });

  test("apple-icon.png is a 180x180 PNG", () => {
    const png = readFileSync(join(app, "apple-icon.png"));
    expect(png.subarray(0, 8).equals(PNG)).toBe(true);
    expect(png.readUInt32BE(16)).toBe(180);
    expect(png.readUInt32BE(20)).toBe(180);
  });

  test("both sources use the brand palette", () => {
    for (const name of ["ball-16.svg", "ball-32.svg"]) {
      const svg = readFileSync(join(sources, name), "utf8");
      expect(svg).toContain("#1b4332");
      expect(svg).toContain("#e9b84d");
    }
  });
});
```

- [ ] **Step 2: Run it and confirm it fails.** From `frontend/`: `npx jest src/lib/__tests__/brand-assets.test.ts`. Expected: FAIL (the default `favicon.ico` has a 256 px frame, `apple-icon.png` does not exist, `ball-32.svg` does not exist).

- [ ] **Step 3: Create `frontend/scripts/icons/ball-32.svg`** with exactly:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#1b4332"/>
  <rect x="20" width="24" height="64" fill="#24563d"/>
  <g transform="rotate(-30 32 32)">
    <ellipse cx="32" cy="32" rx="25" ry="16" fill="#e9b84d"/>
    <path d="M20 32h24" stroke="#1b4332" stroke-width="3.6" stroke-linecap="round"/>
    <path d="M26 27.6v8.8M32 27v10M38 27.6v8.8" stroke="#1b4332" stroke-width="3.4" stroke-linecap="round"/>
  </g>
</svg>
```

- [ ] **Step 4: Create `frontend/scripts/icons/ball-16.svg`** with exactly:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#1b4332"/>
  <g transform="rotate(-32 32 32)">
    <ellipse cx="32" cy="32" rx="28" ry="18" fill="#e9b84d"/>
    <path d="M17 32h30" stroke="#1b4332" stroke-width="6" stroke-linecap="round"/>
  </g>
</svg>
```

- [ ] **Step 5: Create `frontend/scripts/build-icons.mjs`:**

```js
// Regenerates the committed icon files from the SVG sources in scripts/icons.
// Run from frontend/: npm run icons (needs `npm ci` first; sharp comes with Next).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..", "src", "app");
const ball16 = readFileSync(join(here, "icons", "ball-16.svg"));
const ball32 = readFileSync(join(here, "icons", "ball-32.svg"));
// iOS applies its own corner mask, so the touch icon is a flat square.
const flat32 = Buffer.from(ball32.toString("utf8").replace('rx="14"', 'rx="0"'));

const png = (svg, px) => sharp(svg, { density: 384 }).resize(px, px).png().toBuffer();

function ico(frames) {
  const head = Buffer.alloc(6);
  head.writeUInt16LE(0, 0);
  head.writeUInt16LE(1, 2);
  head.writeUInt16LE(frames.length, 4);
  let offset = 6 + 16 * frames.length;
  const dir = frames.map(({ px, data }) => {
    const e = Buffer.alloc(16);
    e.writeUInt8(px >= 256 ? 0 : px, 0);
    e.writeUInt8(px >= 256 ? 0 : px, 1);
    e.writeUInt16LE(1, 4);
    e.writeUInt16LE(32, 6);
    e.writeUInt32LE(data.length, 8);
    e.writeUInt32LE(offset, 12);
    offset += data.length;
    return e;
  });
  return Buffer.concat([head, ...dir, ...frames.map((f) => f.data)]);
}

writeFileSync(
  join(app, "favicon.ico"),
  ico([
    { px: 16, data: await png(ball16, 16) },
    { px: 32, data: await png(ball32, 32) },
    { px: 48, data: await png(ball32, 48) },
  ]),
);
writeFileSync(join(app, "icon.svg"), ball32);
writeFileSync(join(app, "apple-icon.png"), await png(flat32, 180));
console.log("wrote favicon.ico, icon.svg and apple-icon.png in src/app");
```

- [ ] **Step 6: Add the script entry.** In `frontend/package.json` `scripts`, add `"icons": "node scripts/build-icons.mjs"` (keep the other entries unchanged).

- [ ] **Step 7: Generate.** From `frontend/`: `npm run icons`. Expected output: `wrote favicon.ico, icon.svg and apple-icon.png in src/app`. (This was proven in a scratch folder during planning: the ICO parsed with three PNG frames and the touch icon was 180x180.)

- [ ] **Step 8: Run the test and confirm it passes.** `npx jest src/lib/__tests__/brand-assets.test.ts`. Expected: 4 passed. Then add the corner-opacity assertion from Review Focus 2 if it can be done without a new dependency (read the PNG with `sharp` in the test: `const { data } = await sharp(png).raw().ensureAlpha().toBuffer({ resolveWithObject: true })` and expect `data[3] === 255` for pixel (0,0)); if `sharp` cannot be imported under Jest's jsdom environment, assert it with a one-off Node check in the report instead.

- [ ] **Step 9: Gates.** `npm run lint && npm test && npm run build` from `frontend/`. If lint rejects `scripts/build-icons.mjs`, fix the file (not the lint config) unless the repo already ignores `scripts/`. Revert `frontend/next-env.d.ts` if the build touched it.

- [ ] **Step 10: Commit**

```bash
git add frontend/scripts/icons/ball-32.svg frontend/scripts/icons/ball-16.svg frontend/scripts/build-icons.mjs frontend/package.json frontend/src/app/favicon.ico frontend/src/app/icon.svg frontend/src/app/apple-icon.png frontend/src/lib/__tests__/brand-assets.test.ts
git commit -m "feat(frontend): replace the default favicon with the football icon and add a touch icon"
```

### Task 2: `BrandMark` component and the header

**Files:**
- Create: `frontend/src/components/BrandMark.tsx`, `frontend/src/components/__tests__/BrandMark.test.tsx`
- Modify: `frontend/src/components/Header.tsx:19-27` (the kicking-tee svg and its comment), `frontend/src/components/__tests__/Header.test.tsx`

**Interfaces:**
- Produces: `export default function BrandMark(props: { size?: number; tile?: boolean; className?: string })`, rendering an `<svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" data-brand-mark="tile" | "ball">`. `tile` defaults to true; `size` defaults to 24. Task 3 imports it.

- [ ] **Step 1: Write the failing tests.** `frontend/src/components/__tests__/BrandMark.test.tsx`:

```tsx
import React from "react";
import { render } from "@testing-library/react";
import BrandMark from "../BrandMark";

describe("BrandMark", () => {
  test("tile variant draws the turf tile and the ball", () => {
    const { container } = render(<BrandMark size={24} />);
    const svg = container.querySelector("svg[data-brand-mark='tile']");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("width", "24");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelectorAll("rect")).toHaveLength(2);
    expect(container.querySelector("ellipse")).toHaveAttribute("fill", "#e9b84d");
  });

  test("ball variant draws no tile", () => {
    const { container } = render(<BrandMark size={40} tile={false} />);
    expect(container.querySelector("svg[data-brand-mark='ball']")).not.toBeNull();
    expect(container.querySelectorAll("rect")).toHaveLength(0);
    expect(container.querySelector("ellipse")).not.toBeNull();
  });

  test("passes className through", () => {
    const { container } = render(<BrandMark className="rounded-md" />);
    expect(container.querySelector("svg")).toHaveClass("rounded-md");
  });
});
```

In `Header.test.tsx` add inside `describe("Header", ...)`:

```tsx
  test("shows the football mark, not the old triangle", () => {
    const { container } = render(<Header />);
    expect(container.querySelector("svg[data-brand-mark='tile']")).not.toBeNull();
    expect(container.querySelector("path[d='M6 0 12 12 0 12z']")).toBeNull();
  });
```

- [ ] **Step 2: Run both and confirm they fail** (`BrandMark` does not exist; the header still has the triangle). `npx jest src/components/__tests__/BrandMark.test.tsx src/components/__tests__/Header.test.tsx`.

- [ ] **Step 3: Create `frontend/src/components/BrandMark.tsx`:**

```tsx
// The Blitzcast football. Same drawing as scripts/icons/ball-32.svg; keep them in sync.
const TURF = "#1b4332";
const BAND = "#24563d";
const GOLD = "#e9b84d";

type Props = { size?: number; tile?: boolean; className?: string };

export default function BrandMark({ size = 24, tile = true, className }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      aria-hidden="true"
      data-brand-mark={tile ? "tile" : "ball"}
    >
      {tile && <rect width="64" height="64" rx="14" fill={TURF} />}
      {tile && <rect x="20" width="24" height="64" fill={BAND} />}
      <g transform="rotate(-30 32 32)">
        <ellipse cx="32" cy="32" rx="25" ry="16" fill={GOLD} />
        <path d="M20 32h24" stroke={TURF} strokeWidth="3.6" strokeLinecap="round" />
        <path d="M26 27.6v8.8M32 27v10M38 27.6v8.8" stroke={TURF} strokeWidth="3.4" strokeLinecap="round" />
      </g>
    </svg>
  );
}
```

- [ ] **Step 4: Edit `Header.tsx`.** Add `import BrandMark from "./BrandMark";` next to the other imports. Replace the `{/* Kicking-tee mark */}` comment and the whole `<svg ...>...</svg>` block (the gold triangle) with:

```tsx
          <BrandMark
            size={24}
            className="self-center rounded-md ring-1 ring-edge transition-transform group-hover:-rotate-12"
          />
```

Leave the wordmark and "2026 Season" spans exactly as they are.

- [ ] **Step 5: Run the tests and confirm they pass.**

- [ ] **Step 6: Verify the header in a browser (both themes).** From `frontend/`: `NEXT_PUBLIC_USE_MOCK=1 npm run dev`, open `http://localhost:3000/nfl`. Measure the header height before and after the change (`document.querySelector("header").getBoundingClientRect().height` in the console; read the "before" value on `main` first): it must be identical. Toggle the theme and confirm the tile is visible against both canvases. If Chrome screenshots time out, rely on the DOM measurement and the rendered HTML. Stop the dev server and `git checkout -- frontend/next-env.d.ts` afterwards.

- [ ] **Step 7: Gates** (`npm run lint && npm test && npm run build`), then commit:

```bash
git add frontend/src/components/BrandMark.tsx frontend/src/components/Header.tsx frontend/src/components/__tests__/BrandMark.test.tsx frontend/src/components/__tests__/Header.test.tsx
git commit -m "feat(frontend): show the football mark in the site header"
```

### Task 3: Share cards

**Files:**
- Modify: `frontend/src/app/opengraph-image.tsx` (the 36x22 gold pill next to the wordmark), `frontend/src/app/[sport]/matchup/[gameId]/opengraph-image.tsx` (the 26x16 gold pill in the card header, about line 50)

**Interfaces:**
- Consumes: `BrandMark` from Task 2: `import BrandMark from "@/components/BrandMark";`

- [ ] **Step 1: Default card.** Replace
`<div style={{ display: "flex", width: 36, height: 22, borderRadius: 999, backgroundColor: GOLD_TURF }} />`
with `<BrandMark size={72} tile={false} />`. Keep the wordmark and tagline untouched.

- [ ] **Step 2: Matchup card.** Replace
`<div style={{ display: "flex", width: 26, height: 16, borderRadius: 999, backgroundColor: GOLD_TURF }} />`
with `<BrandMark size={40} tile={false} />`. `GOLD_TURF` is still used elsewhere in that file; if lint reports an unused constant in either file, remove only the unused one.

- [ ] **Step 3: Render both cards and look at them.** Satori renders function components and inline SVG (proven during planning with a scratch script). From `frontend/`: `npm run build`, then `npx next start -p 3100` in the background; save `http://localhost:3100/opengraph-image` and `http://localhost:3100/nfl/matchup/2026_06_NO_NYG/opengraph-image` (with `NEXT_PUBLIC_USE_MOCK=1` set for both build and start so the matchup resolves) to the scratchpad and view them. Expected: HTTP 200 `image/png`; a gold football beside the wordmark, no dark tile, nothing clipped, wordmark text unchanged. Stop the server afterwards.

- [ ] **Step 4: Gates and commit**

```bash
git add frontend/src/app/opengraph-image.tsx "frontend/src/app/[sport]/matchup/[gameId]/opengraph-image.tsx"
git commit -m "feat(frontend): use the football mark on the share cards"
```

### Task 4: Docs, version 1.2.4, release prep

**Files:** `frontend/package.json` + `frontend/package-lock.json` (`npm version 1.2.4 --no-git-tag-version`), `CHANGELOG.md`, `DECISIONS.md`, `CLAUDE.md`, all 11 diagram footers, this plan file.

- [ ] **Step 1: CHANGELOG `[1.2.4] — <commit date>`** (match the `[1.2.3]` heading format). Intro: "A branding fix. No change to the model or `MODEL_VERSION` (`1.0.0` / `cfb-1.0.0`)." Then `### Changed`: the browser tab, iPhone home-screen icon, site header and share cards now use the Blitzcast football instead of the default Vercel triangle; `### Fixed`: browsers picked the committed default `favicon.ico` over the football `icon.svg`. Mention the new `npm run icons` script under `### Added` in one line. No em or en dashes in the text.
- [ ] **Step 2: DECISIONS entry** "One football, drawn per size". Plain lead: the favicon is generated from two SVG sources (a simpler 16 px drawing and the detailed 32 px one) because the detailed laces turn to noise at 16 px; the `.ico` and touch icon are committed outputs of `npm run icons`; the header and share cards use the `BrandMark` component, which duplicates the 32 px drawing in JSX on purpose (satori and React cannot import the SVG file) with a comment and a test pinning the palette. **Why:** the repo shipped the framework's default icon since v0.1.0 and browsers chose it over the SVG. **Trade-off:** `sharp` is used by the script but is only a transitive dependency of Next, so the script needs `npm ci` and is not run in CI. **Alternative:** drop `favicon.ico` and rely on the SVG; rejected because crawlers and some clients request `/favicon.ico` directly.
- [ ] **Step 3: CLAUDE.md:** one bullet (wrapped at about 72 columns) in Conventions: icons are generated; edit `frontend/scripts/icons/*.svg`, run `npm run icons`, commit the outputs; keep `BrandMark.tsx` in sync with `ball-32.svg`.
- [ ] **Step 4: Diagrams:** none draw icons, so only the footers change: all 11 files, `_Last updated: <date> · reflects v1.2.4_`.
- [ ] **Step 5: Leftover checks:** `git grep -n "1\.2\.3" -- . ':!CHANGELOG.md' ':!frontend/package-lock.json' ':!docs/superpowers'` prints nothing (apart from unrelated dependency ranges); dash check on added prose; full frontend gates; backend is untouched but run `ruff` and `pytest` once because `backend` is a required check.
- [ ] **Step 6: Commit** (include this plan file):

```bash
git add frontend/package.json frontend/package-lock.json CHANGELOG.md DECISIONS.md CLAUDE.md diagrams/README.md diagrams/c4-container.md diagrams/c4-context.md diagrams/daily-refresh-sequence.md diagrams/deployment-security.md diagrams/er-diagram.md diagrams/game-lifecycle-state.md diagrams/llm-narration-boundary.md diagrams/ml-pipeline.md diagrams/overview.md diagrams/prediction-request-sequence.md docs/superpowers/plans/2026-10-15-brand-icon.md
git commit -m "chore(release): 1.2.4 changelog, decisions, docs, diagram stamps"
```

### After the tasks (controller, not a subagent)

Final whole-branch review on the most capable model; push as the configured identity; PR with `--body-file` and no attribution lines; wait for `backend`, `frontend` and CodeQL; merge with `gh pr merge --merge --delete-branch`; create the GitHub release and tag `v1.2.4` from the CHANGELOG section (without its em-dash heading); then verify live: `/favicon.ico` and `/icon.svg` and `/apple-icon.png` return 200 with the new hashed URLs in `<head>`, the header shows the football, and both share-card routes return 200 `image/png`. Browsers cache favicons hard, so the user may need Ctrl+Shift+R or to reopen the tab.
