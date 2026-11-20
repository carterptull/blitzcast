/** SlateSelector rendering tests: chip labels, active state, query
 *  preservation, and prefetch behavior (see DECISIONS.md: disabling
 *  prefetch here avoids tripping Vercel's automatic DDoS mitigation on a
 *  burst of near-simultaneous prefetch requests for every visible chip). */

import React from "react";
import { render, screen } from "@testing-library/react";
import SlateSelector from "../SlateSelector";
import type { Slate } from "@/lib/types";

// jsdom doesn't implement scrollIntoView; SlateSelector calls it on mount.
const scrollIntoView = jest.fn();
Element.prototype.scrollIntoView = scrollIntoView;

// Mock Next.js Link, forwarding `prefetch` as a data attribute so tests
// can assert on it (the real Link strips it from the DOM).
jest.mock("next/link", () => {
  const MockLink = ({
    children,
    href,
    prefetch,
    "aria-current": ariaCurrent,
  }: {
    children: React.ReactNode;
    href: string;
    prefetch?: boolean;
    "aria-current"?: "true" | "false";
  }) => (
    <a href={href} aria-current={ariaCurrent} data-prefetch={String(prefetch)}>
      {children}
    </a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

const slate = (over: Partial<Slate>): Slate => ({
  key: "w1",
  phase: "regular",
  week: 1,
  round: null,
  label: null,
  group_label: "Wk",
  short_label: "1",
  game_count: 1,
  first_kickoff: null,
  next_kickoff: null,
  has_unscheduled: false,
  last_kickoff: null,
  ...over,
});

const week = (n: number) => slate({ key: `w${n}`, week: n, short_label: String(n) });
const champ = slate({
  key: "w14",
  week: 14,
  round: "conf_championship",
  label: "Conference Championships",
  group_label: "Champ",
  short_label: "14",
});
const wildCard = slate({
  key: "wild-card",
  phase: "postseason",
  week: 19,
  round: "wild_card",
  label: "Wild Card",
  group_label: "Round",
  short_label: "WC",
});
const quarterfinals = slate({
  key: "cfp-quarterfinals",
  phase: "postseason",
  week: 17,
  round: "cfp_quarterfinal",
  label: "CFP Quarterfinals",
  group_label: "CFP",
  short_label: "QF",
});

const chip = (short: string) => screen.getByText(short).closest("a");

describe("SlateSelector", () => {
  test("PS-F5 / PS-V2: a chip is group_label over short_label", () => {
    render(<SlateSelector slates={[week(13), champ]} selectedKey="w14" basePath="/cfb" />);
    expect(chip("14")).toHaveTextContent("Champ14");
    expect(chip("13")).toHaveTextContent("Wk13");
  });

  test("PS-F5: postseason chips read Round / WC and CFP / QF", () => {
    render(<SlateSelector slates={[wildCard]} selectedKey="wild-card" basePath="/nfl" />);
    expect(chip("WC")).toHaveTextContent("RoundWC");
    render(
      <SlateSelector slates={[quarterfinals]} selectedKey="cfp-quarterfinals" basePath="/cfb" />
    );
    expect(chip("QF")).toHaveTextContent("CFPQF");
  });

  test("PS-F5: links use ?week=N or ?round=slug and keep extra query params", () => {
    render(
      <SlateSelector
        slates={[champ, wildCard]}
        selectedKey="w14"
        basePath="/cfb"
        query="&conf=SEC"
      />
    );
    expect(chip("14")).toHaveAttribute("href", "/cfb?week=14&conf=SEC");
    expect(chip("WC")).toHaveAttribute("href", "/cfb?round=wild-card&conf=SEC");
  });

  test("PS-F5: the active chip is marked and scrolled into view", () => {
    render(<SlateSelector slates={[week(1), week(2), week(3)]} selectedKey="w2" basePath="/nfl" />);
    expect(chip("2")).toHaveAttribute("aria-current", "page");
    expect(chip("1")).not.toHaveAttribute("aria-current");
    expect(scrollIntoView).toHaveBeenCalled();
  });

  test("PS-F5: chips do not prefetch (avoids a same-instant burst of requests)", () => {
    render(
      <SlateSelector
        slates={[1, 2, 3, 4, 5].map(week)}
        selectedKey="w1"
        basePath="/nfl"
      />
    );
    for (const n of [1, 2, 3, 4, 5]) {
      expect(chip(String(n))).toHaveAttribute("data-prefetch", "false");
    }
  });
});
