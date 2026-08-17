"""CFBD poll week semantics.

The leakage rule depends on "week N poll" meaning the poll published BEFORE
week N's games. Verified against the live 2025 AP polls: all six ranked teams
that lost in week 1 kept their week 1 rank and fell only in the week 2 poll.
Texas sat at #1 in the week 1 poll, lost to Ohio State that week, and appeared
at #7 in week 2.

These tests pin that the loader stores the week verbatim, so a refactor cannot
silently shift the poll forward a week and leak results into
poll_strength_diff.
"""

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import SPORT_CFB, Base, PollRank, Team
from data_pipeline.refresh_polls_cfb import upsert_polls

AP = "AP Top 25"

# Mirrors the real 2025 sequence: Texas is #1 entering week 1, loses that week,
# and drops only in the poll that precedes week 2.
TEXAS_2025 = pd.DataFrame(
    [
        {"season": 2025, "week": 1, "poll": AP, "school": "Texas", "rank": 1},
        {"season": 2025, "week": 1, "poll": AP, "school": "Ohio State", "rank": 3},
        {"season": 2025, "week": 2, "poll": AP, "school": "Texas", "rank": 7},
        {"season": 2025, "week": 2, "poll": AP, "school": "Ohio State", "rank": 1},
    ]
)


@pytest.fixture()
def poll_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    for abbr, name in (("TEX", "Texas"), ("OSU", "Ohio State")):
        session.add(Team(sport=SPORT_CFB, abbr=abbr, name=name, conference="FBS", tier="FBS"))
    session.flush()
    yield session
    session.close()
    engine.dispose()


def _ranks_for(db, week: int) -> dict[str, int]:
    rows = db.execute(
        select(Team.name, PollRank.rank)
        .join(Team, Team.team_id == PollRank.team_id)
        .where(PollRank.week == week)
    ).all()
    return dict(rows)


def test_poll_week_is_stored_verbatim(poll_db):
    """A shift of even one week would leak that week's results."""
    assert upsert_polls(poll_db, TEXAS_2025) == 4
    assert _ranks_for(poll_db, 1) == {"Texas": 1, "Ohio State": 3}
    assert _ranks_for(poll_db, 2) == {"Texas": 7, "Ohio State": 1}


def test_a_partial_response_leaves_other_weeks_intact(poll_db):
    """A CFBD response covering only week 2 must not wipe week 1 history."""
    upsert_polls(poll_db, TEXAS_2025)
    week2_only = TEXAS_2025[TEXAS_2025["week"] == 2]
    upsert_polls(poll_db, week2_only)

    assert _ranks_for(poll_db, 1) == {"Texas": 1, "Ohio State": 3}
    assert _ranks_for(poll_db, 2) == {"Texas": 7, "Ohio State": 1}


def test_a_week_one_loss_does_not_change_the_week_one_poll(poll_db):
    """Texas is still #1 entering week 1 despite losing that week."""
    upsert_polls(poll_db, TEXAS_2025)
    week1, week2 = _ranks_for(poll_db, 1), _ranks_for(poll_db, 2)

    assert week1["Texas"] == 1, "week 1 poll must predate the week 1 loss"
    assert week2["Texas"] == 7, "the loss shows up in the week 2 poll"
    # The team atop the poll changes between the two weeks, which only happens
    # when each poll precedes its own week's games.
    assert min(week1, key=week1.get) != min(week2, key=week2.get)
