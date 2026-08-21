"""Historical CFB backfill: games + betting lines, PPA -> team_game_stats,
and poll rankings for 5 seasons. CFB injuries are intentionally not loaded
(no standardized report — the injury features stay inert at 0.0).

Usage: python -m data_pipeline.backfill_cfb [--start 2021] [--end 2025]
"""

import argparse
import sys

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, Game, TeamGameStat
from data_pipeline import cfbd
from data_pipeline.cfb_games_loader import cfb_team_map, upsert_games
from data_pipeline.refresh_polls_cfb import upsert_polls

# Provider preference order for CFBD betting lines.
PREFERRED_PROVIDERS = ["consensus", "Bovada", "DraftKings", "ESPN Bet"]


def pick_lines(lines: pd.DataFrame) -> pd.DataFrame:
    """One line per game: first preferred provider present, else first seen."""
    ranks = {name.lower(): i for i, name in enumerate(PREFERRED_PROVIDERS)}
    df = lines.assign(
        _rank=lines["provider"].map(lambda p: ranks.get(str(p).lower(), len(ranks)))
    )
    df = df.sort_values(["game_id", "_rank"], kind="stable").groupby("game_id").head(1)
    return df.drop(columns="_rank")


def _season_games(db: Session, season: int) -> dict[str, Game]:
    return {
        g.game_id: g
        for g in db.scalars(
            select(Game).where(Game.sport == SPORT_CFB, Game.season == season)
        )
    }


def backfill_lines(db: Session, season: int) -> int:
    lines = cfbd.load_lines(season)
    if lines.empty:
        return 0
    games = _season_games(db, season)
    rows = 0
    for row in pick_lines(lines).itertuples(index=False):
        game = games.get(f"cfb_{int(row.game_id)}")
        if game is None:
            continue
        if not pd.isna(row.spread):
            # CFBD spread is betting convention (negative = home favored);
            # games.spread_line follows nflverse (positive = home favored).
            game.spread_line = -float(row.spread)
        if not pd.isna(row.over_under):
            game.total_line = float(row.over_under)
        if not pd.isna(row.home_moneyline):
            game.home_moneyline = int(row.home_moneyline)
        if not pd.isna(row.away_moneyline):
            game.away_moneyline = int(row.away_moneyline)
        rows += 1
    db.flush()
    return rows


def backfill_team_game_stats(db: Session, season: int) -> int:
    """PPA -> epa_offense/epa_defense; delete-then-insert scoped to the
    affected CFB game_ids only."""
    ppa = cfbd.load_team_game_ppa(season)
    if ppa.empty:
        return 0
    teams = cfb_team_map(db)
    games = _season_games(db, season)

    records = []
    seen: set[tuple[str, int]] = set()
    for row in ppa.to_dict("records"):
        gid = f"cfb_{int(row['game_id'])}"
        game = games.get(gid)
        team = teams.get(row.get("team"))
        if game is None or team is None:
            continue
        if team.team_id not in (game.home_team_id, game.away_team_id):
            continue
        if (gid, team.team_id) in seen:
            continue
        seen.add((gid, team.team_id))
        is_home = team.team_id == game.home_team_id
        off, dfn = row.get("ppa_offense"), row.get("ppa_defense")
        records.append(
            TeamGameStat(
                game_id=gid,
                team_id=team.team_id,
                points=game.home_score if is_home else game.away_score,
                yards=None,
                epa_offense=None if pd.isna(off) else float(off),
                epa_defense=None if pd.isna(dfn) else float(dfn),
                turnovers=None,
            )
        )

    game_ids = list({r.game_id for r in records})
    db.execute(delete(TeamGameStat).where(TeamGameStat.game_id.in_(game_ids)))
    db.add_all(records)
    db.flush()
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2021)
    parser.add_argument("--end", type=int, default=2026)
    args = parser.parse_args()

    if not get_settings().cfbd_api_key:
        print("CFBD_API_KEY is not set in backend/.env — skipping CFB backfill.")
        sys.exit(0)

    with session_scope() as db:
        for season in range(args.start, args.end + 1):
            written, skipped = upsert_games(db, cfbd.load_games(season))
            n_lines = backfill_lines(db, season)
            n_stats = backfill_team_game_stats(db, season)
            n_polls = upsert_polls(db, cfbd.load_rankings(season))
            print(
                f"{season}: games {written} (skipped {skipped}), lines {n_lines}, "
                f"team_game_stats {n_stats}, poll_ranks {n_polls}"
            )


if __name__ == "__main__":
    main()
