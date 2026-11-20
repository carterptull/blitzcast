"""add game postseason fields

Revision ID: d5a1c7e3f9b2
Revises: c3f1a9d27e48
Create Date: 2026-11-19 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models import ROUND_CHECK, SEASON_TYPE_CHECK
from app.postseason import super_bowl_name


# revision identifiers, used by Alembic.
revision: str = 'd5a1c7e3f9b2'
down_revision: Union[str, Sequence[str], None] = 'c3f1a9d27e48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# nflverse numbers playoff weeks 19-22 from 2021 (18-21 before the 17-game season).
_FIRST_PLAYOFF_WEEK_SQL = "CASE WHEN season >= 2021 THEN 19 ELSE 18 END"
_ROUND_BY_OFFSET = ("wild_card", "divisional", "conference", "super_bowl")


def backfill_statements(seasons: list[int]) -> list[str]:
    """SQL that marks past NFL playoff games, given the NFL seasons present."""
    offset = f"(week - {_FIRST_PLAYOFF_WEEK_SQL})"
    cases = " ".join(f"WHEN {i} THEN '{r}'" for i, r in enumerate(_ROUND_BY_OFFSET))
    statements = [
        "UPDATE games SET season_type = 'postseason', "
        f"round = CASE {offset} {cases} END "
        f"WHERE sport = 'NFL' AND week >= {_FIRST_PLAYOFF_WEEK_SQL} "
        f"AND {offset} BETWEEN 0 AND 3"
    ]
    for season in seasons:
        name = super_bowl_name(season).replace("'", "''")
        statements.append(
            f"UPDATE games SET event_name = '{name}' "
            f"WHERE sport = 'NFL' AND season = {int(season)} AND round = 'super_bowl'"
        )
    return statements


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('games', sa.Column(
        'season_type', sa.String(length=12), nullable=False, server_default='regular'))
    op.add_column('games', sa.Column('round', sa.String(length=24), nullable=True))
    op.add_column('games', sa.Column('event_name', sa.String(length=64), nullable=True))
    op.add_column('games', sa.Column('home_seed', sa.SmallInteger(), nullable=True))
    op.add_column('games', sa.Column('away_seed', sa.SmallInteger(), nullable=True))
    op.create_check_constraint('ck_games_season_type', 'games', SEASON_TYPE_CHECK)
    op.create_check_constraint('ck_games_round', 'games', ROUND_CHECK)

    conn = op.get_bind()
    seasons = [row[0] for row in conn.execute(
        sa.text("SELECT DISTINCT season FROM games WHERE sport = 'NFL'"))]
    for statement in backfill_statements(seasons):
        conn.execute(sa.text(statement))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_games_round', 'games', type_='check')
    op.drop_constraint('ck_games_season_type', 'games', type_='check')
    op.drop_column('games', 'away_seed')
    op.drop_column('games', 'home_seed')
    op.drop_column('games', 'event_name')
    op.drop_column('games', 'round')
    op.drop_column('games', 'season_type')
