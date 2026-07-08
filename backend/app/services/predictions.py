"""Read-side query helpers for the API routers."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Game, Odds, Prediction, Team, Weather
from app.schemas import (
    FactorOut,
    GameSummary,
    GameTeam,
    OddsOut,
    PredictionOut,
    ScheduleOut,
    TeamDetail,
    TeamOut,
    VenueOut,
    WeatherOut,
    WeekOut,
)
from data_pipeline.team_names import logo_url, nickname


def list_teams(db: Session) -> list[TeamOut]:
    teams = db.scalars(select(Team).order_by(Team.abbr)).all()
    return [
        TeamOut(
            id=t.team_id,
            abbr=t.abbr,
            name=t.name,
            conference=t.conference,
            division=t.division,
            logo_url=logo_url(t.abbr),
        )
        for t in teams
    ]


def _prediction_probs(db: Session) -> dict[str, float]:
    rows = db.execute(select(Prediction.game_id, Prediction.home_win_prob))
    return dict(rows.all())


def _game_summary(game: Game, home_win_prob: float | None) -> GameSummary:
    return GameSummary(
        game_id=game.game_id,
        kickoff=game.kickoff_time,
        home=GameTeam(abbr=game.home_team.abbr, name=nickname(game.home_team.name)),
        away=GameTeam(abbr=game.away_team.abbr, name=nickname(game.away_team.name)),
        is_primetime=game.is_primetime,
        status=game.status,
        has_prediction=home_win_prob is not None,
        home_win_prob=home_win_prob,
    )


def _season_games(db: Session, season: int, week: int | None = None) -> list[Game]:
    query = (
        select(Game)
        .options(joinedload(Game.home_team), joinedload(Game.away_team))
        .where(Game.season == season)
        .order_by(Game.kickoff_time)
    )
    if week is not None:
        query = query.where(Game.week == week)
    return list(db.scalars(query))


def get_schedule(db: Session, season: int) -> ScheduleOut:
    games = _season_games(db, season)
    probs = _prediction_probs(db)
    weeks: dict[int, list[GameSummary]] = {}
    for game in games:
        weeks.setdefault(game.week, []).append(
            _game_summary(game, probs.get(game.game_id))
        )
    return ScheduleOut(
        season=season,
        weeks=[WeekOut(week=w, games=weeks[w]) for w in sorted(weeks)],
    )


def get_games(db: Session, season: int, week: int) -> list[GameSummary]:
    games = _season_games(db, season, week)
    probs = _prediction_probs(db)
    return [_game_summary(g, probs.get(g.game_id)) for g in games]


def _record_entering(db: Session, team_id: int, game: Game) -> str:
    """Team's W-L(-T) record in this season before this game's kickoff."""
    prior = db.scalars(
        select(Game).where(
            Game.season == game.season,
            Game.kickoff_time < game.kickoff_time,
            Game.home_score.is_not(None),
            (Game.home_team_id == team_id) | (Game.away_team_id == team_id),
        )
    ).all()
    wins = losses = ties = 0
    for g in prior:
        own = g.home_score if g.home_team_id == team_id else g.away_score
        opp = g.away_score if g.home_team_id == team_id else g.home_score
        if own > opp:
            wins += 1
        elif own < opp:
            losses += 1
        else:
            ties += 1
    record = f"{wins}-{losses}"
    return f"{record}-{ties}" if ties else record


def get_prediction_detail(db: Session, game_id: str) -> PredictionOut | None:
    game = db.get(
        Game,
        game_id,
        options=[
            joinedload(Game.home_team),
            joinedload(Game.away_team),
            joinedload(Game.stadium),
        ],
    )
    if game is None:
        return None

    prediction = db.scalar(
        select(Prediction)
        .where(Prediction.game_id == game_id)
        .order_by(Prediction.predicted_at.desc())
    )
    weather = db.get(Weather, game_id)
    odds = db.scalar(
        select(Odds).where(Odds.game_id == game_id).order_by(Odds.captured_at.desc())
    )

    if odds is not None:
        odds_out = OddsOut(
            spread_home=odds.spread_home,
            moneyline_home=odds.moneyline_home,
            moneyline_away=odds.moneyline_away,
            total=odds.total,
        )
    elif game.spread_line is not None or game.home_moneyline is not None:
        odds_out = OddsOut(
            spread_home=game.spread_line,
            moneyline_home=game.home_moneyline,
            moneyline_away=game.away_moneyline,
            total=game.total_line,
        )
    else:
        odds_out = None

    home_prob = prediction.home_win_prob if prediction else None
    factors = (
        [
            FactorOut(**{k: f[k] for k in ("label", "value", "direction")})
            for f in prediction.shap_top_features
        ]
        if prediction and prediction.shap_top_features
        else []
    )

    return PredictionOut(
        game_id=game.game_id,
        season=game.season,
        week=game.week,
        kickoff=game.kickoff_time,
        venue=VenueOut(
            name=game.stadium.name if game.stadium else None,
            city=game.stadium.city if game.stadium else None,
            is_dome=game.stadium.is_dome if game.stadium else None,
        ),
        is_primetime=game.is_primetime,
        is_divisional=game.is_divisional,
        home=TeamDetail(
            abbr=game.home_team.abbr,
            name=nickname(game.home_team.name),
            record=_record_entering(db, game.home_team_id, game),
            logo_url=logo_url(game.home_team.abbr),
            win_prob=home_prob,
        ),
        away=TeamDetail(
            abbr=game.away_team.abbr,
            name=nickname(game.away_team.name),
            record=_record_entering(db, game.away_team_id, game),
            logo_url=logo_url(game.away_team.abbr),
            win_prob=None if home_prob is None else round(1.0 - home_prob, 4),
        ),
        odds=odds_out,
        weather=(
            WeatherOut(
                temp_f=weather.temp_f,
                wind_mph=weather.wind_mph,
                precipitation=weather.precipitation,
                conditions=weather.conditions,
            )
            if weather
            else None
        ),
        factors=factors,
        narrative=prediction.llm_narrative if prediction else None,
        model_version=prediction.model_version if prediction else None,
        predicted_at=prediction.predicted_at if prediction else None,
        prediction_status="available" if prediction else "pending",
    )
