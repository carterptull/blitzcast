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

  it("keeps the two footer links together so they wrap as a unit", () => {
    render(<Footer />);
    const group = screen.getByRole("link", { name: "How It Works" }).parentElement;
    expect(group).toBe(screen.getByRole("link", { name: "Report an Issue" }).parentElement);
    expect(group).not.toHaveTextContent("Paymon Software");
  });
});
