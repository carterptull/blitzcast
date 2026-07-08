"""Weekly refresh orchestrator: schedule -> odds -> weather -> injuries ->
prediction batch. Each step is independently re-runnable and a failure in
one optional step does not block the rest.

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--skip-predict", action="store_true")
    args = parser.parse_args()
    season = str(args.season)

    ok = run_step("schedule sync", ["data_pipeline.refresh_schedule", "--season", season])
    run_step("odds refresh", ["data_pipeline.refresh_odds"])
    run_step("weather refresh", ["data_pipeline.refresh_weather"])
    run_step("injury refresh", ["data_pipeline.refresh_injuries", "--season", season])

    if not args.skip_predict:
        if ok:
            run_step("prediction batch", ["app.jobs.predict_week", "--season", season])
        else:
            print("skipping prediction batch because schedule sync failed")


if __name__ == "__main__":
    main()
