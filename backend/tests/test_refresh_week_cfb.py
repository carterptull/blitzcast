"""CFB weekly orchestrator: weather refresh must be wired in (CFB games get
real stadium coordinates from CFBD, unlike NFL's Team-derived lookup, so
refresh_weather works for CFB even though it was never called here)."""
from unittest.mock import patch

import pytest

from data_pipeline import refresh_week, refresh_week_cfb


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
    assert weather_call.args[1] == [
        "data_pipeline.refresh_weather", "--sport", "cfb", "--backfill-days", "3",
    ]

    # Weather runs after odds, before polls -- matches NFL's step ordering.
    assert steps.index("cfb odds refresh") < steps.index("cfb weather refresh")
    assert steps.index("cfb weather refresh") < steps.index("cfb polls refresh")


def test_orchestrator_refreshes_stats_after_schedule_and_before_odds():
    import sys

    with patch.object(refresh_week_cfb, "run_step", return_value=True) as mock_run:
        with patch.object(sys, "argv", ["refresh_week_cfb", "--season", "2026", "--skip-predict"]):
            refresh_week_cfb.main()
    steps = [call.args[0] for call in mock_run.call_args_list]
    call = next(c for c in mock_run.call_args_list if c.args[0] == "cfb stats refresh")
    assert call.args[1] == ["data_pipeline.refresh_stats_cfb", "--season", "2026"]
    assert steps.index("cfb schedule sync") < steps.index("cfb stats refresh")
    assert steps.index("cfb stats refresh") < steps.index("cfb odds refresh")


def _run_orchestrator(module, argv, failing=()):
    import sys

    calls = []

    def fake(name, args):
        calls.append(name)
        return name not in failing

    with patch.object(module, "run_step", side_effect=fake):
        with patch.object(sys, "argv", argv):
            try:
                module.main()
            except SystemExit as exc:
                return calls, exc.code
    return calls, None


CFB = (refresh_week_cfb, ["refresh_week_cfb", "--season", "2026"], "cfb prediction batch")
NFL = (refresh_week, ["refresh_week", "--season", "2026"], "prediction batch")


def _schedule(module):
    return "cfb schedule sync" if module is refresh_week_cfb else "schedule sync"


@pytest.mark.parametrize("module,argv,predict", [CFB, NFL])
def test_a_failed_prediction_step_fails_the_run_after_every_step_ran(module, argv, predict):
    calls, code = _run_orchestrator(module, argv, failing={predict})
    assert code == 1
    assert calls[-1] == predict
    assert len(calls) == 6
    assert "odds refresh" in " ".join(calls) and "weather refresh" in " ".join(calls)


@pytest.mark.parametrize("module,argv,predict", [CFB, NFL])
def test_a_failed_schedule_sync_skips_prediction_and_fails_the_run(
    module, argv, predict, capsys
):
    calls, code = _run_orchestrator(module, argv, failing={_schedule(module)})
    assert code == 1
    assert predict not in calls
    assert len(calls) == 5
    assert "skipping prediction batch because schedule sync failed" in capsys.readouterr().out


@pytest.mark.parametrize("module,argv,predict", [CFB, NFL])
def test_a_failed_non_prediction_step_keeps_the_soft_fail_contract(module, argv, predict):
    first = "cfb stats refresh" if module is refresh_week_cfb else "stats refresh"
    calls, code = _run_orchestrator(module, argv, failing={first})
    assert code is None
    assert calls[-1] == predict


@pytest.mark.parametrize("module,argv,predict", [CFB, NFL])
def test_skip_predict_exits_zero_even_when_schedule_sync_failed(module, argv, predict):
    calls, code = _run_orchestrator(
        module, [*argv, "--skip-predict"], failing={_schedule(module)}
    )
    assert code is None
    assert predict not in calls
    assert len(calls) == 5


@pytest.mark.parametrize("module,argv,predict", [CFB, NFL])
def test_a_clean_run_exits_zero(module, argv, predict):
    calls, code = _run_orchestrator(module, argv)
    assert code is None
    assert calls[-1] == predict
