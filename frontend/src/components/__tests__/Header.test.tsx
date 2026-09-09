/** Header rendering tests: sport tabs, active state, prefetch behavior. */

import React from "react";
import { render, screen } from "@testing-library/react";
import Header from "../Header";

jest.mock("next/navigation", () => ({
  usePathname: () => "/nfl",
}));

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

describe("Header", () => {
  test("renders NFL and CFB tabs with the current sport marked active", () => {
    render(<Header />);
    expect(screen.getByText("NFL").closest("a")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("CFB").closest("a")).not.toHaveAttribute("aria-current");
  });

  test("sport tabs do not prefetch (rendered on every page)", () => {
    render(<Header />);
    expect(screen.getByText("NFL").closest("a")).toHaveAttribute("data-prefetch", "false");
    expect(screen.getByText("CFB").closest("a")).toHaveAttribute("data-prefetch", "false");
  });
});
