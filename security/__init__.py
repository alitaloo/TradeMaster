# Security module - Safety gateway and circuit breaker

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """執行模式"""
    PAPER = "paper"      # 模擬交易
    SEMI_LIVE = "semi"   # 半實盤（需確認）
    LIVE = "live"        # 實盤


class SafetyLevel(Enum):
    """安全級別"""
    CONSERVATIVE = "conservative"  # 保守
    MODERATE = "moderate"          # 中等
    AGGRESSIVE = aggressive        # 激進


@dataclass
class SafetyConfig:
    """安全配置"""
    mode: ExecutionMode = ExecutionMode.PAPER
    safety_level: SafetyLevel = SafetyLevel.MODERATE
    
    # 金額限制
    max_order_value: float = 10000
    max_daily_loss_pct: float = 0.05
    max_position_pct: float = 0.25
    
    # 頻率限制
    max_orders_per_day: int = 50
    min_order_interval_seconds: int = 60
    
    # 確認閾值
    require_confirmation_above: float = 1000
    confirmation_timeout_seconds: int = 300
    
    # 熔斷
    circuit_breaker_enabled: bool = True
    max_consecutive_losses: int = 5
    max_drawdown_pct: float = 0.10
    
    # 通知
    notify_on_order: bool = True
    notify_on_block: bool = True


@dataclass
class DailyStats:
    """當日統計"""
    orders_placed: int = 0
    orders_value: float = 0.0
    daily_pnl: float = 0.0
    trades: List[Dict] = field(default_factory=list)
    last_order_time: datetime = None
    
    def to_dict(self) -> dict:
        return {
            "orders_placed": self.orders_placed,
            "orders_value": self.orders_value,
            "daily_pnl": self.daily_pnl,
            "trade_count": len(self.trades)
        }


