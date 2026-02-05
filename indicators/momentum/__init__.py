#!/usr/bin/env python3
"""
動量指標 - Momentum Indicators
"""

import pandas as pd
from core.decorators import indicator
from core.base_classes import BaseIndicator, IndicatorResult


@indicator(name="RSI", category="momentum",
    parameters={"period": {"type": int, "default": 14}},
    outputs=["rsi", "signal"], tags=["momentum", "oscillator"])
class RSI(BaseIndicator):
    def compute(self, data):
        self.validate_input(data, ["Close"])
        delta = data["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.period).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return IndicatorResult(
            values={"rsi": rsi},
            last_value={"rsi": rsi.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="Stochastic", category="momentum",
    parameters={"period": {"type": int, "default": 14}},
    outputs=["stoch_k", "stoch_d"], tags=["momentum", "oscillator"])
class Stochastic(BaseIndicator):
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        lowest = data["Low"].rolling(self.period).min()
        highest = data["High"].rolling(self.period).max()
        stoch_k = 100 * (data["Close"] - lowest) / (highest - lowest + 1e-10)
        stoch_d = stoch_k.rolling(3).mean()
        return IndicatorResult(
            values={"stoch_k": stoch_k, "stoch_d": stoch_d},
            last_value={"stoch_k": stoch_k.iloc[-1], "stoch_d": stoch_d.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="WilliamsR", category="momentum",
    parameters={"period": {"type": int, "default": 14}},
    outputs=["williams_r"], tags=["momentum", "oscillator"])
class WilliamsR(BaseIndicator):
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        highest = data["High"].rolling(self.period).max()
        lowest = data["Low"].rolling(self.period).min()
        wr = -100 * (highest - data["Close"]) / (highest - lowest + 1e-10)
        return IndicatorResult(
            values={"williams_r": wr},
            last_value={"williams_r": wr.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="Momentum", category="momentum",
    parameters={"period": {"type": int, "default": 10}},
    outputs=["momentum"], tags=["momentum", "trend"])
class Momentum(BaseIndicator):
    def compute(self, data):
        self.validate_input(data, ["Close"])
        mom = data["Close"] - data["Close"].shift(self.period)
        return IndicatorResult(
            values={"momentum": mom},
            last_value={"momentum": mom.iloc[-1]},
            metadata={"period": self.period}
        )
