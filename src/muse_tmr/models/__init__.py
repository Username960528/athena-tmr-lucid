"""REM detection models."""

from muse_tmr.models.heuristic_rem_detector import HeuristicRemConfig, HeuristicRemDetector
from muse_tmr.models.ml_rem_detector import (
    DEFAULT_PERSONAL_REM_FEATURES,
    PersonalRemClassifierConfig,
    PersonalRemModel,
    PersonalRemTrainingSummary,
    train_personal_rem_classifier,
)
from muse_tmr.models.rem_detector import RemPrediction

__all__ = [
    "DEFAULT_PERSONAL_REM_FEATURES",
    "HeuristicRemConfig",
    "HeuristicRemDetector",
    "PersonalRemClassifierConfig",
    "PersonalRemModel",
    "PersonalRemTrainingSummary",
    "RemPrediction",
    "train_personal_rem_classifier",
]
