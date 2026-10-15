import React from "react";
import { render } from "@testing-library/react";
import BrandMark from "../BrandMark";

describe("BrandMark", () => {
  test("tile variant draws the turf tile and the ball", () => {
    const { container } = render(<BrandMark size={24} />);
    const svg = container.querySelector("svg[data-brand-mark='tile']");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("width", "24");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelectorAll("rect")).toHaveLength(2);
    expect(container.querySelector("ellipse")).toHaveAttribute("fill", "#e9b84d");
  });

  test("ball variant draws no tile", () => {
    const { container } = render(<BrandMark size={40} tile={false} />);
    expect(container.querySelector("svg[data-brand-mark='ball']")).not.toBeNull();
    expect(container.querySelectorAll("rect")).toHaveLength(0);
    expect(container.querySelector("ellipse")).not.toBeNull();
  });

  test("passes className through", () => {
    const { container } = render(<BrandMark className="rounded-md" />);
    expect(container.querySelector("svg")).toHaveClass("rounded-md");
  });
});
