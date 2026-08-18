"""Record endpoint: the app's honesty check on itself."""

from datetime import UTC, date, datetime

from sqlalchemy import select

from app.models import SPORT_CFB, Game, Odds, Prediction, Team


def test_record_excludes_backfilled_predictions(client, db):
    """Reconstructed backtest rows must never inflate the live record."""
    body = client.get("/api/record?sport=NFL&season=2026").json()
    assert body["total"] == 0  # 2026 has no finished games in the fixture


def test_record_reports_insufficient_sample(client):
    body = client.get("/api/record?sport=NFL&season=2026").json()
    assert body["sufficient"] is False


def test_record_market_baseline_shares_the_sample(client):
    body = client.get("/api/record?season=2026").json()
    assert body["market_correct"] <= body["total"]


def test_record_counts_graded_finished_games(client, db):
    """2025 KC/BUF games are finished, have market data, and KC always wins."""
    for week in range(1, 7):
        db.add(
            Prediction(
                game_id=f"2025_{week:02d}_BUF_KC",
                model_version="1.0.0",
                home_win_prob=0.65,
                predicted_at=datetime(2025, 9, 1, tzinfo=UTC),
            )
        )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 6
    assert body["correct"] == 6
    assert body["market_correct"] == 6  # -150/130 moneyline also favors KC


def test_record_excludes_backtest_rows_even_with_scores(client, db):
    """A backtest-prefixed model_version must never enter the live count."""
    for week in range(1, 7):
        db.add(
            Prediction(
                game_id=f"2025_{week:02d}_BUF_KC",
                model_version="backtest-1.0.0",
                home_win_prob=0.65,
                predicted_at=datetime(2025, 9, 1, tzinfo=UTC),
            )
        )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 0


def test_record_newest_prediction_per_game_wins(client, db):
    game_id = "2025_01_BUF_KC"
    db.add(
        Prediction(
            game_id=game_id, model_version="0.9.0", home_win_prob=0.30,
            predicted_at=datetime(2025, 9, 1, tzinfo=UTC),
        )
    )
    db.add(
        Prediction(
            game_id=game_id, model_version="1.0.0", home_win_prob=0.65,
            predicted_at=datetime(2025, 9, 2, tzinfo=UTC),
        )
    )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 1
    assert body["correct"] == 1  # 0.65 (newer, home favorite) beats the stale 0.30


def test_record_excludes_games_without_any_market_data_from_both(client, db):
    kc = db.scalar(select(Team).where(Team.abbr == "KC"))
    buf = db.scalar(select(Team).where(Team.abbr == "BUF"))
    game_id = "2025_99_BUF_KC"
    db.add(
        Game(
            game_id=game_id, season=2025, week=99,
            game_date=date(2025, 12, 1),
            kickoff_time=datetime(2025, 12, 1, 18, 0, tzinfo=UTC),
            home_team_id=kc.team_id, away_team_id=buf.team_id,
            stadium_id=kc.stadium_id, status="final",
            home_score=24, away_score=17,
            # no spread_line, no moneylines, no Odds row -> no market data at all
        )
    )
    db.add(
        Prediction(
            game_id=game_id, model_version="1.0.0", home_win_prob=0.7,
            predicted_at=datetime(2025, 11, 1, tzinfo=UTC),
        )
    )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 0
    assert body["market_correct"] == 0


def test_record_excludes_pickem_market_lines_from_both_counts(client, db):
    """A pick'em market line (exact 0.5, no favorite) must be excluded from
    the record entirely -- not scored as a market loss -- even though the
    model's own prediction on the same game is gradeable."""
    kc = db.scalar(select(Team).where(Team.abbr == "KC"))
    buf = db.scalar(select(Team).where(Team.abbr == "BUF"))
    game_id = "2025_95_BUF_KC"
    db.add(
        Game(
            game_id=game_id, season=2025, week=95,
            game_date=date(2025, 12, 1),
            kickoff_time=datetime(2025, 12, 1, 18, 0, tzinfo=UTC),
            home_team_id=kc.team_id, away_team_id=buf.team_id,
            stadium_id=kc.stadium_id, status="final",
            home_score=24, away_score=17,
            home_moneyline=-110, away_moneyline=-110,  # de-vigs to exactly 0.5
        )
    )
    db.add(
        Prediction(
            game_id=game_id, model_version="1.0.0", home_win_prob=0.65,
            predicted_at=datetime(2025, 11, 1, tzinfo=UTC),
        )
    )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 0
    assert body["correct"] == 0
    assert body["market_correct"] == 0


def test_record_prefers_live_odds_over_game_level_lines(client, db):
    """A live Odds row must be used even when the Game columns are empty."""
    kc = db.scalar(select(Team).where(Team.abbr == "KC"))
    buf = db.scalar(select(Team).where(Team.abbr == "BUF"))
    game_id = "2025_98_BUF_KC"
    db.add(
        Game(
            game_id=game_id, season=2025, week=98,
            game_date=date(2025, 12, 1),
            kickoff_time=datetime(2025, 12, 1, 18, 0, tzinfo=UTC),
            home_team_id=kc.team_id, away_team_id=buf.team_id,
            stadium_id=kc.stadium_id, status="final",
            home_score=24, away_score=17,
        )
    )
    db.add(
        Odds(
            game_id=game_id, source="test", spread_home=None,
            moneyline_home=-150, moneyline_away=130,
            captured_at=datetime(2025, 11, 30, tzinfo=UTC),
        )
    )
    db.add(
        Prediction(
            game_id=game_id, model_version="1.0.0", home_win_prob=0.7,
            predicted_at=datetime(2025, 11, 1, tzinfo=UTC),
        )
    )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 1
    assert body["market_correct"] == 1


