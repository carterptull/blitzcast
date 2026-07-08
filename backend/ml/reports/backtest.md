# Backtest — walk-forward by season

Model trains only on seasons before each holdout season; the market
baseline uses de-vigged closing moneyline probabilities (nflverse).

| Season | Games | Model Brier | Vegas Brier | Model LogLoss | Vegas LogLoss | Model Acc | Vegas Acc | Model AUC | Vegas AUC |
|---|---|---|---|---|---|---|---|---|---|
| 2023 | 285 | 0.2405 | 0.2186 | 0.6817 | 0.6270 | 0.604 | 0.677 | 0.637 | 0.691 |
| 2024 | 285 | 0.2100 | 0.2010 | 0.6102 | 0.5892 | 0.702 | 0.705 | 0.750 | 0.757 |
| 2025 | 285 | 0.2191 | 0.2104 | 0.6278 | 0.6059 | 0.663 | 0.663 | 0.701 | 0.725 |
| **All** | 855 | **0.2232** | **0.2100** | 0.6399 | 0.6074 | 0.656 | 0.682 | 0.690 | 0.725 |

![Calibration](./calibration.png)
