"""Leakage-safe feature engineering.

Builds one feature row per game using only information available before
kickoff: rolling form is taken from each team's most recent *played* game
strictly before the target kickoff (via merge_asof), and Elo ratings are
pre-game ratings from a chronological replay.

Cold start (2026): rolling windows and Elo carry across the season boundary
(late-2025 form seeds early-2026 windows; Elo is regressed 25% to the mean),
and the market feature is always available, so Week 1 predictions are real
rather than a flat 50/50.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SPORT_NFL, Game, Injury, Odds, PollRank, Team, TeamGameStat, Weather
from ml import elo

DATA_DIR = Path(__file__).resolve().parent / "data"
FEATURES_PARQUET = DATA_DIR / "features.parquet"


def features_parquet(sport: str = SPORT_NFL) -> Path:
    """Per-sport feature cache; NFL keeps the legacy filename."""
    if sport.upper() == SPORT_NFL:
        return FEATURES_PARQUET
    return DATA_DIR / f"features_{sport.lower()}.parquet"

FEATURE_COLUMNS = [
    "elo_diff",
    "epa_off_diff",
    "epa_def_diff",
    "point_margin_diff",
    "win_pct_diff",
    "turnover_diff_diff",
    "rest_diff",
    "off_bye_diff",
    "short_week_diff",
    "b2b_road_diff",
    "qb_out_diff",
    "injury_sev_diff",
    "is_divisional",
    "is_primetime",
    "week_number",
    "temp_f",
    "wind_mph",
    "precip",
    "market_spread_home",
    "market_home_prob",
    # CFB-only signals; structurally 0.0 for NFL.
    "tier_diff",
    "poll_strength_diff",
]

TIER_VALUES = {"FBS": 1.0, "FCS": 0.0}

# Injury severity weights: positional importance x report status.
POSITION_WEIGHTS = {
    "QB": 8.0,
    "RB": 3.0, "FB": 1.0,
    "WR": 3.0, "TE": 2.0,
    "T": 2.5, "G": 2.5, "C": 2.5, "OT": 2.5, "OG": 2.5, "OL": 2.5,
    "DE": 2.0, "DT": 2.0, "NT": 2.0, "EDGE": 2.0, "DL": 2.0,
    "LB": 2.0, "ILB": 2.0, "OLB": 2.0, "MLB": 2.0,
    "CB": 2.0, "S": 2.0, "SS": 2.0, "FS": 2.0, "DB": 2.0,
    "K": 0.5, "P": 0.5, "LS": 0.5,
}
DEFAULT_POSITION_WEIGHT = 1.0
STATUS_WEIGHTS = {
    "out": 1.0,
    "injured reserve": 1.0,
    "ir": 1.0,
    "physically unable to perform": 1.0,
    "pup": 1.0,
    "doubtful": 0.75,
    "questionable": 0.4,
}
OUT_STATUSES = {k for k, v in STATUS_WEIGHTS.items() if v >= 0.75}


def moneyline_to_prob(ml: float) -> float:
    if ml < 0:
        return -ml / (-ml + 100.0)
    return 100.0 / (ml + 100.0)


def market_home_prob(home_ml, away_ml, spread_home) -> float | None:
    """De-vigged moneyline probability; spread-based fallback (25 Elo/point)."""
    if home_ml is not None and away_ml is not None:
        p_home = moneyline_to_prob(home_ml)
        p_away = moneyline_to_prob(away_ml)
        return p_home / (p_home + p_away)
    if spread_home is not None:
        return 1.0 / (1.0 + 10.0 ** (-spread_home * 25.0 / 400.0))
    return None


def injury_severity(rows: pd.DataFrame) -> float:
    total = 0.0
    for row in rows.itertuples(index=False):
        status = (row.status or "").lower()
        sw = STATUS_WEIGHTS.get(status, 0.0)
        if sw == 0.0:
            continue
        pw = POSITION_WEIGHTS.get((row.position or "").upper(), DEFAULT_POSITION_WEIGHT)
        total += pw * sw
    return total


def _load_frames(db: Session, sport: str = SPORT_NFL) -> dict[str, pd.DataFrame]:
    teams = pd.DataFrame(
        [(t.team_id, t.abbr, t.tier) for t in db.scalars(select(Team).where(Team.sport == sport))],
        columns=["team_id", "abbr", "tier"],
    )
    games = pd.DataFrame(
        [
            (
                g.game_id, g.season, g.week, g.kickoff_time, g.game_date,
                g.home_team_id, g.away_team_id, g.home_score, g.away_score,
                g.is_divisional, g.is_primetime, g.spread_line, g.total_line,
                g.home_moneyline, g.away_moneyline,
            )
            for g in db.scalars(
                select(Game)
                .where(Game.sport == sport)
                .order_by(func.coalesce(Game.kickoff_time, Game.game_date))
            )
        ],
        columns=[
            "game_id", "season", "week", "kickoff", "game_date",
            "home_team_id", "away_team_id", "home_score", "away_score",
            "is_divisional", "is_primetime", "spread_line", "total_line",
            "home_moneyline", "away_moneyline",
        ],
    )
    # TBD-kickoff (CFB) games get game_date at midnight UTC as a stand-in,
    # so merge_asof and the Elo replay always have a sortable, non-null key.
    games["kickoff"] = pd.to_datetime(games["kickoff"], utc=True).fillna(
        pd.to_datetime(games["game_date"], utc=True)
    )
    stats = pd.DataFrame(
        [
            (s.game_id, s.team_id, s.epa_offense, s.epa_defense, s.turnovers)
            for s in db.scalars(
                select(TeamGameStat)
                .join(Game, TeamGameStat.game_id == Game.game_id)
                .where(Game.sport == sport)
            )
        ],
        columns=["game_id", "team_id", "epa_offense", "epa_defense", "turnovers"],
    )
    injuries = pd.DataFrame(
        [
            (i.game_id, i.team_id, i.position, i.status)
            for i in db.scalars(
                select(Injury).join(Game, Injury.game_id == Game.game_id).where(Game.sport == sport)
            )
        ],
        columns=["game_id", "team_id", "position", "status"],
    )
    weather = pd.DataFrame(
        [
            (w.game_id, w.temp_f, w.wind_mph, w.precipitation)
            for w in db.scalars(
                select(Weather)
                .join(Game, Weather.game_id == Game.game_id)
                .where(Game.sport == sport)
            )
        ],
        columns=["game_id", "temp_f", "wind_mph", "precipitation"],
    )
    odds = pd.DataFrame(
        [
            (o.game_id, o.spread_home, o.moneyline_home, o.moneyline_away, o.captured_at)
            for o in db.scalars(
                select(Odds).join(Game, Odds.game_id == Game.game_id).where(Game.sport == sport)
            )
        ],
        columns=["game_id", "spread_home", "moneyline_home", "moneyline_away", "captured_at"],
    )
    polls = pd.DataFrame(
        [
            (p.season, p.week, p.poll, p.team_id, p.rank)
            for p in db.scalars(select(PollRank).where(PollRank.sport == sport))
        ],
        columns=["season", "week", "poll", "team_id", "rank"],
    )
    return {
        "teams": teams, "games": games, "stats": stats,
        "injuries": injuries, "weather": weather, "odds": odds, "polls": polls,
    }


def _poll_strength(polls: pd.DataFrame) -> pd.DataFrame:
    """Per (season, week, team): f(rank)=max(0, 26-rank) from the poll
    entering that week (AP preferred when a team appears in several polls)."""
    if polls.empty:
        return pd.DataFrame(columns=["season", "week", "team_id", "poll_strength"])
    p = polls.copy()
    p["is_ap"] = p["poll"].fillna("").str.contains("AP", case=False)
    p = p.sort_values("is_ap", ascending=False, kind="stable")
    p = p.drop_duplicates(subset=["season", "week", "team_id"], keep="first")
    p["poll_strength"] = (26.0 - p["rank"]).clip(lower=0.0)
    return p[["season", "week", "team_id", "poll_strength"]]


def _elo_pregame(
    games: pd.DataFrame,
    id_to_abbr: dict[int, str],
    config: elo.EloConfig = elo.NFL_CONFIG,
    tiers: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Chronological Elo replay: pre-game rating for every game row."""
    book = elo.EloBook(config=config, tiers=tiers or {})
    records = []
    for row in games.itertuples(index=False):
        home = id_to_abbr[row.home_team_id]
        away = id_to_abbr[row.away_team_id]
        elo_home, elo_away = book.pre_game(int(row.season), home, away)
        records.append((row.game_id, elo_home, elo_away))
        # Both scores: a live or forfeited row can carry one side only.
        if not pd.isna(row.home_score) and not pd.isna(row.away_score):
            book.record_result(
                int(row.season), home, away, int(row.home_score), int(row.away_score)
            )
    return pd.DataFrame(records, columns=["game_id", "elo_home", "elo_away"])


