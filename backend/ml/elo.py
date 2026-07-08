"""Standard NFL Elo rating implementation.

Constants per the implementation plan: K=20, home-field advantage of 55 Elo
points in the expectation, logistic scale 400, base rating 1500, and 0.75
regression toward the mean between seasons.
"""

from dataclasses import dataclass, field

K = 20.0
HFA = 55.0
SCALE = 400.0
BASE = 1500.0
SEASON_REGRESSION = 0.75


def expected_home(elo_home: float, elo_away: float) -> float:
    """Pre-game home win expectation including home-field advantage."""
    return 1.0 / (1.0 + 10.0 ** (-((elo_home + HFA) - elo_away) / SCALE))


def update(elo_home: float, elo_away: float, home_won: float) -> tuple[float, float]:
    """Post-game ratings. `home_won` is 1.0, 0.0, or 0.5 for a tie."""
    exp = expected_home(elo_home, elo_away)
    delta = K * (home_won - exp)
    return elo_home + delta, elo_away - delta


def regress_to_mean(elo: float) -> float:
    """Between-season carry-forward."""
    return BASE + SEASON_REGRESSION * (elo - BASE)


@dataclass
class EloBook:
    """Replays games chronologically and tracks each team's current rating."""

    ratings: dict[str, float] = field(default_factory=dict)
    current_season: int | None = None

    def _roll_season(self, season: int) -> None:
        if self.current_season is not None and season != self.current_season:
            for team in self.ratings:
                self.ratings[team] = regress_to_mean(self.ratings[team])
        self.current_season = season

    def pre_game(self, season: int, home: str, away: str) -> tuple[float, float]:
        """Ratings entering a game (applies season regression when needed)."""
        self._roll_season(season)
        return self.ratings.get(home, BASE), self.ratings.get(away, BASE)

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
        self.ratings[home], self.ratings[away] = update(elo_home, elo_away, result)
