"""initial schema

Revision ID: afd772fc0bff
Revises: 
Create Date: 2026-07-06 11:37:01.298267

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'afd772fc0bff'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('stadiums',
    sa.Column('stadium_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('lat', sa.Float(), nullable=False),
    sa.Column('lon', sa.Float(), nullable=False),
    sa.Column('is_dome', sa.Boolean(), nullable=False),
    sa.Column('surface', sa.String(length=30), nullable=False),
    sa.PrimaryKeyConstraint('stadium_id')
    )
    op.create_table('teams',
    sa.Column('team_id', sa.Integer(), nullable=False),
    sa.Column('abbr', sa.String(length=4), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('conference', sa.String(length=3), nullable=False),
    sa.Column('division', sa.String(length=10), nullable=False),
    sa.Column('stadium_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['stadium_id'], ['stadiums.stadium_id'], ),
    sa.PrimaryKeyConstraint('team_id')
    )
    op.create_index(op.f('ix_teams_abbr'), 'teams', ['abbr'], unique=True)
    op.create_table('games',
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('season', sa.Integer(), nullable=False),
    sa.Column('week', sa.Integer(), nullable=False),
    sa.Column('game_date', sa.Date(), nullable=False),
    sa.Column('kickoff_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('home_team_id', sa.Integer(), nullable=False),
    sa.Column('away_team_id', sa.Integer(), nullable=False),
    sa.Column('stadium_id', sa.Integer(), nullable=True),
    sa.Column('is_primetime', sa.Boolean(), nullable=False),
    sa.Column('is_divisional', sa.Boolean(), nullable=False),
    sa.Column('home_score', sa.Integer(), nullable=True),
    sa.Column('away_score', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('spread_line', sa.Float(), nullable=True),
    sa.Column('total_line', sa.Float(), nullable=True),
    sa.Column('home_moneyline', sa.Integer(), nullable=True),
    sa.Column('away_moneyline', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['away_team_id'], ['teams.team_id'], ),
    sa.ForeignKeyConstraint(['home_team_id'], ['teams.team_id'], ),
    sa.ForeignKeyConstraint(['stadium_id'], ['stadiums.stadium_id'], ),
    sa.PrimaryKeyConstraint('game_id')
    )
    op.create_index(op.f('ix_games_season'), 'games', ['season'], unique=False)
    op.create_index(op.f('ix_games_week'), 'games', ['week'], unique=False)
    op.create_table('team_ratings',
    sa.Column('team_id', sa.Integer(), nullable=False),
    sa.Column('season', sa.Integer(), nullable=False),
    sa.Column('week', sa.Integer(), nullable=False),
    sa.Column('elo_rating', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ),
    sa.PrimaryKeyConstraint('team_id', 'season', 'week')
    )
    op.create_table('injuries',
    sa.Column('injury_id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('team_id', sa.Integer(), nullable=False),
    sa.Column('player_name', sa.String(length=80), nullable=False),
    sa.Column('position', sa.String(length=6), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=True),
    sa.Column('report_date', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['game_id'], ['games.game_id'], ),
    sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ),
    sa.PrimaryKeyConstraint('injury_id'),
    sa.UniqueConstraint('game_id', 'team_id', 'player_name', name='uq_injury_game_player')
    )
    op.create_index(op.f('ix_injuries_game_id'), 'injuries', ['game_id'], unique=False)
    op.create_table('odds',
    sa.Column('odds_id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=40), nullable=False),
    sa.Column('spread_home', sa.Float(), nullable=True),
    sa.Column('moneyline_home', sa.Integer(), nullable=True),
    sa.Column('moneyline_away', sa.Integer(), nullable=True),
    sa.Column('total', sa.Float(), nullable=True),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['games.game_id'], ),
    sa.PrimaryKeyConstraint('odds_id'),
    sa.UniqueConstraint('game_id', 'source', name='uq_odds_game_source')
    )
    op.create_index(op.f('ix_odds_game_id'), 'odds', ['game_id'], unique=False)
    op.create_table('predictions',
    sa.Column('prediction_id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('model_version', sa.String(length=20), nullable=False),
    sa.Column('home_win_prob', sa.Float(), nullable=False),
    sa.Column('predicted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('shap_top_features', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('llm_narrative', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['game_id'], ['games.game_id'], ),
    sa.PrimaryKeyConstraint('prediction_id'),
    sa.UniqueConstraint('game_id', 'model_version', name='uq_prediction_game_version')
    )
    op.create_index(op.f('ix_predictions_game_id'), 'predictions', ['game_id'], unique=False)
    op.create_table('team_game_stats',
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('team_id', sa.Integer(), nullable=False),
    sa.Column('points', sa.Integer(), nullable=True),
    sa.Column('yards', sa.Float(), nullable=True),
    sa.Column('epa_offense', sa.Float(), nullable=True),
    sa.Column('epa_defense', sa.Float(), nullable=True),
    sa.Column('turnovers', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['game_id'], ['games.game_id'], ),
    sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ),
    sa.PrimaryKeyConstraint('game_id', 'team_id')
    )
    op.create_table('weather',
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('temp_f', sa.Float(), nullable=True),
    sa.Column('wind_mph', sa.Float(), nullable=True),
    sa.Column('precipitation', sa.Boolean(), nullable=True),
    sa.Column('conditions', sa.String(length=80), nullable=True),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['games.game_id'], ),
    sa.PrimaryKeyConstraint('game_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('weather')
    op.drop_table('team_game_stats')
    op.drop_index(op.f('ix_predictions_game_id'), table_name='predictions')
    op.drop_table('predictions')
    op.drop_index(op.f('ix_odds_game_id'), table_name='odds')
    op.drop_table('odds')
    op.drop_index(op.f('ix_injuries_game_id'), table_name='injuries')
    op.drop_table('injuries')
    op.drop_table('team_ratings')
    op.drop_index(op.f('ix_games_week'), table_name='games')
    op.drop_index(op.f('ix_games_season'), table_name='games')
    op.drop_table('games')
    op.drop_index(op.f('ix_teams_abbr'), table_name='teams')
    op.drop_table('teams')
    op.drop_table('stadiums')
