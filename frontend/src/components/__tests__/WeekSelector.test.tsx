/** WeekSelector rendering tests: week links, active state, query
 *  preservation, and prefetch behavior (see DECISIONS.md -- disabling
 *  prefetch here avoids tripping Vercel's automatic DDoS mitigation on a
 *  burst of near-simultaneous prefetch requests for every visible week). */

import React from "react";
import { render, screen } from "@testing-library/react";
import WeekSelector from "../WeekSelector";

// jsdom doesn't implement scrollIntoView; WeekSelector calls it on mount.
Element.prototype.scrollIntoView = jest.fn();

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

describe("WeekSelector", () => {
  test("renders every week with the selected one marked", () => {
    render(<WeekSelector weeks={[1, 2, 3]} selected={2} basePath="/nfl" />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("2").closest("a")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("1").closest("a")).not.toHaveAttribute("aria-current");
  });

  test("links point at the right week and preserve extra query params", () => {
    render(<WeekSelector weeks={[1, 2]} selected={1} basePath="/cfb" query="&conf=SEC" />);
    expect(screen.getByText("2").closest("a")).toHaveAttribute("href", "/cfb?week=2&conf=SEC");
  });

  test("week links do not prefetch (avoids a same-instant burst of requests)", () => {
    render(<WeekSelector weeks={[1, 2, 3, 4, 5]} selected={1} basePath="/nfl" />);
    for (const week of [1, 2, 3, 4, 5]) {
      expect(screen.getByText(String(week)).closest("a")).toHaveAttribute(
        "data-prefetch",
        "false"
      );
    }
  });
});
