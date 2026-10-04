"""Weekly refresh orchestrator: schedule -> stats -> odds -> weather ->
injuries -> prediction batch. Each step is independently re-runnable and a
failure in one step does not block the rest; a failed (or skipped-for-schedule)
prediction batch fails the run at the end.

Usage: python -m data_pipeline.refresh_week [--season 2026] [--skip-predict]
"""

import argparse
import subprocess
import sys


def run_step(name: str, args: list[str]) -> bool:
    print(f"--- {name} ---")
    result = subprocess.run([sys.executable, "-m", *args], check=False)
    if result.returncode != 0:
        print(f"{name} failed with exit code {result.returncode}")
        return False
    return True


def finish_run(prediction_ok: bool | None) -> None:
    """Exit 1 after every step ran if the prediction batch failed or was skipped
    for a failed schedule sync; None means it was not requested."""
    if prediction_ok is False:
        print("refresh run failed: the prediction batch did not complete")
        sys.exit(1)
    print("refresh run complete")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--skip-predict", action="store_true")
    args = parser.parse_args()
    season = str(args.season)

    ok = run_step("schedule sync", ["data_pipeline.refresh_schedule", "--season", season])
    # Keeps the rolling EPA/turnover form features fed once games are final.
    run_step("stats refresh", ["data_pipeline.refresh_stats", "--season", season])
    run_step("odds refresh", ["data_pipeline.refresh_odds"])
    run_step("weather refresh", ["data_pipeline.refresh_weather", "--backfill-days", "3"])
    run_step("injury refresh", ["data_pipeline.refresh_injuries", "--season", season])

    predicted = None
    if not args.skip_predict:
        if ok:
            predicted = run_step("prediction batch", ["app.jobs.predict_week", "--season", season])
        else:
            print("skipping prediction batch because schedule sync failed")
            predicted = False
    finish_run(predicted)


if __name__ == "__main__":
    main()
