"""Detector config registry — serialize / deserialize PatternDetectors to plain dicts.

Round-trip guarantee: build_detector_from_config(_detector_to_config(det)) produces
a detector with identical .name, .family, and .detect() output.

The config dict is JSON-safe so it can be stored in params_json or passed in LangGraph state.
"""

from __future__ import annotations

import json
from typing import Any


def _detector_to_config(detector: Any) -> dict:
    """Serialize a PatternDetector instance to a JSON-serializable config dict."""
    from atforge.patterns.composition import AndDetector, OrDetector
    from atforge.patterns.pandas_ta import RsiOversoldReclaim, SmaCrossover
    from atforge.patterns.talib_cdl import TalibCdlDetector

    if isinstance(detector, SmaCrossover):
        return {"type": "sma_crossover", "fast": detector._fast, "slow": detector._slow}
    if isinstance(detector, RsiOversoldReclaim):
        return {"type": "rsi_oversold", "period": detector._period, "oversold": detector._oversold}
    if isinstance(detector, TalibCdlDetector):
        return {
            "type": "talib_cdl",
            "cdl_name": detector._cdl_name,
            "direction": detector._direction,
        }
    if isinstance(detector, AndDetector):
        return {
            "type": "and",
            "left": _detector_to_config(detector.left),
            "right": _detector_to_config(detector.right),
        }
    if isinstance(detector, OrDetector):
        return {
            "type": "or",
            "left": _detector_to_config(detector.left),
            "right": _detector_to_config(detector.right),
        }
    raise TypeError(f"unknown detector type: {type(detector).__name__!r}")


def build_detector_from_config(config: dict) -> Any:
    """Deserialize a config dict back into a PatternDetector."""
    from atforge.patterns.composition import AndDetector, OrDetector
    from atforge.patterns.pandas_ta import RsiOversoldReclaim, SmaCrossover
    from atforge.patterns.talib_cdl import TalibCdlDetector

    t = config.get("type")
    if t == "sma_crossover":
        return SmaCrossover(fast=config["fast"], slow=config["slow"])
    if t == "rsi_oversold":
        return RsiOversoldReclaim(period=config["period"], oversold=config["oversold"])
    if t == "talib_cdl":
        return TalibCdlDetector(
            cdl_name=config["cdl_name"],
            direction=config.get("direction", "bullish"),
        )
    if t == "and":
        return AndDetector(
            left=build_detector_from_config(config["left"]),
            right=build_detector_from_config(config["right"]),
        )
    if t == "or":
        return OrDetector(
            left=build_detector_from_config(config["left"]),
            right=build_detector_from_config(config["right"]),
        )
    raise ValueError(f"unknown detector type: {t!r}")


def detector_params_json(detector: Any) -> str:
    """Canonical JSON of detector config — stable key order for UNIQUE(name, params_json) dedup."""
    return json.dumps(_detector_to_config(detector), sort_keys=True, separators=(",", ":"))
