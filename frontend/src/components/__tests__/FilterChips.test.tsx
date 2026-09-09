/** FilterChips rendering tests: conf/top25 chip links preserve extra query state. */

import React from "react";
import { render, screen } from "@testing-library/react";
import FilterChips from "../FilterChips";

// jsdom doesn't implement scrollIntoView; FilterChips calls it on mount.
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

describe("FilterChips", () => {
  test("conference and top25 chip links preserve an active status filter", () => {
    render(
      <FilterChips
        conferences={["SEC", "Big Ten"]}
        activeConf={null}
        top25={false}
        week={3}
        query="&status=final"
      />
    );
    expect(screen.getByText("SEC").closest("a")?.getAttribute("href")).toContain(
      "status=final"
    );
    expect(screen.getByText("Top 25").closest("a")?.getAttribute("href")).toContain(
      "status=final"
    );
    expect(screen.getByText("All conferences").closest("a")?.getAttribute("href")).toContain(
      "status=final"
    );
  });

  test("query defaults to empty, leaving hrefs unchanged when omitted", () => {
    render(<FilterChips conferences={["SEC"]} activeConf={null} top25={false} week={3} />);
    expect(screen.getByText("SEC").closest("a")?.getAttribute("href")).not.toContain("status=");
  });

  test("no chip prefetches (a full CFB conference list renders many at once)", () => {
    render(
      <FilterChips conferences={["SEC", "Big Ten", "ACC"]} activeConf={null} top25={false} week={3} />
    );
    for (const label of ["Top 25", "All conferences", "SEC", "Big Ten", "ACC"]) {
      expect(screen.getByText(label).closest("a")).toHaveAttribute("data-prefetch", "false");
    }
  });
});
