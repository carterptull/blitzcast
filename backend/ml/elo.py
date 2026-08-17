"""Elo ratings, parameterized per sport via EloConfig.

NFL keeps the original constants (K=20, HFA=55, logistic scale 400, base
1500, 0.75 season regression, no margin-of-victory) so its math is
unchanged. CFB uses a stronger home edge, heavier season regression, a
538-style margin-of-victory multiplier (margin capped to blunt cupcake
blowouts), and anchors FCS-tier teams 350 points below base at first
appearance and each season rollover.

Note: the recruiting / returning-production preseason anchor is deferred
to v2; CFB v1 ships the regression + FCS-floor baseline.
"""

import math
from dataclasses import dataclass, field

from app.models import SPORT_CFB

K = 20.0
HFA = 55.0
SCALE = 400.0
BASE = 1500.0
SEASON_REGRESSION = 0.75


@dataclass(frozen=True)
class EloConfig:
    k: float = K
    hfa: float = HFA
    scale: float = SCALE
    base: float = BASE
    season_regression: float = SEASON_REGRESSION
    mov: bool = False
    margin_cap: int = 28
    fcs_offset: float = 0.0


NFL_CONFIG = EloConfig()
CFB_CONFIG = EloConfig(
    hfa=65.0, season_regression=0.50, mov=True, margin_cap=28, fcs_offset=350.0
)


def config_for(sport: str) -> EloConfig:
    return CFB_CONFIG if sport.upper() == SPORT_CFB else NFL_CONFIG


def expected_home(elo_home: float, elo_away: float, config: EloConfig = NFL_CONFIG) -> float:
    """Pre-game home win expectation including home-field advantage."""
    return 1.0 / (1.0 + 10.0 ** (-((elo_home + config.hfa) - elo_away) / config.scale))


def mov_multiplier(margin: float, elo_diff_winner: float, config: EloConfig = CFB_CONFIG) -> float:
    """538-style: log of the capped margin, damped when the winner was favored."""
    capped = min(abs(margin), config.margin_cap)
    return math.log(capped + 1.0) * (2.2 / (elo_diff_winner * 0.001 + 2.2))


def update(
    elo_home: float,
    elo_away: float,
    home_won: float,
    config: EloConfig = NFL_CONFIG,
    margin: float | None = None,
) -> tuple[float, float]:
    """Post-game ratings. `home_won` is 1.0, 0.0, or 0.5 for a tie."""
    exp = expected_home(elo_home, elo_away, config)
    delta = config.k * (home_won - exp)
    if config.mov and margin:
        home_adv = (elo_home + config.hfa) - elo_away
        winner_adv = home_adv if margin > 0 else -home_adv
        delta *= mov_multiplier(margin, winner_adv, config)
    return elo_home + delta, elo_away - delta


def regress_to_mean(elo: float, config: EloConfig = NFL_CONFIG, base: float | None = None) -> float:
    """Between-season carry-forward, toward `base` (default: config base)."""
    anchor = config.base if base is None else base
    return anchor + config.season_regression * (elo - anchor)


@dataclass
class EloBook:
    """Replays games chronologically and tracks each team's current rating."""

    ratings: dict[str, float] = field(default_factory=dict)
    current_season: int | None = None
    config: EloConfig = NFL_CONFIG
    tiers: dict[str, str] = field(default_factory=dict)

    def _anchor(self, team: str) -> float:
        if self.tiers.get(team) == "FCS":
            return self.config.base - self.config.fcs_offset
        return self.config.base

    def _roll_season(self, season: int) -> None:
        if self.current_season is not None and season != self.current_season:
            for team in self.ratings:
                self.ratings[team] = regress_to_mean(
                    self.ratings[team], self.config, self._anchor(team)
                )
        self.current_season = season

    def pre_game(self, season: int, home: str, away: str) -> tuple[float, float]:
        """Ratings entering a game (applies season regression when needed)."""
        self._roll_season(season)
        return (
            self.ratings.get(home, self._anchor(home)),
            self.ratings.get(away, self._anchor(away)),
        )

    def record_result(
        self, season: int, home: str, away: str, home_score: int, away_score: int
    ) -> None:
        elo_home, elo_away = self.pre_game(season, home, away)
        if home_score > away_score:
            result = 1.0
        elif home_score < away_score:
            result = 0.0
        else:
            result = 0.5
        self.ratings[home], self.ratings[away] = update(
            elo_home, elo_away, result, self.config, margin=home_score - away_score
        )