class SafetyGateway:
    """安全閘道 - 所有交易的最後一道防線"""
    
    def __init__(self, config: SafetyConfig = None):
        self.config = config or SafetyConfig()
        self.daily_stats = DailyStats()
        self.circuit_breaker_triggered = False
        self.circuit_breaker_time: datetime = None
        self.pending_confirmations: Dict[str, dict] = {}
    
    def pre_execute_check(self, order: dict) -> dict:
        """
        執行前檢查
        返回: {"status": "APPROVED"|"BLOCKED"|"PENDING_CONFIRMATION", "reason": str}
        """
        # 1. 熔斷檢查
        if self.circuit_breaker_triggered:
            return {
                "status": "BLOCKED",
                "reason": "熔斷已觸發，請聯繫管理員",
                "code": "CIRCUIT_BREAKER"
            }
        
        # 2. 模式檢查
        if self.config.mode == ExecutionMode.PAPER:
            order["mode"] = "PAPER"
            return {"status": "APPROVED", "reason": "模擬交易模式"}
        
        # 3. 金額檢查
        order_value = order.get("quantity", 0) * order.get("price", 0)
        if order_value > self.config.max_order_value:
            return {
                "status": "BLOCKED",
                "reason": f"訂單金額 ${order_value:,.2f} 超過限制 ${self.config.max_order_value:,.2f}",
                "code": "MAX_ORDER_VALUE"
            }
        
        # 4. 頻率檢查
        if self.daily_stats.orders_placed >= self.config.max_orders_per_day:
            return {
                "status": "BLOCKED",
                "reason": f"今日訂單數 {self.daily_stats.orders_placed} 已達上限",
                "code": "MAX_DAILY_ORDERS"
            }
        
        # 5. 最小間隔檢查
        if self.daily_stats.last_order_time:
            elapsed = (datetime.now() - self.daily_stats.last_order_time).seconds
            if elapsed < self.config.min_order_interval_seconds:
                return {
                    "status": "BLOCKED",
                    "reason": f"距離上次訂單僅 {elapsed} 秒，需間隔 {self.config.min_order_interval_seconds} 秒",
                    "code": "MIN_INTERVAL"
                }
        
        # 6. 大額訂單確認
        if (
            self.config.mode != ExecutionMode.PAPER
            and order_value > self.config.require_confirmation_above
        ):
            confirmation_id = f"confirm_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            self.pending_confirmations[confirmation_id] = {
                "order": order,
                "created_at": datetime.now(),
                "timeout": self.config.confirmation_timeout_seconds
            }
            
            return {
                "status": "PENDING_CONFIRMATION",
                "reason": f"大額訂單需確認",
                "confirmation_id": confirmation_id,
                "order_details": {
                    "symbol": order.get("symbol"),
                    "side": order.get("side"),
                    "quantity": order.get("quantity"),
                    "price": order.get("price"),
                    "value": order_value
                },
                "timeout_seconds": self.config.confirmation_timeout_seconds
            }
        
        return {"status": "APPROVED", "reason": "通過所有檢查"}
    
    def post_execute_update(self, trade_result: dict):
        """執行後更新統計"""
        self.daily_stats.orders_placed += 1
        self.daily_stats.orders_value += trade_result.get("value", 0)
        self.daily_stats.daily_pnl += trade_result.get("pnl", 0)
        self.daily_stats.trades.append(trade_result)
        self.daily_stats.last_order_time = datetime.now()
        
        # 檢查是否觸發熔斷
        self._check_circuit_breaker()
    
    def confirm_order(self, confirmation_id: str) -> dict:
        """確認訂單"""
        if confirmation_id not in self.pending_confirmations:
            return {"status": "ERROR", "reason": "確認 ID 不存在或已過期"}
        
        pending = self.pending_confirmations[confirmation_id]
        order = pending["order"]
        
        # 檢查是否超時
        elapsed = (datetime.now() - pending["created_at"]).seconds
        if elapsed > pending["timeout"]:
            del self.pending_confirmations[confirmation_id]
            return {"status": "ERROR", "reason": "確認超時"}
        
        del self.pending_confirmations[confirmation_id]
        
        return {
            "status": "APPROVED",
            "reason": "訂單已確認",
            "order": order
        }
    
    def cancel_confirmation(self, confirmation_id: str) -> dict:
        """取消確認"""
        if confirmation_id in self.pending_confirmations:
            del self.pending_confirmations[confirmation_id]
            return {"status": "CANCELLED", "reason": "確認已取消"}
        return {"status": "ERROR", "reason": "確認 ID 不存在"}
    
    def reset_daily_stats(self):
        """重置每日統計"""
        self.daily_stats = DailyStats()
        logger.info("Daily stats reset")
    
    def _check_circuit_breaker(self):
        """檢查是否觸發熔斷"""
        if not self.config.circuit_breaker_enabled:
            return
        
        reasons = []
        
        # 1. 虧損超過限制
        if self.daily_stats.daily_pnl < -(
            self.config.max_daily_loss_pct * self._get_portfolio_value()
        ):
            reasons.append(f"當日虧損 ${abs(self.daily_stats.daily_pnl):,.2f}")
        
        # 2. 連續虧損
        consecutive_losses = self._count_consecutive_losses()
        if consecutive_losses >= self.config.max_consecutive_losses:
            reasons.append(f"連續 {consecutive_losses} 筆虧損")
        
        # 3. 總回撤
        current_value = self._get_portfolio_value()
        peak_value = self._get_peak_value()
        drawdown = (peak_value - current_value) / peak_value if peak_value > 0 else 0
        
        if drawdown >= self.config.max_drawdown_pct:
            reasons.append(f"回撤 {drawdown:.1%}")
        
        if reasons:
            self.circuit_breaker_triggered = True
            self.circuit_breaker_time = datetime.now()
            logger.error(f"CIRCUIT BREAKER TRIGGERED: {', '.join(reasons)}")
            
            # 記錄觸發原因
            self._log_circuit_breaker(reasons)
    
    def _count_consecutive_losses(self) -> int:
        """計算連續虧損"""
        losses = 0
        for trade in reversed(self.daily_stats.trades):
            if trade.get("pnl", 0) < 0:
                losses += 1
            else:
                break
        return losses
    
    def _get_portfolio_value(self) -> float:
        """獲取投資組合價值"""
        # 從持倉計算
        return 100000  # 簡化，實際應從 portfolio 獲取
    
    def _get_peak_value(self) -> float:
        """獲取峰值"""
        return 100000  # 簡化，實際應追蹤
    
    def _log_circuit_breaker(self, reasons: List[str]):
        """記錄熔斷"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "triggered_by": reasons,
            "daily_stats": self.daily_stats.to_dict()
        }
        
        logger.error(f"CIRCUIT BREAKER: {json.dumps(log_entry)}")
    
    def get_safety_status(self) -> dict:
        """獲取安全狀態"""
        return {
            "mode": self.config.mode.value,
            "circuit_breaker": self.circuit_breaker_triggered,
            "daily_stats": self.daily_stats.to_dict(),
            "pending_confirmations": len(self.pending_confirmations),
            "safety_level": self.config.safety_level.value
        }


class SecurityManager:
    """安全管理器"""
    
    def __init__(self):
        self.api_keys_encrypted = {}
        self.sensitive_data = []
    
    def encrypt_api_key(self, key: str, service: str) -> str:
        """加密 API Key"""
        # 簡化實現，實際應使用 proper 加密
        import base64
        encoded = base64.b64encode(key.encode()).decode()
        self.api_keys_encrypted[service] = encoded
        return encoded
    
    def decrypt_api_key(self, service: str) -> Optional[str]:
        """解密 API Key"""
        import base64
        encoded = self.api_keys_encrypted.get(service)
        if encoded:
            return base64.b64decode(encoded.encode()).decode()
        return None
    
    def sanitize_order_for_log(self, order: dict) -> dict:
        """清理訂單日誌（隱藏敏感信息）"""
        sanitized = order.copy()
        
        # 隱藏 API key
        if "api_key" in sanitized:
            sanitized["api_key"] = "***"
        
        # 隱藏密碼
        if "password" in sanitized:
            sanitized["password"] = "***"
        
        return sanitized
    
    def validate_order_permissions(self, order: dict, permissions: List[str]) -> bool:
        """驗證訂單權限"""
        # 檢查訂單類型是否在允許列表中
        order_type = order.get("type", "MKT")
        return order_type in permissions
