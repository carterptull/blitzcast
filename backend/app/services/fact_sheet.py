"""Pre-game fact sheet for narration. Every fact the narrator may state is
rendered here in plain words, from data strictly before kickoff, so each claim
in the narration can be checked against it."""

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SPORT_CFB, SPORT_NFL, Game, Injury, Team, Weather
from app.services.predictions import latest_odds_by_game, record_string, season_games_before
from data_pipeline.team_names import nickname
from ml.features import DEFAULT_POSITION_WEIGHT, POSITION_WEIGHTS

ET = ZoneInfo("America/New_York")
NARRATED_INJURY_STATUSES = {"out", "doubtful"}
MAX_INJURIES_PER_TEAM = 3

FACTOR_PHRASES = {
    "elo_diff": "season-long team strength rating",
    "epa_off_diff": "offensive efficiency over the last 5 games",
    "epa_def_diff": "defensive efficiency over the last 5 games",
    "point_margin_diff": "point differential over the last 5 games",
    "win_pct_diff": "win rate over the last 5 games",
    "turnover_diff_diff": "turnover margin over the last 3 games",
    "rest_diff": "rest advantage",
    "off_bye_diff": "coming off a bye",
    "short_week_diff": "short-week fatigue",
    "b2b_road_diff": "back-to-back road trips",
    "qb_out_diff": "quarterback availability",
    "injury_sev_diff": "overall injury report",
    "is_divisional": "division familiarity",
    "temp_f": "kickoff temperature",
    "wind_mph": "wind",
    "precip": "precipitation",
    "tier_diff": "FBS versus FCS class gap",
    "poll_strength_diff": "AP poll standing",
}
CFB_PHRASE_OVERRIDES = {"is_divisional": "conference familiarity"}
MARKET_FEATURES = {"market_spread_home", "market_home_prob"}
# Rolling windows that span the season boundary until a team has played this many games.
FORM_WINDOWS = {
    "epa_off_diff": 5, "epa_def_diff": 5, "point_margin_diff": 5,
    "win_pct_diff": 5, "turnover_diff_diff": 3,
}


@dataclass(frozen=True)
class TeamFacts:
    name: str
    full_name: str
    abbr: str
    mascot: str | None
    record: str
    games_this_season: int
    last_game: str | None
    streak: str | None
    scoring: str | None
    rank: int | None
    rank_note: str | None
    rest: str | None
    injuries: tuple[str, ...]


@dataclass(frozen=True)
class GameFacts:
    sport: str
    home: TeamFacts
    away: TeamFacts
    home_win_prob: float
    spread_home: float | None
    total: float | None
    when: str
    venue: str | None
    is_neutral_site: bool
    matchup_note: str | None
    last_meeting: str | None
    weather: str | None
    factor_lines: tuple[str, ...]


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _short_name(team: Team) -> str:
    return nickname(team.name) if team.sport == SPORT_NFL else team.name


def _opponent_ref(team: Team) -> str:
    return f"the {nickname(team.name)}" if team.sport == SPORT_NFL else team.name


def _scores(g: Game, team_id: int) -> tuple[int, int]:
    home = g.home_team_id == team_id
    return (g.home_score, g.away_score) if home else (g.away_score, g.home_score)


def _result_phrase(g: Game, team_id: int) -> str:
    own, opp = _scores(g, team_id)
    opponent = g.away_team if g.home_team_id == team_id else g.home_team
    if g.is_neutral_site:
        where = "at a neutral site"
    else:
        where = "at home" if g.home_team_id == team_id else "on the road"
    if own > opp:
        return f"beat {_opponent_ref(opponent)} {own}-{opp} {where}"
    if own < opp:
        return f"lost to {_opponent_ref(opponent)} {opp}-{own} {where}"
    return f"tied {_opponent_ref(opponent)} {own}-{opp} {where}"


def _streak(games: list[Game], team_id: int) -> str | None:
    outcomes = []
    for g in games:
        own, opp = _scores(g, team_id)
        outcomes.append("W" if own > opp else "L" if own < opp else "T")
    if not outcomes or outcomes[-1] == "T":
        return None
    last, run = outcomes[-1], 0
    for o in reversed(outcomes):
        if o != last:
            break
        run += 1
    if run < 2:
        return None
    return f"{'won' if last == 'W' else 'lost'} {run} straight"


def _scoring(games: list[Game], team_id: int) -> str | None:
    recent = games[-3:]
    if len(recent) < 2:
        return None
    pf = sum(_scores(g, team_id)[0] for g in recent) / len(recent)
    pa = sum(_scores(g, team_id)[1] for g in recent) / len(recent)
    return f"averaging {pf:.1f} points and allowing {pa:.1f} over the last {len(recent)} games"


def _rest(db: Session, team_id: int, game: Game) -> str | None:
    prev = db.scalar(
        select(Game.game_date)
        .where(
            Game.sport == game.sport,
            Game.game_date < game.game_date,
            (Game.home_team_id == team_id) | (Game.away_team_id == team_id),
        )
        .order_by(Game.game_date.desc())
        .limit(1)
    )
    if prev is None:
        return None
    days = (game.game_date - prev).days
    if days <= 5:
        return "on a short week"
    if 13 <= days <= 21:
        return "coming off a bye"
    return None


