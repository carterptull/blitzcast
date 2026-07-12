"""Seed CFB reference data from CFBD: venues into stadiums, FBS teams plus
the FCS teams appearing on FBS schedules into teams, and the generated
alias file for the CFB name resolver. Re-running refreshes conference
membership (realignment currency).

Usage: python -m data_pipeline.seed_cfb [--start 2021] [--end 2026]
"""

import argparse
import re
import sys

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import SPORT_CFB, Stadium, Team
from data_pipeline import cfbd
from data_pipeline.cfb_games_loader import field
from data_pipeline.cfb_team_names import build_alias_map, derive_abbrs, save_aliases

# CFBD logos carry the ESPN CDN path .../ncaa/500/<espn_id>.png. [VERIFY]
_ESPN_LOGO_RE = re.compile(r"/(\d+)\.png$")


def espn_id_from_logo(logo: str | None) -> int | None:
    if not logo:
        return None
    match = _ESPN_LOGO_RE.search(logo)
    return int(match.group(1)) if match else None


def fcs_schools_on_fbs_schedules(years: list[int]) -> set[str]:
    schools: set[str] = set()
    for year in years:
        for row in cfbd.load_games(year).to_dict("records"):
            hc = str(field(row, "homeClassification", "home_division") or "").lower()
            ac = str(field(row, "awayClassification", "away_division") or "").lower()
            if hc == "fbs" and ac == "fcs":
                schools.add(field(row, "awayTeam", "away_team"))
            elif hc == "fcs" and ac == "fbs":
                schools.add(field(row, "homeTeam", "home_team"))
    schools.discard(None)
    return schools


def upsert_stadiums(
    db: Session, venues: pd.DataFrame
) -> tuple[dict[int, Stadium], dict[str, Stadium]]:
    """Upsert keyed by name; returns (cfbd venue id -> Stadium, name -> Stadium)."""
    by_id: dict[int, Stadium] = {}
    by_name = {s.name: s for s in db.scalars(select(Stadium))}
    for row in venues.to_dict("records"):
        name = field(row, "name")
        lat, lon = field(row, "latitude"), field(row, "longitude")
        if not name or lat is None or lon is None:
            continue
        stadium = by_name.get(name)
        if stadium is None:
            stadium = Stadium(name=name)
            db.add(stadium)
            by_name[name] = stadium
        stadium.city = field(row, "city") or ""
        stadium.lat = float(lat)
        stadium.lon = float(lon)
        stadium.is_dome = bool(field(row, "dome"))
        grass = field(row, "grass")
        stadium.surface = "unknown" if grass is None else ("grass" if grass else "turf")
        vid = field(row, "id")
        if vid is not None:
            by_id[int(vid)] = stadium
    db.flush()
    return by_id, by_name


def upsert_teams(
    db: Session,
    teams: pd.DataFrame,
    tiers: dict[str, str],
    venues_by_id: dict[int, Stadium],
    venues_by_name: dict[str, Stadium],
) -> int:
    abbrs = derive_abbrs(teams)
    existing = {t.abbr: t for t in db.scalars(select(Team).where(Team.sport == SPORT_CFB))}
    for row in teams.to_dict("records"):
        school = row["school"]
        abbr = abbrs[school]
        team = existing.get(abbr)
        if team is None:
            team = Team(sport=SPORT_CFB, abbr=abbr)
            db.add(team)
            existing[abbr] = team
        team.name = school
        team.conference = field(row, "conference") or "FCS-Ind"
        team.division = None
        team.tier = tiers[school]
        logos = row.get("logos")
        logo = logos[0] if isinstance(logos, list) and logos else None
        team.logo_url = logo
        team.espn_id = espn_id_from_logo(logo)
        team.color = field(row, "color")
        team.alt_color = field(row, "alternateColor", "alt_color")
        vid = field(row, "location.id", "location.venueId", "location.venue_id")
        stadium = venues_by_id.get(int(vid)) if vid is not None else None
        if stadium is None:
            stadium = venues_by_name.get(field(row, "location.name"))
        team.stadium_id = stadium.stadium_id if stadium else None
    db.flush()
    return len(teams)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2021)
    parser.add_argument("--end", type=int, default=2026)
    args = parser.parse_args()

    if not get_settings().cfbd_api_key:
        print("CFBD_API_KEY is not set in backend/.env — skipping CFB seed.")
        sys.exit(0)

    fbs = cfbd.load_fbs_teams(args.end).sort_values("school")
    fcs = cfbd.load_fcs_teams(args.end).sort_values("school")
    wanted = fcs_schools_on_fbs_schedules(list(range(args.start, args.end + 1)))
    fcs = fcs[fcs["school"].isin(wanted)]
    # FBS first: collision priority for abbr derivation.
    teams = pd.concat([fbs, fcs], ignore_index=True)
    tiers = {s: "FBS" for s in fbs["school"]} | {s: "FCS" for s in fcs["school"]}

    venues = cfbd.load_venues()
    with session_scope() as db:
        by_id, by_name = upsert_stadiums(db, venues)
        n_teams = upsert_teams(db, teams, tiers, by_id, by_name)
    aliases = build_alias_map(teams)
    save_aliases(aliases)
    print(
        f"seeded {n_teams} CFB teams ({len(fbs)} FBS, {len(fcs)} FCS), "
        f"{len(by_id)} venues, {len(aliases)} aliases"
    )


if __name__ == "__main__":
    main()
