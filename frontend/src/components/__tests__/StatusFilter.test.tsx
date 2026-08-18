/** StatusFilter rendering tests: chip labels, active state, link preservation. */

import React from "react";
import { render, screen } from "@testing-library/react";
import StatusFilter from "../StatusFilter";

// jsdom doesn't implement scrollIntoView; StatusFilter calls it on mount.
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
});
