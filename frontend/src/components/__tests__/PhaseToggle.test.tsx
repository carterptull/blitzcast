/** PhaseToggle: the Regular season / Postseason segmented pill. */

import React from "react";
import { render, screen } from "@testing-library/react";
import PhaseToggle from "../PhaseToggle";

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

const link = (name: RegExp) => screen.getByText(name).closest("a");

describe("PhaseToggle", () => {
  test("PS-F4: renders nothing until a postseason slate exists", () => {
    const { container } = render(
      <PhaseToggle phase="regular" regularHref="/cfb?week=12" postseasonHref={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  test("PS-F4: each side links to its phase default and marks the active one", () => {
    render(
      <PhaseToggle phase="regular" regularHref="/cfb?week=14" postseasonHref="/cfb?round=bowls" />
    );
    expect(link(/regular season/i)).toHaveAttribute("href", "/cfb?week=14");
    expect(link(/postseason/i)).toHaveAttribute("href", "/cfb?round=bowls");
    expect(link(/regular season/i)).toHaveAttribute("aria-current", "true");
    expect(link(/postseason/i)).not.toHaveAttribute("aria-current");
    expect(link(/postseason/i)).toHaveAttribute("data-prefetch", "false");
  });

  test("PS-F4: the gold dot shows only while Postseason is the inactive side", () => {
    const { rerender } = render(
      <PhaseToggle phase="regular" regularHref="/nfl?week=18" postseasonHref="/nfl?round=wild-card" />
    );
    expect(screen.getByTestId("postseason-dot")).toBeInTheDocument();
    rerender(
      <PhaseToggle
        phase="postseason"
        regularHref="/nfl?week=18"
        postseasonHref="/nfl?round=wild-card"
      />
    );
    expect(screen.queryByTestId("postseason-dot")).not.toBeInTheDocument();
    expect(link(/postseason/i)).toHaveAttribute("aria-current", "true");
  });

  test("PS-F4: toggle copy has no en or em dashes", () => {
    const { container } = render(
      <PhaseToggle phase="regular" regularHref="/cfb?week=14" postseasonHref="/cfb?round=bowls" />
    );
    expect(container.innerHTML).not.toMatch(/[–—]|&[mn]dash;/);
  });
});
