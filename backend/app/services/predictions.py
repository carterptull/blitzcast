"""Read-side query helpers for the API routers."""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import SPORT_CFB, SPORT_NFL, Game, Odds, PollRank, Prediction, Team, Weather
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

ESPN_CFB_LOGO = "https://a.espncdn.com/i/teamlogos/ncaa/500/{espn_id}.png"


def _team_logo(team: Team) -> str | None:
    if team.sport == SPORT_NFL:
        return logo_url(team.abbr)
    if team.logo_url:
        return team.logo_url
    if team.espn_id:
        return ESPN_CFB_LOGO.format(espn_id=team.espn_id)
    return None


def _display_name(team: Team) -> str:
    return nickname(team.name) if team.sport == SPORT_NFL else team.name


def poll_ranks_entering(db: Session, sport: str, season: int, week: int) -> dict[int, int]:
    """team_id -> rank from the poll entering (season, week); AP preferred."""
    return _poll_ranks_by_week(db, sport, season, week=week).get(week, {})


def _poll_ranks_by_week(
    db: Session, sport: str, season: int, week: int | None = None
) -> dict[int, dict[int, int]]:
    """week -> {team_id: rank} from the poll entering each week; AP preferred."""
    if sport != SPORT_CFB:
        return {}
    query = select(PollRank.week, PollRank.poll, PollRank.team_id, PollRank.rank).where(
        PollRank.sport == sport, PollRank.season == season
    )
    if week is not None:
        query = query.where(PollRank.week == week)
    by_week: dict[int, dict[str, dict[int, int]]] = {}
    for wk, poll, team_id, rank in db.execute(query):
        by_week.setdefault(wk, {}).setdefault(poll, {})[team_id] = rank
    ranks: dict[int, dict[int, int]] = {}
    for wk, polls in by_week.items():
        ap = next((p for p in sorted(polls) if p.upper().startswith("AP")), None)
        ranks[wk] = polls[ap or sorted(polls)[0]]
    return ranks


def list_teams(db: Session, sport: str = SPORT_NFL) -> list[TeamOut]:
    teams = db.scalars(select(Team).where(Team.sport == sport).order_by(Team.abbr)).all()
    return [
        TeamOut(
            id=t.team_id,
            sport=t.sport,
            abbr=t.abbr,
            name=t.name,
            conference=t.conference,
            division=t.division,
            logo_url=_team_logo(t),
            tier=t.tier,
            color=t.color,
            alt_color=t.alt_color,
        )
        for t in teams
    ]


def _prediction_probs(
    db: Session, season: int, sport: str, week: int | None = None
) -> dict[str, float]:
    """Latest prediction per game, scoped to the slate being rendered.

    Oldest first so newer rows win: a model version bump leaves more than one
    prediction row per game, and the cards must agree with the detail page.
    """
    stmt = (
        select(Prediction.game_id, Prediction.home_win_prob)
        .join(Game, Game.game_id == Prediction.game_id)
        .where(Game.season == season, Game.sport == sport)
        .order_by(Prediction.predicted_at)
    )
    if week is not None:
        stmt = stmt.where(Game.week == week)
    return dict(db.execute(stmt).all())


def _game_team(team: Team, ranks: dict[int, int]) -> GameTeam:
    if team.sport == SPORT_NFL:
        return GameTeam(abbr=team.abbr, name=nickname(team.name))
    return GameTeam(
        abbr=team.abbr,
        name=team.name,
        rank=ranks.get(team.team_id),
        conference=team.conference,
        logo_url=_team_logo(team),
        color=team.color,
    )


def prediction_verdict(
    home_win_prob: float | None, home_score: int | None, away_score: int | None
) -> bool | None:
    """Did the model pick the winner? None when there is nothing to grade:
    no prediction, an unfinished game, a tie, or an exact coin flip."""
    if home_win_prob is None or home_score is None or away_score is None:
        return None
    if home_score == away_score or home_win_prob == 0.5:
        return None
    return (home_win_prob > 0.5) == (home_score > away_score)


