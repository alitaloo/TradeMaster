# TradeMaster Pro v2.0 - 擴展指南

本文檔說明如何擴展 TradeMaster 系統。

## 添加新指標

### 1. 創建指標文件

在 `indicators/<category>/` 目錄下創建新文件：

```python
# indicators/trend/new_indicator.py

import pandas as pd
from typing import Dict
from core.decorators import indicator
from core.base_classes import BaseIndicator, IndicatorResult


@indicator(
    name="NewIndicator",
    category="trend",
    parameters={
        "period": {"type": int, "default": 14}
    },
    outputs=["value", "signal"],
    tags=["trend", "custom"]
)
class NewIndicator(BaseIndicator):
    """新指標說明"""
    
    def __init__(self, period: int = 14, **kwargs):
        self.period = period
    
    def compute(self, data: pd.DataFrame) -> IndicatorResult:
        self.validate_input(data, ["Close"])
        data = self.handle_missing_data(data)
        
        # 計算邏輯
        value = data["Close"].rolling(self.period).mean()
        
        result_df = pd.DataFrame({"value": value})
        
        return IndicatorResult(
            values=result_df,
            last_value={"value": value.iloc[-1]},
            metadata={"period": self.period}
        )
```

### 2. 指標裝飾器參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | str | 指標名稱 (唯一) |
| `category` | str | 類別 (momentum/trend/volume) |
| `parameters` | dict | 參數定義 |
| `outputs` | list | 輸出欄位 |
| `tags` | list | 標籤列表 |

---

## 添加新策略

### 1. 創建策略文件

在 `strategies/<category>/` 目錄下創建新文件：

```python
# strategies/trend/new_strategy.py

import pandas as pd
from typing import Dict
from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult


@strategy(
    name="NewStrategy",
    type="trend",
    indicators=["SMA", "EMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"],
    parameters={
        "period": {"type": int, "default": 20}
    },
    tags=["trend", "custom"]
)
class NewStrategy(BaseStrategy):
    """新策略說明"""
    
    def __init__(self, period: int = 20, **kwargs):
        self.period = period
    
    def generate_signal(
        self,
        indicator_values: Dict,
        price_data: pd.DataFrame
    ) -> SignalResult:
        # 獲取指標
        sma_data = indicator_values.get("SMA")
        
        # 生成信號
        current_price = price_data["Close"].iloc[-1]
        
        # ... 邏輯實現 ...
        
        return SignalResult(
            signal="LONG",  # 或 SHORT, HOLD
            confidence=0.7,
            price=current_price,
            reason="信號原因說明"
        )
```

### 2. 策略裝飾器參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | str | 策略名稱 |
| `type` | str | 策略類型 |
| `indicators` | list | 依賴的指標 |
| `signals` | list | 輸出信號類型 |
| `market_regimes` | list | 適用的市場環境 |
| `parameters` | dict | 策略參數 |

---

## 添加新風控規則

### 1. 創建風控規則

```python
# risk_rules/new_rule.py

from typing import Dict
from core.decorators import risk_rule
from core.base_classes import BaseRiskRule, RiskCheckResult


@risk_rule(
    name="NewRiskRule",
    type="position_sizing",
    parameters={
        "max_value": {"type": float, "default": 10000}
    },
    tags=["position", "limit"]
)
class NewRiskRule(BaseRiskRule):
    """新風控規則說明"""
    
    def __init__(self, max_value: float = 10000, **kwargs):
        self.max_value = max_value
    
    def check(
        self,
        position: Dict,
        portfolio: Dict = None,
        market_data: Dict = None
    ) -> RiskCheckResult:
        position_value = position.get("value", 0)
        
        if position_value > self.max_value:
            return RiskCheckResult(
                passed=False,
                violations=[{
                    "rule": "new_risk",
                    "message": f"倉位 {position_value} 超過限制 {self.max_value}",
                    "action": "REDUCE",
                    "reduce_amount": position_value - self.max_value
                }],
                message=f"倉位超限"
            )
        
        return RiskCheckResult(passed=True)
```

---

## 添加新 API 端點

### 1. 創建 API Blueprint

```python
# api/new_blueprint.py

from flask import Blueprint, request, jsonify


new_bp = Blueprint('new', __name__, url_prefix='/api/v1')


@new_bp.route('/endpoint', methods=['GET'])
def new_endpoint():
    """新端點說明"""
    return jsonify({"status": "ok", "data": "..."})


@new_bp.route('/action', methods=['POST'])
def new_action():
    """新動作說明"""
    data = request.get_json()
    # 處理邏輯
    return jsonify({"success": True})
```

### 2. 註冊到主程序

在 `api_server.py` 或主入口中：

```python
from api.new_blueprint import new_bp

app.register_blueprint(new_bp)
```

---

## 添加新數據源

### 1. 擴展 DataEngine

```python
# data/new_source.py

import pandas as pd
from typing import Optional


class NewDataSource:
    """新數據源"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
    
    def get_data(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """獲取數據"""
        # 實現數據獲取邏輯
        pass
```

---

## 配置說明

### 配置文件結構

```yaml
# config/settings.yaml

# 交易配置
trading:
  mode: paper  # paper / semi / live
  initial_capital: 100000

# API 配置
api_keys:
  telegram:
    token: "YOUR_BOT_TOKEN"
    chat_id: "YOUR_CHAT_ID"

# 風控配置
risk:
  max_risk_per_trade: 0.01
  max_position_pct: 0.25

# 通知配置
notifications:
  trade_signals: true
  daily_summary: true

# 舆情模組
sentiment:
  news:
    api_key: "YOUR_NEWSAPI_KEY"
```

---

## 命令行使用

```bash
# 列出所有指標
python main.py list indicators

# 列出所有策略
python main.py list strategies

# 執行每日掃描
python main.py scan --strategy RSI_Reversal

# 查看系統狀態
python main.py status

# 執行測試
python main.py test

# 回測
python run_backtest.py --strategy RSI_Reversal --symbol AAPL --period 1y
```

---

## 最佳實踐

1. **保持模組化** - 每個指標/策略/規則應該是獨立的
2. **錯誤處理** - 始終處理可能的異常情況
3. **日誌記錄** - 使用 `logger` 記錄重要信息
4. **參數驗證** - 驗證輸入參數的有效性
5. **單元測試** - 為新功能添加測試
