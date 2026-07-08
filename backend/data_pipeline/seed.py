"""Load the hand-curated teams/stadiums seed files into the database.

Usage: python -m data_pipeline.seed
"""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Stadium, Team

SEEDS_DIR = Path(__file__).resolve().parent / "seeds"


def load_seeds(db: Session) -> tuple[int, int]:
    stadiums = json.loads((SEEDS_DIR / "stadiums.json").read_text(encoding="utf-8"))
    teams = json.loads((SEEDS_DIR / "teams.json").read_text(encoding="utf-8"))

    stadium_by_name: dict[str, Stadium] = {}
    for row in stadiums:
        existing = db.scalar(select(Stadium).where(Stadium.name == row["name"]))
        if existing is None:
            existing = Stadium(**row)
            db.add(existing)
        else:
            for key, value in row.items():
                setattr(existing, key, value)
        stadium_by_name[row["name"]] = existing
    db.flush()

    for row in teams:
        stadium = stadium_by_name[row["stadium"]]
        existing = db.scalar(select(Team).where(Team.abbr == row["abbr"]))
        if existing is None:
            existing = Team(abbr=row["abbr"])
            db.add(existing)
        existing.name = row["name"]
        existing.conference = row["conference"]
        existing.division = row["division"]
        existing.stadium_id = stadium.stadium_id
    db.flush()
    return len(teams), len(stadiums)


def main() -> None:
    with session_scope() as db:
        n_teams, n_stadiums = load_seeds(db)
    print(f"seeded {n_teams} teams, {n_stadiums} stadiums")


if __name__ == "__main__":
    main()
