/** RecordBanner rendering tests: the model's number must never appear without
 *  the market's number beside it, and an insufficient sample must never show
 *  a percentage. */

import React from "react";
import { render, screen } from "@testing-library/react";
import RecordBanner from "../RecordBanner";

test("shows the record next to the market baseline", () => {
  render(
    <RecordBanner
      record={{ sport: "NFL", season: 2026, correct: 11, total: 16, market_correct: 12, sufficient: true }}
    />
  );
  expect(screen.getByText(/11/)).toBeInTheDocument();
  expect(screen.getByText(/16/)).toBeInTheDocument();
  expect(screen.getByText(/market/i)).toBeInTheDocument();
});

test("shows an insufficient-sample state instead of a percentage", () => {
  render(
    <RecordBanner
      record={{ sport: "NFL", season: 2026, correct: 2, total: 3, market_correct: 2, sufficient: false }}
    />
  );
  expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  expect(screen.getByText(/not enough games/i)).toBeInTheDocument();
});
