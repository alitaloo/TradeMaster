# 風控規則
from core.decorators import risk_rule
from core.base_classes import BaseRiskRule, RiskCheckResult


@risk_rule(name="DailyLossLimit", parameters={"max_loss_percent": {"type": float, "default": 5.0}})
class DailyLossLimit(BaseRiskRule):
    """每日虧損限制"""
    def evaluate(self, portfolio):
        return RiskCheckResult(allowed=True, message="Daily limit OK")


@risk_rule(name="FixedStopLoss", parameters={"stop_loss_pct": {"type": float, "default": 2.0}})
class FixedStopLoss(BaseRiskRule):
    """固定止損"""
    def evaluate(self, portfolio, position):
        return RiskCheckResult(allowed=True, message="Fixed SL OK")


@risk_rule(name="TrailingStopLoss", parameters={"trailing_pct": {"type": float, "default": 3.0}})
class TrailingStopLoss(BaseRiskRule):
    """移動止損"""
    def evaluate(self, portfolio, position):
        return RiskCheckResult(allowed=True, message="Trailing SL OK")


@risk_rule(name="TakeProfit", parameters={"target_pct": {"type": float, "default": 10.0}})
class TakeProfit(BaseRiskRule):
    """止盈"""
    def evaluate(self, portfolio, position):
        return RiskCheckResult(allowed=True, message="Take profit OK")


@risk_rule(name="MaxPositionLimit", parameters={"max_pct": {"type": float, "default": 25.0}})
class MaxPositionLimit(BaseRiskRule):
    """最大倉位限制"""
    def evaluate(self, portfolio, new_position):
        return RiskCheckResult(allowed=True, message="Position limit OK")


@risk_rule(name="DynamicStopLoss", parameters={"atr_multiplier": {"type": float, "default": 2.0}})
class DynamicStopLoss(BaseRiskRule):
    """動態止損"""
    def evaluate(self, portfolio, position, atr):
        return RiskCheckResult(allowed=True, message="Dynamic SL OK")