def _game_summary(game: Game, home_win_prob: float | None, ranks: dict[int, int]) -> GameSummary:
    return GameSummary(
        game_id=game.game_id,
        sport=game.sport,
        kickoff=game.kickoff_time,
        home=_game_team(game.home_team, ranks),
        away=_game_team(game.away_team, ranks),
        is_primetime=game.is_primetime,
        status=game.status,
        has_prediction=home_win_prob is not None,
        home_win_prob=home_win_prob,
        home_score=game.home_score,
        away_score=game.away_score,
        prediction_correct=prediction_verdict(home_win_prob, game.home_score, game.away_score),
    )


GameStatusFilter = Literal["all", "final", "upcoming"]


def _apply_status(query, status: str):
    """Keyed on scores, not Game.status: that column is derived, unindexed,
    and NFL sets it final on the home score alone."""
    both = Game.home_score.is_not(None) & Game.away_score.is_not(None)
    if status == "final":
        return query.where(both)
    if status == "upcoming":
        return query.where(~both)
    return query


def _season_games(
    db: Session, season: int, week: int | None = None, sport: str = SPORT_NFL, status: str = "all"
) -> list[Game]:
    query = (
        select(Game)
        .options(joinedload(Game.home_team), joinedload(Game.away_team))
        .where(Game.season == season, Game.sport == sport)
        .order_by(Game.kickoff_time)
    )
    if week is not None:
        query = query.where(Game.week == week)
    query = _apply_status(query, status)
    return list(db.scalars(query))


def get_schedule(
    db: Session, season: int, sport: str = SPORT_NFL, status: str = "all"
) -> ScheduleOut:
    games = _season_games(db, season, sport=sport, status=status)
    probs = _prediction_probs(db, season, sport)
    week_ranks = _poll_ranks_by_week(db, sport, season)
    weeks: dict[int, list[GameSummary]] = {}
    for game in games:
        weeks.setdefault(game.week, []).append(
            _game_summary(game, probs.get(game.game_id), week_ranks.get(game.week, {}))
        )
    return ScheduleOut(
        season=season,
        sport=sport,
        weeks=[WeekOut(week=w, games=weeks[w]) for w in sorted(weeks)],
    )


def get_games(
    db: Session, season: int, week: int, sport: str = SPORT_NFL, status: str = "all"
) -> list[GameSummary]:
    games = _season_games(db, season, week, sport=sport, status=status)
    probs = _prediction_probs(db, season, sport, week)
    ranks = poll_ranks_entering(db, sport, season, week)
    return [_game_summary(g, probs.get(g.game_id), ranks) for g in games]


def _record_entering(db: Session, team_id: int, game: Game) -> str:
    """Team's W-L(-T) record in this season before this game's kickoff.

    Falls back to game_date when kickoff is TBD (NULL)."""
    if game.kickoff_time is not None:
        before = Game.kickoff_time < game.kickoff_time
    else:
        before = Game.game_date < game.game_date
    prior = db.scalars(
        select(Game).where(
            Game.season == game.season,
            Game.sport == game.sport,
            before,
            Game.home_score.is_not(None),
            Game.away_score.is_not(None),
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


def _team_detail(
    db: Session, team: Team, game: Game, win_prob: float | None, ranks: dict[int, int]
) -> TeamDetail:
    is_cfb = team.sport == SPORT_CFB
    return TeamDetail(
        abbr=team.abbr,
        name=_display_name(team),
        record=_record_entering(db, team.team_id, game),
        logo_url=_team_logo(team),
        win_prob=win_prob,
        rank=ranks.get(team.team_id) if is_cfb else None,
        conference=team.conference if is_cfb else None,
        color=team.color if is_cfb else None,
    )


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
    ranks = poll_ranks_entering(db, game.sport, game.season, game.week)

    return PredictionOut(
        game_id=game.game_id,
        sport=game.sport,
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
        home=_team_detail(db, game.home_team, game, home_prob, ranks),
        away=_team_detail(
            db,
            game.away_team,
            game,
            None if home_prob is None else round(1.0 - home_prob, 4),
            ranks,
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
        prediction_status="ready" if prediction else "pending",
        home_score=game.home_score,
        away_score=game.away_score,
        prediction_correct=prediction_verdict(home_prob, game.home_score, game.away_score),
    )
