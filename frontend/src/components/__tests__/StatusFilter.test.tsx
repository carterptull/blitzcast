/** StatusFilter rendering tests: chip labels, active state, link preservation. */

import React from "react";
import { render, screen } from "@testing-library/react";
import StatusFilter from "../StatusFilter";

// jsdom doesn't implement scrollIntoView; StatusFilter calls it on mount.
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

describe("StatusFilter", () => {
  test("renders three status chips with the active one marked", () => {
    render(<StatusFilter sport="nfl" active="final" week={1} query="" />);
    expect(screen.getByText(/all/i)).toBeInTheDocument();
    expect(screen.getByText(/completed/i)).toBeInTheDocument();
    expect(screen.getByText(/upcoming/i)).toBeInTheDocument();
    expect(screen.getByText(/completed/i).closest("a")).toHaveAttribute(
      "aria-current",
      "true"
    );
  });

  test("links preserve the current week", () => {
    render(<StatusFilter sport="nfl" active="all" week={5} query="" />);
    expect(screen.getByText(/completed/i).closest("a")?.getAttribute("href")).toContain(
      "week=5"
    );
  });

  test("chips do not prefetch (all render at once)", () => {
    render(<StatusFilter sport="nfl" active="all" week={1} query="" />);
    for (const label of [/all/i, /completed/i, /upcoming/i]) {
      expect(screen.getByText(label).closest("a")).toHaveAttribute("data-prefetch", "false");
    }
  });
});
