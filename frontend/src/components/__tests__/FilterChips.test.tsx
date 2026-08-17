/** FilterChips rendering tests: conf/top25 chip links preserve extra query state. */

import React from "react";
import { render, screen } from "@testing-library/react";
import FilterChips from "../FilterChips";

// jsdom doesn't implement scrollIntoView; FilterChips calls it on mount.
Element.prototype.scrollIntoView = jest.fn();

// Mock Next.js Link component to avoid routing issues in tests
jest.mock("next/link", () => {
  const MockLink = ({
    children,
    href,
    "aria-current": ariaCurrent,
  }: {
    children: React.ReactNode;
    href: string;
    "aria-current"?: "true" | "false";
  }) => (
    <a href={href} aria-current={ariaCurrent}>
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
});