def _team_form(games: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """Post-game rolling form per (team, played game): last-5 EPA/margin/win%,
    last-3 turnover differential. Consumed via as-of merge."""
    played = games[games["home_score"].notna()]
    home = played[["game_id", "kickoff", "home_team_id", "home_score", "away_score"]].copy()
    home.columns = ["game_id", "kickoff", "team_id", "pts_for", "pts_against"]
    away = played[["game_id", "kickoff", "away_team_id", "away_score", "home_score"]].copy()
    away.columns = ["game_id", "kickoff", "team_id", "pts_for", "pts_against"]
    long = pd.concat([home, away], ignore_index=True)

    long = long.merge(stats, on=["game_id", "team_id"], how="left")
    opp = stats.rename(columns={"team_id": "opp_id", "turnovers": "opp_turnovers"})
    opp = opp[["game_id", "opp_id", "opp_turnovers"]]
    long = long.merge(opp, on="game_id", how="left")
    long = long[long["team_id"] != long["opp_id"]]

    long["margin"] = long["pts_for"] - long["pts_against"]
    long["win"] = (long["margin"] > 0).astype(float) + 0.5 * (long["margin"] == 0)
    long["to_diff"] = long["opp_turnovers"].fillna(0) - long["turnovers"].fillna(0)

    long = long.sort_values(["team_id", "kickoff"])
    grouped = long.groupby("team_id", sort=False)
    long["form_epa_off"] = grouped["epa_offense"].transform(
        lambda s: s.rolling(5, min_periods=1).mean()
    )
    long["form_epa_def"] = grouped["epa_defense"].transform(
        lambda s: s.rolling(5, min_periods=1).mean()
    )
    long["form_margin"] = grouped["margin"].transform(
        lambda s: s.rolling(5, min_periods=1).mean()
    )
    long["form_win_pct"] = grouped["win"].transform(
        lambda s: s.rolling(5, min_periods=1).mean()
    )
    long["form_to_diff"] = grouped["to_diff"].transform(
        lambda s: s.rolling(3, min_periods=1).mean()
    )
    return long[
        [
            "team_id", "kickoff",
            "form_epa_off", "form_epa_def", "form_margin", "form_win_pct", "form_to_diff",
        ]
    ]


def _asof_form(games: pd.DataFrame, form: pd.DataFrame, side: str) -> pd.DataFrame:
    """Most recent post-game form strictly before each game's kickoff."""
    left = games[["game_id", "kickoff", f"{side}_team_id"]].rename(
        columns={f"{side}_team_id": "team_id"}
    )
    left = left.sort_values("kickoff")
    right = form.sort_values("kickoff")
    merged = pd.merge_asof(
        left,
        right,
        on="kickoff",
        by="team_id",
        direction="backward",
        allow_exact_matches=False,
    )
    return merged.drop(columns=["kickoff", "team_id"]).set_index("game_id").add_prefix(f"{side}_")


def _rest_features(games: pd.DataFrame) -> pd.DataFrame:
    """Rest days / bye / short week / back-to-back road per (game, team)."""
    home = games[["game_id", "game_date", "home_team_id"]].copy()
    home["is_away"] = 0
    home.columns = ["game_id", "game_date", "team_id", "is_away"]
    away = games[["game_id", "game_date", "away_team_id"]].copy()
    away["is_away"] = 1
    away.columns = ["game_id", "game_date", "team_id", "is_away"]
    long = pd.concat([home, away], ignore_index=True).sort_values(["team_id", "game_date"])

    grouped = long.groupby("team_id", sort=False)
    long["prev_date"] = grouped["game_date"].shift(1)
    long["prev_away"] = grouped["is_away"].shift(1)
    rest = (
        pd.to_datetime(long["game_date"]) - pd.to_datetime(long["prev_date"])
    ).dt.days
    long["rest_days"] = rest.clip(upper=21).fillna(7.0)
    long["off_bye"] = (rest >= 13).astype(float)
    long["short_week"] = (rest <= 5).astype(float)
    long["b2b_road"] = ((long["is_away"] == 1) & (long["prev_away"] == 1)).astype(float)
    return long[["game_id", "team_id", "rest_days", "off_bye", "short_week", "b2b_road"]]


def _injury_features(injuries: pd.DataFrame) -> pd.DataFrame:
    if injuries.empty:
        return pd.DataFrame(columns=["game_id", "team_id", "qb_out", "injury_sev"])
    inj = injuries.copy()
    inj["status_l"] = inj["status"].fillna("").str.lower()
    inj["pos_u"] = inj["position"].fillna("").str.upper()
    inj["sw"] = inj["status_l"].map(STATUS_WEIGHTS).fillna(0.0)
    inj["pw"] = inj["pos_u"].map(POSITION_WEIGHTS).fillna(DEFAULT_POSITION_WEIGHT)
    inj["sev"] = inj["sw"] * inj["pw"]
    inj["is_qb_out"] = ((inj["pos_u"] == "QB") & inj["status_l"].isin(OUT_STATUSES)).astype(float)
    agg = inj.groupby(["game_id", "team_id"]).agg(
        qb_out=("is_qb_out", "max"), injury_sev=("sev", "sum")
    )
    return agg.reset_index()


def build_features(
    db: Session, seasons: list[int] | None = None, sport: str = SPORT_NFL
) -> pd.DataFrame:
    """One row per game: FEATURE_COLUMNS + metadata + home_win target
    (NaN for unplayed games)."""
    frames = _load_frames(db, sport)
    games = frames["games"]
    id_to_abbr = dict(
        zip(frames["teams"]["team_id"], frames["teams"]["abbr"], strict=True)
    )
    id_to_tier = dict(
        zip(frames["teams"]["team_id"], frames["teams"]["tier"], strict=True)
    )
    abbr_tiers = {id_to_abbr[tid]: tier for tid, tier in id_to_tier.items() if tier}

    elo_df = _elo_pregame(games, id_to_abbr, elo.config_for(sport), abbr_tiers)
    form = _team_form(games, frames["stats"])
    home_form = _asof_form(games, form, "home")
    away_form = _asof_form(games, form, "away")
    rest = _rest_features(games)
    inj = _injury_features(frames["injuries"])

    df = games.merge(elo_df, on="game_id")
    df = df.join(home_form, on="game_id").join(away_form, on="game_id")

    for side in ("home", "away"):
        side_rest = rest.rename(
            columns={
                "team_id": f"{side}_team_id",
                "rest_days": f"{side}_rest",
                "off_bye": f"{side}_off_bye",
                "short_week": f"{side}_short_week",
                "b2b_road": f"{side}_b2b_road",
            }
        )
        df = df.merge(side_rest, on=["game_id", f"{side}_team_id"], how="left")
        side_inj = inj.rename(
            columns={
                "team_id": f"{side}_team_id",
                "qb_out": f"{side}_qb_out",
                "injury_sev": f"{side}_injury_sev",
            }
        )
        df = df.merge(side_inj, on=["game_id", f"{side}_team_id"], how="left")
        df[f"{side}_qb_out"] = df[f"{side}_qb_out"].fillna(0.0).astype(float)
        df[f"{side}_injury_sev"] = df[f"{side}_injury_sev"].fillna(0.0).astype(float)

    df = df.merge(frames["weather"], on="game_id", how="left")

    # Prefer live odds rows (The Odds API) over nflverse schedule lines.
    odds = frames["odds"]
    if not odds.empty:
        # Pre-kickoff captures only. The refresh window reaches slightly into
        # in-progress games, and an in-play line must never reach training.
        odds = odds.merge(df[["game_id", "kickoff"]], on="game_id", how="inner")
        odds = odds[pd.to_datetime(odds["captured_at"], utc=True) < odds["kickoff"]]
    if not odds.empty:
        latest = odds.sort_values("captured_at").groupby("game_id").tail(1)
        df = df.merge(
            latest[["game_id", "spread_home", "moneyline_home", "moneyline_away"]],
            on="game_id",
            how="left",
        )
        df["spread_line"] = df["spread_home"].combine_first(df["spread_line"])
        df["home_moneyline"] = df["moneyline_home"].combine_first(df["home_moneyline"])
        df["away_moneyline"] = df["moneyline_away"].combine_first(df["away_moneyline"])

    # Diff features (home minus away).
    df["elo_diff"] = df["elo_home"] - df["elo_away"]
    df["epa_off_diff"] = df["home_form_epa_off"] - df["away_form_epa_off"]
    df["epa_def_diff"] = df["home_form_epa_def"] - df["away_form_epa_def"]
    df["point_margin_diff"] = df["home_form_margin"] - df["away_form_margin"]
    df["win_pct_diff"] = df["home_form_win_pct"] - df["away_form_win_pct"]
    df["turnover_diff_diff"] = df["home_form_to_diff"] - df["away_form_to_diff"]
    df["rest_diff"] = df["home_rest"] - df["away_rest"]
    df["off_bye_diff"] = df["home_off_bye"] - df["away_off_bye"]
    df["short_week_diff"] = df["home_short_week"] - df["away_short_week"]
    df["b2b_road_diff"] = df["home_b2b_road"] - df["away_b2b_road"]
    df["qb_out_diff"] = df["home_qb_out"] - df["away_qb_out"]
    df["injury_sev_diff"] = df["home_injury_sev"] - df["away_injury_sev"]
    df["is_divisional"] = df["is_divisional"].astype(float)
    df["is_primetime"] = df["is_primetime"].astype(float)
    df["week_number"] = df["week"].astype(float)

    # Weather: neutral fill for domes / missing forecasts.
    df["temp_f"] = pd.to_numeric(df["temp_f"], errors="coerce").fillna(70.0)
    df["wind_mph"] = pd.to_numeric(df["wind_mph"], errors="coerce").fillna(0.0)
    df["precip"] = (
        df["precipitation"].map({True: 1.0, False: 0.0}).astype(float).fillna(0.0)
    )

    df["market_spread_home"] = df["spread_line"]
    df["market_home_prob"] = df.apply(
        lambda r: market_home_prob(
            None if pd.isna(r["home_moneyline"]) else float(r["home_moneyline"]),
            None if pd.isna(r["away_moneyline"]) else float(r["away_moneyline"]),
            None if pd.isna(r["spread_line"]) else float(r["spread_line"]),
        ),
        axis=1,
    )

    # Tier class edge (FBS=1, FCS=0); 0.0 for NFL where tier is NULL.
    df["home_tier"] = df["home_team_id"].map(id_to_tier)
    df["away_tier"] = df["away_team_id"].map(id_to_tier)
    df["tier_diff"] = (
        df["home_tier"].map(TIER_VALUES).fillna(1.0)
        - df["away_tier"].map(TIER_VALUES).fillna(1.0)
    )

    # Poll standing entering the game's week (exact season+week join is
    # leakage-safe: the week-W poll is published before week W's games).
    strength = _poll_strength(frames["polls"])
    if strength.empty:
        df["poll_strength_diff"] = 0.0
    else:
        for side in ("home", "away"):
            side_poll = strength.rename(
                columns={"team_id": f"{side}_team_id", "poll_strength": f"{side}_poll_strength"}
            )
            df = df.merge(side_poll, on=["season", "week", f"{side}_team_id"], how="left")
            df[f"{side}_poll_strength"] = df[f"{side}_poll_strength"].fillna(0.0)
        df["poll_strength_diff"] = df["home_poll_strength"] - df["away_poll_strength"]

    df["home_win"] = np.where(
        df["home_score"].isna(),
        np.nan,
        (df["home_score"] > df["away_score"]).astype(float),
    )
    df["home_abbr"] = df["home_team_id"].map(id_to_abbr)
    df["away_abbr"] = df["away_team_id"].map(id_to_abbr)

    if seasons is not None:
        df = df[df["season"].isin(seasons)]

    meta = [
        "game_id", "season", "week", "kickoff", "home_abbr", "away_abbr",
        "home_tier", "away_tier", "home_win",
    ]
    return df[meta + FEATURE_COLUMNS].reset_index(drop=True)


def training_frame(db: Session, seasons: list[int], sport: str = SPORT_NFL) -> pd.DataFrame:
    """Played games in the given seasons, feature-complete, cached to parquet."""
    df = build_features(db, seasons=seasons, sport=sport)
    df = df[df["home_win"].notna()]
    cache = features_parquet(sport)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df
