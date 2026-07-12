"""add sport dimension for CFB expansion

Adds a sport discriminator to teams/games/team_ratings, widens team
fields for CFB, and rebuilds uniqueness so NFL and CFB coexist.
Existing NFL rows are backfilled sport='NFL' via server defaults.
Downgrade will fail if CFB rows exist — remove them first.

Revision ID: b7e42c9d1a05
Revises: afd772fc0bff
Create Date: 2026-07-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e42c9d1a05'
down_revision: Union[str, Sequence[str], None] = 'afd772fc0bff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # teams: sport column, widened fields, per-sport abbr uniqueness
    op.add_column('teams', sa.Column('sport', sa.String(length=8), nullable=False, server_default='NFL'))
    op.add_column('teams', sa.Column('tier', sa.String(length=3), nullable=True))
    op.add_column('teams', sa.Column('espn_id', sa.Integer(), nullable=True))
    op.alter_column('teams', 'abbr', existing_type=sa.String(length=4), type_=sa.String(length=16), existing_nullable=False)
    op.alter_column('teams', 'conference', existing_type=sa.String(length=3), type_=sa.String(length=40), existing_nullable=False)
    op.alter_column('teams', 'division', existing_type=sa.String(length=10), nullable=True)
    op.drop_index(op.f('ix_teams_abbr'), table_name='teams')
    op.create_index(op.f('ix_teams_abbr'), 'teams', ['abbr'], unique=False)
    op.create_index(op.f('ix_teams_sport'), 'teams', ['sport'], unique=False)
    op.create_unique_constraint('uq_team_sport_abbr', 'teams', ['sport', 'abbr'])

    op.add_column('teams', sa.Column('color', sa.String(length=9), nullable=True))
    op.add_column('teams', sa.Column('alt_color', sa.String(length=9), nullable=True))
    op.add_column('teams', sa.Column('logo_url', sa.String(length=255), nullable=True))

    # games: sport column
    op.add_column('games', sa.Column('sport', sa.String(length=8), nullable=False, server_default='NFL'))
    op.create_index(op.f('ix_games_sport'), 'games', ['sport'], unique=False)

    # weekly poll rankings (CFB): the poll entering (season, week)
    op.create_table('poll_ranks',
        sa.Column('poll_rank_id', sa.Integer(), nullable=False),
        sa.Column('sport', sa.String(length=8), nullable=False, server_default='CFB'),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('poll', sa.String(length=30), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ),
        sa.PrimaryKeyConstraint('poll_rank_id'),
        sa.UniqueConstraint('sport', 'season', 'week', 'poll', 'team_id', name='uq_poll_rank'),
    )
    op.create_index(op.f('ix_poll_ranks_season'), 'poll_ranks', ['season'], unique=False)
    op.create_index(op.f('ix_poll_ranks_week'), 'poll_ranks', ['week'], unique=False)

    # team_ratings: sport joins the primary key so per-sport Elo coexists
    op.add_column('team_ratings', sa.Column('sport', sa.String(length=8), nullable=False, server_default='NFL'))
    op.drop_constraint('team_ratings_pkey', 'team_ratings', type_='primary')
    op.create_primary_key('team_ratings_pkey', 'team_ratings', ['sport', 'team_id', 'season', 'week'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_poll_ranks_week'), table_name='poll_ranks')
    op.drop_index(op.f('ix_poll_ranks_season'), table_name='poll_ranks')
    op.drop_table('poll_ranks')

    op.drop_constraint('team_ratings_pkey', 'team_ratings', type_='primary')
    op.create_primary_key('team_ratings_pkey', 'team_ratings', ['team_id', 'season', 'week'])
    op.drop_column('team_ratings', 'sport')

    op.drop_index(op.f('ix_games_sport'), table_name='games')
    op.drop_column('games', 'sport')

    op.drop_constraint('uq_team_sport_abbr', 'teams', type_='unique')
    op.drop_index(op.f('ix_teams_sport'), table_name='teams')
    op.drop_index(op.f('ix_teams_abbr'), table_name='teams')
    op.create_index(op.f('ix_teams_abbr'), 'teams', ['abbr'], unique=True)
    op.alter_column('teams', 'division', existing_type=sa.String(length=10), nullable=False)
    op.alter_column('teams', 'conference', existing_type=sa.String(length=40), type_=sa.String(length=3), existing_nullable=False)
    op.alter_column('teams', 'abbr', existing_type=sa.String(length=16), type_=sa.String(length=4), existing_nullable=False)
    op.drop_column('teams', 'logo_url')
    op.drop_column('teams', 'alt_color')
    op.drop_column('teams', 'color')
    op.drop_column('teams', 'espn_id')
    op.drop_column('teams', 'tier')
