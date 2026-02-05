# Plugin base classes

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import json


@dataclass
class IndicatorResult:
    """指標計算結果"""
    values: pd.DataFrame
    last_value: Any
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "last_value": self.last_value,
            "timestamp": datetime.now().isoformat()
        }


class BaseIndicator(ABC):
    """指標基類"""
    
    def __init__(self, **parameters):
        """初始化指標參數"""
        self.parameters = parameters
        # 將參數設置為實例屬性
        for key, value in parameters.items():
            setattr(self, key, value)
    
    @abstractmethod
    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        """計算指標"""
        pass
    
    def validate_input(self, data: pd.DataFrame, required_columns: list) -> bool:
        """驗證輸入數據"""
        for col in required_columns:
            if col not in data.columns:
                raise ValueError(f"Missing required column: {col}")
        return True
    
    def handle_missing_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """處理缺失數據"""
        return data.dropna()
    
    def get_default_parameters(self) -> dict:
        """獲取默認參數"""
        return {}


@dataclass
class SignalResult:
    """策略信號結果"""
    signal: str  # LONG / SHORT / HOLD / CLOSE
    confidence: float  # 0-1
    price: float
    reason: str
    indicators: Dict = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.indicators is None:
            self.indicators = {}
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "signal": self.signal,
            "confidence": self.confidence,
            "price": self.price,
            "reason": self.reason,
            "indicators": self.indicators,
            "timestamp": datetime.now().isoformat()
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class BaseStrategy(ABC):
    """策略基類"""
    
    @abstractmethod
    def generate_signal(
        self, 
        indicator_values: Dict[str, IndicatorResult],
        price_data: pd.DataFrame
    ) -> SignalResult:
        """生成交易信號"""
        pass
    
    def validate_market_regime(
        self, 
        regime: str, 
        supported_regimes: list
    ) -> bool:
        """驗證市場環境"""
        return regime in supported_regimes or not supported_regimes
    
    def calculate_confidence(
        self, 
        factor_scores: Dict[str, float]
    ) -> float:
        """計算信心度"""
        if not factor_scores:
            return 0.0
        
        weights = [0.3, 0.3, 0.2, 0.2]  # 可配置的權重
        scores = list(factor_scores.values())
        
        while len(scores) < len(weights):
            scores.append(0)
        
        return sum(s * w for s, w in zip(scores[:4], weights))


@dataclass
class RiskCheckResult:
    """風控檢查結果"""
    passed: bool
    violations: list = None
    adjusted_position: float = None
    message: str = ""
    
    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class BaseRiskRule(ABC):
    """風控規則基類"""
    
    @abstractmethod
    def check(
        self, 
        position: Dict,
        portfolio: Dict,
        market_data: pd.DataFrame = None
    ) -> RiskCheckResult:
        """檢查風控"""
        pass
    
    def get_parameters(self) -> dict:
        """獲取參數"""
        return {}


@dataclass
class Order:
    """訂單"""
    symbol: str
    side: str  # BUY / SELL
    quantity: int
    order_type: str  # MKT / LMT / STP
    price: float = None
    stop_price: float = None
    time_in_force: str = "GTC"
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "type": self.order_type,
            "price": self.price,
            "stop_price": self.stop_price,
            "tif": self.time_in_force,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class Trade:
    """成交"""
    order: Order
    filled_price: float
    filled_quantity: int
    commission: float = 0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def total_value(self) -> float:
        return self.filled_price * self.filled_quantity
    
    def pnl(
        self, 
        current_price: float = None,
        position_type: str = "LONG"
    ) -> float:
        if current_price is None:
            current_price = self.filled_price
        
        if position_type == "LONG":
            return (current_price - self.filled_price) * self.filled_quantity
        else:
            return (self.filled_price - current_price) * self.filled_quantity


class BaseExecutor(ABC):
    """執行器基類"""
    
    @abstractmethod
    async def connect(self) -> bool:
        """連接"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """斷開"""
        pass
    
    @abstractmethod
    async def place_order(self, order: Order) -> Trade:
        """下單"""
        pass
    
    @abstractmethod
    async def get_positions(self) -> list:
        """獲取持倉"""
        pass
    
    @abstractmethod
    async def get_account_summary(self) -> dict:
        """獲取帳戶"""
        pass


class Result:
    """通用結果"""
    
    def __init__(
        self, 
        success: bool, 
        data: any = None, 
        error: str = None
    ):
        self.success = success
        self.data = data
        self.error = error
    
    @classmethod
    def ok(cls, data=None):
        return cls(True, data=data)
    
    @classmethod
    def fail(cls, error):
        return cls(False, error=error)
    
    def __bool__(self):
        return self.success
