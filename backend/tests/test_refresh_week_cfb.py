"""CFB weekly orchestrator: weather refresh must be wired in (CFB games get
real stadium coordinates from CFBD, unlike NFL's Team-derived lookup, so
refresh_weather works for CFB even though it was never called here)."""
from unittest.mock import patch

from data_pipeline import refresh_week_cfb


def test_orchestrator_calls_weather_refresh_for_cfb():
    import sys

    with patch.object(refresh_week_cfb, "run_step", return_value=True) as mock_run:
        with patch.object(sys, "argv", ["refresh_week_cfb", "--season", "2026", "--skip-predict"]):
            refresh_week_cfb.main()

    steps = [call.args[0] for call in mock_run.call_args_list]
    assert "cfb weather refresh" in steps

    weather_call = next(
        call for call in mock_run.call_args_list if call.args[0] == "cfb weather refresh"
    )
    assert weather_call.args[1] == ["data_pipeline.refresh_weather", "--sport", "cfb"]

    # Weather runs after odds, before polls -- matches NFL's step ordering.
    assert steps.index("cfb odds refresh") < steps.index("cfb weather refresh")
    assert steps.index("cfb weather refresh") < steps.index("cfb polls refresh")