def test_record_excludes_odds_captured_at_or_after_kickoff(client, db):
    """An in-play/post-kickoff Odds capture is not a pre-game market view --
    it must drop the game from both counts, not silently count as market data."""
    kc = db.scalar(select(Team).where(Team.abbr == "KC"))
    buf = db.scalar(select(Team).where(Team.abbr == "BUF"))
    kickoff = datetime(2025, 12, 1, 18, 0, tzinfo=UTC)
    game_id = "2025_97_BUF_KC"
    db.add(
        Game(
            game_id=game_id, season=2025, week=97,
            game_date=kickoff.date(), kickoff_time=kickoff,
            home_team_id=kc.team_id, away_team_id=buf.team_id,
            stadium_id=kc.stadium_id, status="final",
            home_score=24, away_score=17,
            # no Game-level market columns -- the only market source is Odds
        )
    )
    db.add(
        Odds(
            game_id=game_id, source="test", spread_home=None,
            moneyline_home=-150, moneyline_away=130,
            captured_at=kickoff,  # at kickoff, not strictly before -- must be dropped
        )
    )
    db.add(
        Prediction(
            game_id=game_id, model_version="1.0.0", home_win_prob=0.7,
            predicted_at=datetime(2025, 11, 1, tzinfo=UTC),
        )
    )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 0
    assert body["market_correct"] == 0


def test_record_excludes_post_kickoff_odds_for_tbd_kickoff_game(client, db):
    """TBD-kickoff games fall back to game_date for the cutoff; a daily batch
    can still write a same-day capture after the real (later-resolved)
    kickoff, so that capture must be excluded the same way."""
    kc = db.scalar(select(Team).where(Team.abbr == "KC"))
    buf = db.scalar(select(Team).where(Team.abbr == "BUF"))
    game_date = date(2025, 12, 1)
    game_id = "2025_96_BUF_KC"
    db.add(
        Game(
            game_id=game_id, season=2025, week=96,
            game_date=game_date, kickoff_time=None,
            home_team_id=kc.team_id, away_team_id=buf.team_id,
            stadium_id=kc.stadium_id, status="final",
            home_score=24, away_score=17,
        )
    )
    db.add(
        Odds(
            game_id=game_id, source="test", spread_home=None,
            moneyline_home=-150, moneyline_away=130,
            # game_date at midnight UTC is the TBD-kickoff cutoff; this is after it
            captured_at=datetime(2025, 12, 1, 12, 0, tzinfo=UTC),
        )
    )
    db.add(
        Prediction(
            game_id=game_id, model_version="1.0.0", home_win_prob=0.7,
            predicted_at=datetime(2025, 11, 1, tzinfo=UTC),
        )
    )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 0
    assert body["market_correct"] == 0


def test_record_sufficient_at_ten_graded_games(client, db):
    for week in range(1, 7):
        for away, home in (("BUF", "KC"), ("DAL", "PHI")):
            db.add(
                Prediction(
                    game_id=f"2025_{week:02d}_{away}_{home}",
                    model_version="1.0.0", home_win_prob=0.65,
                    predicted_at=datetime(2025, 9, 1, tzinfo=UTC),
                )
            )
    db.commit()
    body = client.get("/api/record?sport=NFL&season=2025").json()
    assert body["total"] == 12
    assert body["sufficient"] is True
    assert body["market_correct"] <= body["total"]


def test_record_omitting_sport_combines_both(client, db):
    db.add(
        Prediction(
            game_id="2025_01_BUF_KC", model_version="1.0.0", home_win_prob=0.65,
            predicted_at=datetime(2025, 9, 1, tzinfo=UTC),
        )
    )
    ala = db.scalar(select(Team).where(Team.abbr == "ALA"))
    uga = db.scalar(select(Team).where(Team.abbr == "UGA"))
    db.add(
        Game(
            game_id="cfb_401800099", sport=SPORT_CFB, season=2025, week=1,
            game_date=date(2025, 9, 6),
            kickoff_time=datetime(2025, 9, 6, 19, 0, tzinfo=UTC),
            home_team_id=ala.team_id, away_team_id=uga.team_id,
            stadium_id=ala.stadium_id, status="final",
            home_score=30, away_score=20,
            spread_line=-3.0, home_moneyline=-160, away_moneyline=140,
        )
    )
    db.add(
        Prediction(
            game_id="cfb_401800099", model_version="cfb-1.0.0", home_win_prob=0.7,
            predicted_at=datetime(2025, 9, 4, tzinfo=UTC),
        )
    )
    db.commit()
    nfl_total = client.get("/api/record?sport=NFL&season=2025").json()["total"]
    cfb_total = client.get("/api/record?sport=CFB&season=2025").json()["total"]
    combined = client.get("/api/record?season=2025").json()["total"]
    assert nfl_total == 1
    assert cfb_total == 1
    assert combined == nfl_total + cfb_total
