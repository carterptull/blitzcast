"""Thin wrapper around the nflverse data source (nflreadpy).

Keeps the source library swappable: everything downstream consumes pandas
DataFrames with nflverse column names.
"""

import nflreadpy
import pandas as pd


def load_schedules(seasons: list[int]) -> pd.DataFrame:
    return nflreadpy.load_schedules(seasons).to_pandas()


def load_pbp(seasons: list[int]) -> pd.DataFrame:
    return nflreadpy.load_pbp(seasons).to_pandas()


def load_injuries(seasons: list[int]) -> pd.DataFrame:
    return nflreadpy.load_injuries(seasons).to_pandas()
