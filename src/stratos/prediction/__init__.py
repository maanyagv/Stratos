"""Prediction and backtesting subsystem for STRATOS.

Exports schedule detection, leakage-free feature engineering, calibrated forecasting models,
and chronological backtesting tools.
"""

from stratos.prediction.backtesting import BacktestResult, ChronologicalBacktester
from stratos.prediction.features import (
    PREDICTION_STAGES,
    FeatureExtractor,
    FeatureVector,
)
from stratos.prediction.models import (
    ForecastReport,
    HistoricalPaceBaseline,
    StratosRaceForecaster,
)
from stratos.prediction.schedule import NextEventDetector, NextEventInfo

__all__ = [
    "PREDICTION_STAGES",
    "BacktestResult",
    "ChronologicalBacktester",
    "FeatureExtractor",
    "FeatureVector",
    "ForecastReport",
    "HistoricalPaceBaseline",
    "NextEventDetector",
    "NextEventInfo",
    "StratosRaceForecaster",
]
