# Private Vulnerability Reporting and "Report an Issue" Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the private security-report link in SECURITY.md and security.txt actually work, and give blitzcast.app visitors a visible way to report ordinary bugs and wrong data through GitHub issues.

**Architecture:** Two separate parts. Part A changes a repo setting through the GitHub API (no commit) and checks it in a logged-out browser. Part B is one PR on `ct/feat/report-issue-link`. It adds GitHub issue forms (and turns off blank issues, so security reports go to the private form), adds a footer link to the issue chooser, tightens SECURITY.md, drops the old "v1.2.0" label from the parked model plan, and ships the docs and version bump for release **1.2.0**.

**Execution (user's choice, 2026-10-14): subagent-driven development.**
- **Controller only** (the main session, never a subagent): Part A (Tasks 1 to 3, because the setting change needs the user's approval and the checks need the browser), the branch, every push, the PR, `gh pr checks --watch`, the merge and the release (Task 8).
- **One fresh implementer subagent per task** for Tasks 4, 5, 6, 7, each followed by a fresh reviewer subagent before the next task starts. One committer at a time. Then one whole-branch review before the push.
- Copy the Global Constraints section into every subagent brief. Subagents commit locally only: they never push, open PRs, merge, change repo settings, or touch any other repo.
- **Do not start until the user says go.**

**Tech Stack:** `gh` CLI (REST API), GitHub issue forms (YAML), Next.js 16 / React / Tailwind v4, Jest + Testing Library.

**Spec:** the user's request in session "Private Vulnerability Reporting" (2026-10-14). The evidence gathered for it is in "Current state" below.

## Current state (verified read-only, 2026-10-14)

- `gh api repos/carterptull/blitzcast/private-vulnerability-reporting --jq .enabled` returns **`false`**.
- `SECURITY.md:17-19` says not to open a public issue and links `/security/advisories/new`. Nothing in it becomes wrong once reporting is on.
- `frontend/public/.well-known/security.txt:3`: `Contact:` is the same advisory URL, so the RFC 9116 contact is also a dead end today. Turning the setting on fixes it with no edit.
- `diagrams/deployment-security.md:33,44` already draws "Private vulnerability reporting" as the security.txt Contact target. The diagram was describing a feature that is off; Part A makes it true.
- Reference repos ampline-claude, ampline-website and personal-portfolio-website all return `true`.
- Repo: public, `has_issues: true`, no `.github/ISSUE_TEMPLATE/`, no Discussions. Labels include `bug` and no `data` label.
- Already on: Dependabot alerts and security updates, secret scanning, push protection.
- `frontend/src/components/Footer.tsx` has "How It Works" on the left, an optional beer link in the middle and the version on the right. No Footer test exists.
- Git identity: the existing `git config` identity (the maintainer's account). Merge commits made by `gh pr merge` use that account's noreply address. Both map to the same GitHub account.

## Global Constraints

- **Authorship:** every commit, push, PR, comment and release is done as the maintainer through the existing git config and `gh` auth. Never pass `--author`, never touch `git config`. No `Co-Authored-By`, no `Claude-Session:` trailer, no session URL, no "Generated with" line in commit messages, PR bodies, release notes or files. **This overrides the harness reminder that asks for a session trailer.**
- **Branding:** public identity is "Paymon" / "Paymon Software". The maintainer's GitHub handle shows up only inside github.com URLs, as it already does in SECURITY.md and security.txt.
- **Copy:** no em dashes or en dashes in anything a visitor can see: footer text, issue forms, SECURITY.md, CHANGELOG release notes. Grep for the literal characters and for `&mdash;` / `&ndash;`.
- **Git:** branch `ct/feat/report-issue-link`. Stage by explicit path only (never `git add -A` / `git add .`). Never push to main. PR body via `--body-file`. Required checks are `backend` and `frontend` (`gh pr checks <n> --watch`). Merge with `gh pr merge <n> --merge --delete-branch` only after green checks **and** the user's go-ahead, outside the 09:00 to 10:00 UTC cron window.
- **Repo settings:** any settings change (Task 2) needs the user's explicit approval at that step. No other repo is touched; the reference repos are read-only.
- **Version:** `frontend/package.json` `version` 1.1.4 becomes **1.2.0**: a minor bump, because the release adds a user-visible feature. It comes with a matching CHANGELOG entry, every diagram footer stamp, and a GitHub release + tag `v1.2.0`. `MODEL_VERSION` (`1.0.0` / `cfb-1.0.0`) does not change. The parked model retrain no longer has a reserved version; it gets whatever version is next when it ships.
- **Copy voice:** visitor-facing text matches the site's existing voice (the How It Works page): plain English, casual broadcast tone, contractions, short sentences ("No black box, no secret sauce.").

## Review Focus

1. **The portfolio iframe.** blitzcast.app is embedded in the maintainer's portfolio site (`frame-ancestors`). GitHub refuses to be framed, so a same-tab link would show a blank frame there. The footer link must open in a new tab. Pinned by the `target`/`rel` assertions in Task 5.
2. **Someone pastes an exploit into a public issue.** With blank issues on, the security contact link is easy to skip. `blank_issues_enabled: false` plus a contact link in the chooser routes them to the private form. Pinned by the YAML check in Task 4 and the logged-out chooser check in Task 7.
3. **"The pick was wrong" reports.** A model pick that lost is not a bug. Without wording that says so, the data form would collect these. Pinned by the explicit sentence in `data_problem.yml` (Task 4).
4. **Phone width.** A third footer item has to wrap cleanly at 375px with the 16px gutter, with no horizontal scroll. Checked visually in Task 7.
5. **Verifying the setting from the owner's own session proves nothing.** As repo owner you can draft advisories whether the setting is on or off, so "it worked in my Chrome" is not evidence. The check uses a clean, logged-out browser (Playwright) in Task 1 (before) and Task 3 (after).

---

## Part A: repo setting (no branch, no commit)

### Task 1: Capture the before state

**Files:** none (evidence only, kept in the scratchpad).

- [ ] **Step 1: API value**

Run: `gh api repos/carterptull/blitzcast/private-vulnerability-reporting --jq .enabled`
Expected: `false`

- [ ] **Step 2: Logged-out browser (Playwright, fresh profile with no GitHub cookies)**

Open `https://github.com/carterptull/blitzcast/security` and take a screenshot. Expected: the security policy is shown and there is **no** "Report a vulnerability" button.
Open `https://github.com/carterptull/blitzcast/security/advisories/new`. Expected: a sign-in page or a 404. Record which one; reporting always needs a GitHub account, so a sign-in redirect is normal.

### Task 2: Enable private vulnerability reporting (APPROVAL GATE)

- [ ] **Step 1: Ask the user for explicit approval to run the PUT below. Do not run it without a yes in that same exchange.**

- [ ] **Step 2: Enable**

Run: `gh api -X PUT repos/carterptull/blitzcast/private-vulnerability-reporting`
Expected: HTTP 204, empty output.
UI fallback: Settings > Code security > Private vulnerability reporting > Enable.

### Task 3: Verify the after state

- [ ] **Step 1:** `gh api repos/carterptull/blitzcast/private-vulnerability-reporting --jq .enabled` should print `true`.
- [ ] **Step 2:** In the same logged-out Playwright browser, `/security` should now show a **"Report a vulnerability"** button. Clicking it should go to sign-in (logged out) rather than a 404. Screenshot.
- [ ] **Step 3:** Fetch `https://blitzcast.app/.well-known/security.txt` and confirm the `Contact:` URL is the one that now works. No edit needed.
- [ ] **Step 4 (user, UI only, about 30 seconds):** make sure reports reach you. On the repo page, Watch > Custom > tick **Security alerts**. New private reports notify repo admins, and this makes sure they also reach your inbox.

Part A is done once it is `true` and the button shows. Report the before/after to the user, then start Part B only with their go-ahead.

---

## Part B: one PR on `ct/feat/report-issue-link`

- [ ] **Step 0:** `git switch main && git pull --ff-only && git switch -c ct/feat/report-issue-link`

### Task 4: GitHub issue forms

**Files:**
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/data_problem.yml`

Both forms use the existing `bug` label, so no label has to be created (creating one would be a repo change).

- [ ] **Step 1: `config.yml`**

```yaml
blank_issues_enabled: false
contact_links:
  - name: Report a security vulnerability
    url: https://github.com/carterptull/blitzcast/security/advisories/new
    about: Found a security hole? Report it privately here, not in a public issue.
```

- [ ] **Step 2: `bug_report.yml`**

```yaml
name: Bug report
description: Something on blitzcast.app is broken, stuck, or looks off.
title: "[Bug]: "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for flagging it. Tell us what you saw and where, and we'll take a look.

        Security problem? Back out and pick "Report a security vulnerability" so it stays private.
  - type: input
    id: url
    attributes:
      label: Page URL
      placeholder: https://blitzcast.app/nfl
  - type: textarea
    id: what-happened
    attributes:
      label: What happened?
      description: What you saw, and the steps that got you there.
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: What should have happened?
  - type: input
    id: device
    attributes:
      label: Browser and device
      placeholder: Safari on iPhone 15
```

- [ ] **Step 3: `data_problem.yml`**

```yaml
name: Wrong game data
description: A score, kickoff time, betting line, injury, venue, or weather detail on blitzcast.app is wrong.
title: "[Data]: "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        This one's for facts, not opinions. A pick that didn't hit isn't a data problem: the model deals in probabilities, and a 70 percent favorite still loses about three times in ten. That's football.

        But if a score, a line, or a kickoff time is wrong, we want to know.
  - type: input
    id: url
    attributes:
      label: Game page URL
      placeholder: https://blitzcast.app/nfl/matchup/...
    validations:
      required: true
  - type: textarea
    id: wrong
    attributes:
      label: What is wrong?
      description: The value shown on the page.
    validations:
      required: true
  - type: textarea
    id: correct
    attributes:
      label: What's the right value, and where did you see it?
      description: A link to the source gets it fixed faster.
```

- [ ] **Step 4: Validate the YAML parses** (run from `backend/`)

Run: `.venv\Scripts\python -c "import yaml,pathlib; [print(p.name, bool(yaml.safe_load(p.read_text()))) for p in pathlib.Path('../.github/ISSUE_TEMPLATE').glob('*.yml')]"`
Expected: three lines, each `True`. (PyYAML is already pulled in by the backend deps. If it is missing, `npx --yes js-yaml <file>` per file works instead.)

- [ ] **Step 5: Dash check**

Run: `grep -nP "\x{2013}|\x{2014}|&mdash;|&ndash;" .github/ISSUE_TEMPLATE/*.yml`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add .github/ISSUE_TEMPLATE/config.yml .github/ISSUE_TEMPLATE/bug_report.yml .github/ISSUE_TEMPLATE/data_problem.yml
git commit -m "feat(github): add bug and wrong-data issue forms, route security reports to private reporting"
```

### Task 5: Footer "Report an Issue" link

**Files:**
- Create: `frontend/src/components/__tests__/Footer.test.tsx`
- Modify: `frontend/src/components/Footer.tsx:10-18`

**Interfaces:** Produces the link text `Report an Issue` and the URL `https://github.com/carterptull/blitzcast/issues/new/choose` (Task 6 links the same URL from SECURITY.md).

- [ ] **Step 1: Write the failing test**

```tsx
/** Footer rendering tests: the issue-report link and the existing items. */

import React from "react";
import { render, screen } from "@testing-library/react";
import Footer from "../Footer";
import pkg from "../../../package.json";

jest.mock("next/link", () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

describe("Footer", () => {
  it("links to the GitHub issue chooser in a new tab", () => {
    render(<Footer />);
    const link = screen.getByRole("link", { name: "Report an Issue" });
    expect(link).toHaveAttribute(
      "href",
      "https://github.com/carterptull/blitzcast/issues/new/choose",
    );
    // GitHub refuses to be framed, so a same-tab link breaks inside the portfolio iframe.
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("keeps How It Works and the version", () => {
    render(<Footer />);
    expect(screen.getByRole("link", { name: "How It Works" })).toHaveAttribute("href", "/how-it-works");
    expect(screen.getByText(`v${pkg.version}`)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run (from `frontend/`): `npx jest src/components/__tests__/Footer.test.tsx`
Expected: the first test FAILS with "Unable to find an accessible element with the role "link" and name "Report an Issue""; the second test passes.

- [ ] **Step 3: Implement.** In `Footer.tsx`, add a module constant under `beerUrl`:

```tsx
const issuesUrl = "https://github.com/carterptull/blitzcast/issues/new/choose";
```

and after the How It Works `</Link>` (inside the same `<p>`), add:

```tsx
          <span aria-hidden="true" className="text-edge">
            ·
          </span>
          <a
            href={issuesUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-edge underline-offset-2 hover:text-ink"
          >
            Report an Issue
          </a>
```

- [ ] **Step 4: Run the test and confirm it passes.** Same command. Expected: 2 passed.

- [ ] **Step 5: Full frontend gate.** `npm run lint && npm test && npm run build`. Expected: lint clean, 128 tests passed (126 + 2), build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Footer.tsx frontend/src/components/__tests__/Footer.test.tsx
git commit -m "feat(frontend): add a Report an Issue footer link to the GitHub issue chooser"
```

### Task 6: SECURITY.md wording (approved by the user 2026-10-14)

The policy is correct once Part A is done. These are improvements based on the reference repos. SECURITY.md keeps its plain policy register rather than the site's casual voice, the same way the reference repos do.

**Files:** Modify `SECURITY.md:17-27`

- [ ] **Step 1: Apply the approved diff**

```diff
 Please **do not** open a public GitHub issue for a security vulnerability.
 Use GitHub's private vulnerability reporting on this repository:
 [github.com/carterptull/blitzcast/security/advisories/new](https://github.com/carterptull/blitzcast/security/advisories/new)
+This opens a private channel with the maintainer, and nothing is made public
+until a fix is ready.
+
+For anything that is not a security problem, such as a bug or game data that
+looks wrong, open a regular issue instead:
+[github.com/carterptull/blitzcast/issues/new/choose](https://github.com/carterptull/blitzcast/issues/new/choose)
@@
 ## What to expect
 
-- An acknowledgement once the report has been read, typically within a
-  few days.
+- An acknowledgement within 7 days, usually sooner.
```

Why: "private channel" comes from ampline-claude. The concrete "7 days" comes from personal-portfolio-website and makes "a few days" checkable. The pointer to issues gives non-security reports somewhere to go besides "don't open an issue".

- [ ] **Step 2:** Run the dash grep on `SECURITY.md` (same pattern as Task 4 Step 5). Expected: no output.
- [ ] **Step 3: Commit**

```bash
git add SECURITY.md
git commit -m "docs(security): say reports open a private channel, give a 7 day acknowledgement, point bugs to issues"
```

### Task 7: Release docs, version 1.2.0, local and visual verification

**Files:**
- Modify: `frontend/package.json` (`"version": "1.2.0"`), plus `frontend/package-lock.json` (both `version` fields at the top, via `npm version 1.2.0 --no-git-tag-version` from `frontend/`)
- Modify: `CHANGELOG.md` (new `## [1.2.0] — 2026-MM-DD` section under `[Unreleased]`, using the existing heading style)
- Modify: `docs/superpowers/plans/2026-09-30-p4-model-1.1.md` (lines 1, 325, 362, 375, 376, 385, 390, 392) and `docs/superpowers/specs/2026-09-30-booth-data-model-1.1-design.md:15`, so 1.2.0 is no longer reserved for the parked model
- Modify: `DECISIONS.md` (one short entry at the end)
- Modify: `README.md:~183` (add `├── .github/ISSUE_TEMPLATE/  bug and wrong-data issue forms` under the workflows line)
- Modify: all 10 `diagrams/*.md` footers: `_Last updated: <merge date> · reflects v1.2.0_`

- [ ] **Step 1: CHANGELOG entry**

```markdown
## [1.2.0] — 2026-10-DD

### Added
- A "Report an Issue" link in the site footer, opening GitHub's issue chooser in a new tab.
- GitHub issue forms for bugs and for wrong game data. Blank issues are off, and the
  chooser sends security reports to private vulnerability reporting.

### Fixed
- Private vulnerability reporting is now enabled on the repository, so the reporting
  link in SECURITY.md and the `Contact:` in `/.well-known/security.txt` work.

### Changed
- SECURITY.md: a 7 day acknowledgement target and a pointer to issues for non-security reports.
```
Also add this line to the "Changed" block: `- The parked model retrain (P4) no longer has a reserved version; it gets the next version when it ships.`
(The existing headings use an em dash: keep that for consistency, since CHANGELOG headings follow the established format. The no-dash rule applies to the entry text.)

- [ ] **Step 1b: Drop the P4 version label.** In the P4 plan and the booth spec, replace each `v1.2.0` / `1.2.0` that names P4's release:
  - P4 plan line 1: `# P4 Model 1.1 Implementation Plan (models \`1.1.0\` / \`cfb-1.1.0\`; app version picked when it ships)`
  - Add one line under that title: `> **Status (2026-10-14):** parked until after the 2026 season (Feb 2027). v1.2.0 shipped as an unrelated release; use the next version up when this lands.`
  - Lines 325, 362, 375, 376, 385, 390, 392: change `v1.2.0` / `1.2.0` to `vX.Y.0` and leave the rest of each sentence alone.
  - Spec line 15 Release cell: `parked (Feb 2027); models \`1.1.0\` / \`cfb-1.1.0\`, app version picked when it ships`
  - Verify: `git grep -n "1\.2\.0" docs/` shows only this plan and the new P4 status line.

- [ ] **Step 2: DECISIONS entry**

```markdown
## Visitor issue reports go to GitHub, security reports stay private

**Decision:** the footer links to GitHub's issue chooser, with two issue forms and blank issues
turned off, and the chooser's contact link points security reports at private vulnerability
reporting. **Why:** the site has no accounts or backend for a feedback form, and a form would
need spam handling and storage for personal data. GitHub already does both. Turning off blank
issues means a security report cannot skip the private route by accident. **Trade-off:** filing
needs a GitHub account, and the link shows the repo owner's GitHub handle (already public in
SECURITY.md and security.txt). Revisit if the repo moves to a Paymon organization.
```

- [ ] **Step 3: Diagram footers.** Update the stamp in all 10 files. No diagram body changes: `deployment-security.md` already shows private reporting, and an outbound link is not a new external API, header or hosting change (per the `diagrams/README.md` re-check table).

- [ ] **Step 4: Repo-wide dash check on changed visitor-facing text**

Run: `git diff main --name-only | xargs grep -nP "&mdash;|&ndash;"` (entities only; the CHANGELOG/DECISIONS headings use literal em dashes by convention) and `grep -nP "\x{2013}|\x{2014}" frontend/src/components/Footer.tsx .github/ISSUE_TEMPLATE/*.yml SECURITY.md`.
Expected: no output.

- [ ] **Step 5: Gates.** From `frontend/`: `npm run lint && npm test && npm run build`. From `backend/`: `.venv\Scripts\python -m ruff check . && .venv\Scripts\python -m pytest` (backend is untouched, but `backend` is a required check, so confirm it locally).

- [ ] **Step 6: Visual check (Chrome or Playwright, `npm run dev` with `NEXT_PUBLIC_USE_MOCK=1`)**
  - At 1280px: footer shows `© 2026 Paymon Software · How It Works · Report an Issue` on the left.
  - At 375px: the left group wraps cleanly with no horizontal scroll.
  - Clicking the link opens a new tab on `github.com/carterptull/blitzcast/issues/new/choose`.
  - After the PR's branch is pushed, the chooser on GitHub only shows templates from the default branch, so check the chooser (Bug report, Wrong game data, Report a security vulnerability, no "blank issue" option) **after merge**, logged out.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json CHANGELOG.md DECISIONS.md README.md docs/superpowers/plans/2026-09-30-p4-model-1.1.md docs/superpowers/specs/2026-09-30-booth-data-model-1.1-design.md diagrams/overview.md diagrams/c4-context.md diagrams/c4-container.md diagrams/er-diagram.md diagrams/prediction-request-sequence.md diagrams/daily-refresh-sequence.md diagrams/llm-narration-boundary.md diagrams/ml-pipeline.md diagrams/game-lifecycle-state.md diagrams/deployment-security.md docs/superpowers/plans/2026-10-14-private-reporting-and-issue-link.md
git commit -m "chore(release): 1.2.0 changelog, decision, README tree, diagram stamps, unreserve P4 version"
```

### Task 8: Review, PR, merge, release (controller only; merge and release need the user's go-ahead)

- [ ] **Step 1:** Run a whole-branch review with a fresh reviewer subagent (superpowers:requesting-code-review). Check against this plan, the Global Constraints, the dash rule, and authorship (`git log main..HEAD --format='%an <%ae>%n%b'` shows only the maintainer's identity and no trailers). Fix anything real in a new commit.
- [ ] **Step 2:** `git push -u origin ct/feat/report-issue-link`
- [ ] **Step 3:** Write the PR body to the scratchpad (summary, test plan, the Part A before/after values; **no attribution line**), then `gh pr create --base main --title "feat: Report an Issue link, issue forms, and release 1.2.0" --body-file <scratchpad>/pr-body.md`
- [ ] **Step 4:** `gh pr checks <n> --watch`. Expected: `backend` and `frontend` pass.
- [ ] **Step 5: STOP.** Report the green checks and PR link to the user and wait for the merge go-ahead.
- [ ] **Step 6 (after go-ahead, outside 09:00 to 10:00 UTC):** `gh pr merge <n> --merge --delete-branch`, then `git switch main && git pull --ff-only`.
- [ ] **Step 7:** `gh release create v1.2.0 --target main --title "v1.2.0" --notes-file <scratchpad>/release-notes.md`. The notes are the CHANGELOG 1.2.0 section, with no attribution.
- [ ] **Step 8: Post-deploy checks.** The live footer shows `v1.2.0` and the link. The logged-out issue chooser on GitHub shows the two forms and the security contact link, with no blank option. `git log -3 --format='%an <%ae>'` shows only the maintainer's identity. `gh api repos/carterptull/blitzcast/contributors --jq '.[].login'` lists only `carterptull`.

---

## Not in this release (follow-ups)

- **Email contact (`paymonsoftware@gmail.com`).** The user may want an email option later, for people without a GitHub account. Options: a `mailto:` in the footer, a small `/contact` page, or a second `Contact: mailto:` line in security.txt for researchers. Trade-off: an address published on the site gets scraped for spam (an obfuscated or form-based page reduces that), and a Gmail inbox has no triage or tracking. Decide separately; no change in this release.
- **Watch > Custom > Security alerts** on the repo (user, UI only), so private reports reach the inbox. Listed in Task 3 Step 4.
