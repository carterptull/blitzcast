"""Weekly CFB refresh orchestrator: schedule -> odds -> polls -> prediction
batch. Sibling of refresh_week.py with the same soft-fail contract. No weather
step: CFB has no stadium coordinates seeded, and a full FBS slate would burn
the Visual Crossing free tier.

Usage: python -m data_pipeline.refresh_week_cfb [--season 2026] [--skip-predict]
"""

import argparse

from data_pipeline.refresh_week import run_step


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--skip-predict", action="store_true")
    args = parser.parse_args()
    season = str(args.season)

    ok = run_step(
        "cfb schedule sync", ["data_pipeline.refresh_schedule_cfb", "--season", season]
    )
    run_step("cfb odds refresh", ["data_pipeline.refresh_odds", "--sport", "cfb"])
    run_step("cfb polls refresh", ["data_pipeline.refresh_polls_cfb", "--season", season])

    if not args.skip_predict:
        if ok:
            run_step(
                "cfb prediction batch",
                ["app.jobs.predict_week", "--season", season, "--sport", "cfb"],
            )
        else:
            print("skipping prediction batch because schedule sync failed")


if __name__ == "__main__":
    main()