def _injuries(db: Session, game: Game, team_id: int) -> tuple[str, ...]:
    if game.sport != SPORT_NFL:
        return ()
    rows = db.scalars(
        select(Injury).where(Injury.game_id == game.game_id, Injury.team_id == team_id)
    ).all()
    listed = [r for r in rows if (r.status or "").lower() in NARRATED_INJURY_STATUSES]
    listed.sort(
        key=lambda r: -POSITION_WEIGHTS.get((r.position or "").upper(), DEFAULT_POSITION_WEIGHT)
    )
    return tuple(
        f"{r.player_name} ({r.position}) is listed {r.status.title()}"
        for r in listed[:MAX_INJURIES_PER_TEAM]
    )


def _rank_note(team_id: int, ranks: dict[int, int], prev_ranks: dict[int, int]) -> str | None:
    rank, prev = ranks.get(team_id), prev_ranks.get(team_id)
    if rank is None or not prev_ranks:
        return None
    if prev is None:
        return "new to the poll this week"
    if rank < prev:
        return f"up from #{prev}"
    if rank > prev:
        return f"down from #{prev}"
    return "holding steady"


def _team_facts(db, game, team, ranks, prev_ranks) -> TeamFacts:
    games = season_games_before(db, team.team_id, game)
    is_nfl = team.sport == SPORT_NFL
    full_name = team.name if is_nfl else f"{team.name} {team.mascot or ''}".strip()
    return TeamFacts(
        name=_short_name(team),
        full_name=full_name,
        abbr=team.abbr,
        mascot=nickname(team.name) if is_nfl else team.mascot,
        record=record_string(games, team.team_id),
        games_this_season=len(games),
        last_game=_result_phrase(games[-1], team.team_id) if games else None,
        streak=_streak(games, team.team_id),
        scoring=_scoring(games, team.team_id),
        rank=ranks.get(team.team_id),
        rank_note=_rank_note(team.team_id, ranks, prev_ranks),
        rest=_rest(db, team.team_id, game),
        injuries=_injuries(db, game, team.team_id),
    )


def _when(game: Game) -> str:
    if game.kickoff_time is None:
        return f"{game.game_date.strftime('%A')}, kickoff time to be announced"
    local = _utc(game.kickoff_time).astimezone(ET)
    window = "morning" if local.hour < 12 else "afternoon" if local.hour < 17 else "night"
    return f"{local.strftime('%A')} {window}"


def _venue(game: Game) -> str | None:
    if game.stadium is not None:
        return f"{game.stadium.name} in {game.stadium.city}"
    return game.venue_name


def _matchup_note(game: Game) -> str | None:
    home, away = game.home_team, game.away_team
    if game.sport == SPORT_NFL:
        if game.is_divisional and home.division:
            return f"{home.conference} {home.division} division game"
        if home.conference == away.conference:
            return f"{home.conference} matchup"
        return f"{away.conference} versus {home.conference} interconference game"
    if game.is_divisional and home.conference:
        return f"{home.conference} conference game"
    if home.conference and away.conference and home.conference != away.conference:
        return f"nonconference game, {away.conference} at {home.conference}"
    return None


def _last_meeting(db: Session, game: Game) -> str | None:
    pair = {game.home_team_id, game.away_team_id}
    query = select(Game).where(
        Game.sport == game.sport,
        Game.home_team_id.in_(pair),
        Game.away_team_id.in_(pair),
        Game.game_id != game.game_id,
        Game.home_score.is_not(None),
        Game.away_score.is_not(None),
    )
    if game.kickoff_time is not None:
        query = query.where(Game.kickoff_time < game.kickoff_time)
    else:
        query = query.where(Game.game_date < game.game_date)
    prior = db.scalars(query.order_by(Game.game_date.desc()).limit(1)).first()
    if prior is None:
        return None
    hs, as_ = prior.home_score, prior.away_score
    if hs == as_:
        return f"tied {hs}-{as_} in Week {prior.week} of {prior.season}"
    winner = _short_name(prior.home_team if hs > as_ else prior.away_team)
    score = f"{max(hs, as_)}-{min(hs, as_)}"
    return f"{winner} won {score} in Week {prior.week} of {prior.season}"


def _weather(db: Session, game: Game) -> str | None:
    if game.stadium is not None and game.stadium.is_dome:
        return "indoors"
    w = db.get(Weather, game.game_id)
    if w is None or w.temp_f is None:
        return None
    text = f"{w.temp_f:.0f} degrees, wind {w.wind_mph or 0:.0f} mph"
    return text + ", rain or snow likely" if w.precipitation else text


def _factor_lines(
    factors: list[dict], home: TeamFacts, away: TeamFacts, sport: str, spread_home: float | None
) -> tuple[str, ...]:
    phrases = FACTOR_PHRASES | (CFB_PHRASE_OVERRIDES if sport == SPORT_CFB else {})
    fewest_games = min(home.games_this_season, away.games_this_season)
    lines, market_done = [], False
    for f in factors:
        feature = f.get("feature")
        team = home if f["direction"] == "home" else away
        if feature in MARKET_FEATURES:
            if market_done or spread_home is None:
                continue
            market_done = True
            lines.append(f"{team.name}: betting market")
            continue
        phrase = phrases.get(feature)
        if phrase is None:
            continue
        if fewest_games < FORM_WINDOWS.get(feature, 0):
            phrase += " (this window still includes last season's games)"
        lines.append(f"{team.name}: {phrase}")
    return tuple(lines)


def _total(db: Session, game: Game) -> float | None:
    odds = latest_odds_by_game(db, {game.game_id: game}).get(game.game_id)
    if odds is not None and odds.total is not None:
        return odds.total
    return game.total_line


def build_game_facts(
    db: Session,
    game: Game,
    home_win_prob: float,
    factors: list[dict],
    spread_home: float | None,
    ranks: dict[int, int] | None = None,
    prev_ranks: dict[int, int] | None = None,
) -> GameFacts:
    ranks, prev_ranks = ranks or {}, prev_ranks or {}
    home = _team_facts(db, game, game.home_team, ranks, prev_ranks)
    away = _team_facts(db, game, game.away_team, ranks, prev_ranks)
    return GameFacts(
        sport=game.sport,
        home=home,
        away=away,
        home_win_prob=home_win_prob,
        spread_home=spread_home,
        total=_total(db, game) if spread_home is not None else None,
        when=_when(game),
        venue=_venue(game),
        is_neutral_site=bool(game.is_neutral_site),
        matchup_note=_matchup_note(game),
        last_meeting=_last_meeting(db, game),
        weather=_weather(db, game),
        factor_lines=_factor_lines(factors, home, away, game.sport, spread_home),
    )


def market_favorite(facts: GameFacts) -> tuple[TeamFacts, TeamFacts] | None:
    if facts.spread_home is None or facts.spread_home == 0:
        return None
    if facts.spread_home > 0:
        return facts.home, facts.away
    return facts.away, facts.home


def _market_line(facts: GameFacts) -> str:
    if facts.spread_home is None:
        return "No betting line posted for this game."
    total = f" Total {facts.total:g}." if facts.total is not None else ""
    pair = market_favorite(facts)
    if pair is None:
        return f"Betting market: a pick'em.{total}"
    fav, dog = pair
    line = abs(facts.spread_home)
    return (
        f"Betting market: {fav.name} favored by {line:g} points "
        f"({fav.abbr} -{line:g}, {dog.abbr} +{line:g}).{total}"
    )


def _team_block(t: TeamFacts, sport: str) -> list[str]:
    head = f"{t.full_name} ({t.abbr})" + (f", also called the {t.mascot}" if t.mascot else "")
    rows = [head, f"- Record this season: {t.record}"]
    if t.rank:
        rows.append(f"- AP rank: #{t.rank}" + (f", {t.rank_note}" if t.rank_note else ""))
    elif sport == SPORT_CFB:
        rows.append("- AP rank: unranked")
    for label, value in (
        ("Last game", t.last_game), ("Streak", t.streak),
        ("Scoring", t.scoring), ("Rest", t.rest),
    ):
        if value:
            rows.append(f"- {label}: {value}")
    if t.games_this_season == 0:
        rows.append("- First game of the season")
    for injury in t.injuries:
        rows.append(f"- Injury report: {injury}")
    return rows


def render_fact_sheet(facts: GameFacts) -> str:
    p_home = facts.home_win_prob
    model_fav, model_dog, p = (
        (facts.home, facts.away, p_home) if p_home >= 0.5 else (facts.away, facts.home, 1 - p_home)
    )
    lines = [
        f"Sport: {facts.sport}",
        f"Matchup: {facts.away.name} at {facts.home.name}"
        + (" (neutral site)" if facts.is_neutral_site else ""),
        f"When: {facts.when}",
    ]
    if facts.venue:
        lines.append(f"Where: {facts.venue}")
    if facts.matchup_note:
        lines.append(f"Game type: {facts.matchup_note}")
    lines.append(
        f"Model: {model_fav.name} {p:.0%} to win, {model_dog.name} {1 - p:.0%}"
    )
    lines.append(_market_line(facts))
    if facts.last_meeting:
        lines.append(f"Last meeting: {facts.last_meeting}")
    if facts.weather:
        lines.append(f"Weather: {facts.weather}")
    lines.append("")
    lines += _team_block(facts.home, facts.sport)
    lines.append("")
    lines += _team_block(facts.away, facts.sport)
    if facts.factor_lines:
        lines += ["", "Biggest factors behind the model's number (team they favor: factor):"]
        lines += [f"- {line}" for line in facts.factor_lines]
    return "\n".join(lines)
