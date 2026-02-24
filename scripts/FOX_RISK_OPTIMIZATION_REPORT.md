# Fox Analysis 风控优化建议报告

## 📋 现有风控参数分析

### 当前 RISK_PARAMS 配置
```python
RISK_PARAMS = {
    'VIX_THRESHOLD': 30.0,         # VIX 阈值 (固定)
    'MARKET_DROP_THRESHOLD': -3.0,  # 市场跌幅阈值
    'NEWS_WEIGHT_THRESHOLD': 5,     # 新闻权重阈值
    'MIN_CONFIDENCE': 0.6,          # 最低信心度
    'HIGH_CONFIDENCE': 0.8,         # 高信心度
    'STOP_LOSS_PCT': 5.0,           # 止损百分比 (固定)
}
```

### 现有信心度计算逻辑 (`calculate_confidence`)
| 因素 | 条件 | 信心度调整 |
|------|------|-----------|
| **持仓回报率** | > 10% | +0.2 |
| | > 5% | +0.1 |
| | > 0% | +0.05 |
| | -5% ~ 0% | -0.1 |
| | < -5% | -0.2 |
| **新闻权重** | = 0 (无新闻) | +0.1 |
| | < 3 | +0.05 |
| | > 7 | -0.2 |
| **新闻情感** | 正面 > 负面 | +0.1 |
| | 负面 > 正面 | -0.1 |
| **VIX** | < 15 | +0.2 |
| | < 20 | +0.1 |
| | > 25 | -0.1 |
| | > 30 | -0.2 |
| **市场涨跌** | > 1% | +0.1 |
| | < -2% | -0.15 |

---

## 🚨 发现的问题

### 问题 1: 只有止损，缺少止盈机制
- **现状**: `STOP_LOSS_PCT = 5.0` (固定 5%)
- **问题**: 没有 take-profit 逻辑，无法锁定盈利

### 问题 2: 固定 10% 仓位
- **现状**: 在 `create_signal` 中硬编码 `quantity = int(total_capital * 0.1 / current_price)`
- **问题**: 未根据市场环境、信心度、波动率动态调整

### 问题 3: VIX 阈值固定
- **现状**: `VIX_THRESHOLD = 30.0` 全天使用
- **问题**: 美股不同时段波动特性不同:
  - 盘前/盘后: 波动较大，VIX 通常更高
  - 盘中: 相对稳定
  - 开盘/收盘: 波动剧烈

---

## ✅ 风控优化方案

### 1. 加入 Take-Profit 逻辑

```python
# 建议新增参数
'TAKE_PROFIT_PCT': 10.0,           # 止盈百分比 (建议 8-12%)
'TAKE_PROFIT_TRAILING': True,      # 启用移动止盈
'TRAILING_STOP_PCT': 3.0,          # 移动止损距离

# 止盈策略
def calculate_take_profit(entry_price: float, return_pct: float, 
                          high_price: float = None) -> Dict:
    """
    计算止盈价格
    - 固定止盈: 达到目标收益率止盈
    - 移动止盈: 从高点回撤指定比例止盈
    """
    tp_price = entry_price * (1 + RISK_PARAMS['TAKE_PROFIT_PCT'] / 100)
    
    # 如果有高点，使用移动止盈
    if high_price and RISK_PARAMS.get('TAKE_PROFIT_TRAILING'):
        trailing_trigger = high_price * (1 - RISK_PARAMS['TRAILING_STOP_PCT'] / 100)
        # 取固定止盈和移动止盈中较保守的
        return min(tp_price, trailing_trigger)
    
    return tp_price
```

### 2. 动态仓位计算公式

```python
def calculate_position_size(
    total_capital: float,
    confidence: float,
    vix: float,
    market_drop: float,
    stop_loss_pct: float = 5.0
) -> float:
    """
    动态仓位计算
    
    公式: base_position * confidence_factor * market_factor * volatility_factor
    
    信心度因子: 0.5 ~ 1.5
    市场因子: 0.5 ~ 1.2
    波动率因子: 0.5 ~ 1.0
    """
    BASE_POSITION = 0.10  # 基础 10%
    
    # 1. 信心度因子
    confidence_factor = 0.5 + confidence  # 0.6 ~ 1.45
    
    # 2. 市场环境因子
    if market_drop > 1:
        market_factor = 1.2  # 市场上涨可加仓
    elif market_drop > -1:
        market_factor = 1.0  # 中性
    elif market_drop > -3:
        market_factor = 0.7  # 市场下跌减仓
    else:
        market_factor = 0.5  # 大跌回避
    
    # 3. 波动率因子 (VIX)
    if vix < 15:
        volatility_factor = 1.0  # 低波动正常仓位
    elif vix < 20:
        volatility_factor = 0.9
    elif vix < 25:
        volatility_factor = 0.7
    elif vix < 30:
        volatility_factor = 0.5
    else:
        volatility_factor = 0.3  # 高波动大幅减仓
    
    # 计算最终仓位
    position = BASE_POSITION * confidence_factor * market_factor * volatility_factor
    
    # 限制在 2% ~ 20% 之间
    position = max(0.02, min(0.20, position))
    
    return round(position, 3)
```

### 3. 不同时段的 VIX 阈值建议

```python
# 建议新增参数组
VIX_PARAMS = {
    'pre_market': {      # 盘前 (4:00-9:30 EST)
        'threshold': 35.0,    # 允许更高 VIX
        'position_mult': 0.5  # 仓位减半
    },
    'regular': {         # 盘中 (9:30-16:00 EST)
        'threshold': 30.0,    # 标准阈值
        'position_mult': 1.0
    },
    'after_hours': {    # 盘后 (16:00-20:00 EST)
        'threshold': 35.0,    # 允许更高 VIX
        'position_mult': 0.5
    },
    'close': {          # 收盘附近 (15:45-16:00 EST)
        'threshold': 25.0,    # 更严格
        'position_mult': 0.7
    }
}

def get_current_period() -> str:
    """判断当前属于哪个时段"""
    now = datetime.now()
    # 转换为 EST (UTC-5 或 UTC-4)
    est_hour = (now.hour - 5) % 24
    
    if 4 <= est_hour < 9:
        return 'pre_market'
    elif 9 <= est_hour < 15:
        return 'regular'
    elif 15 <= est_hour < 16:
        return 'close'
    elif 16 <= est_hour < 20:
        return 'after_hours'
    else:
        return 'pre_market'  # 非交易时段

def get_vix_threshold() -> float:
    """获取当前时段的 VIX 阈值"""
    period = get_current_period()
    return VIX_PARAMS[period]['threshold']
```

---

## 📊 推荐的新 RISK_PARAMS 配置

```python
RISK_PARAMS = {
    # 现有参数
    'VIX_THRESHOLD': 30.0,         # 基础值 (会被时段覆盖)
    'MARKET_DROP_THRESHOLD': -3.0,
    'NEWS_WEIGHT_THRESHOLD': 5,
    'MIN_CONFIDENCE': 0.6,
    'HIGH_CONFIDENCE': 0.8,
    'STOP_LOSS_PCT': 5.0,
    
    # 新增参数 - 止盈
    'TAKE_PROFIT_PCT': 10.0,        # 止盈目标
    'TAKE_PROFIT_TRAILING': True,   # 启用移动止盈
    'TRAILING_STOP_PCT': 3.0,       # 移动止损幅度
    
    # 仓位控制
    'MIN_POSITION': 0.02,           # 最小仓位 2%
    'MAX_POSITION': 0.20,           # 最大仓位 20%
    
    # 波动率时段参数
    'VIX_PERIOD_PRE_MARKET': 35.0,
    'VIX_PERIOD_REGULAR': 30.0,
    'VIX_PERIOD_AFTER_HOURS': 35.0,
    'VIX_PERIOD_CLOSE': 25.0,
}

# 信心度增强 (可选)
CONFIDENCE_BOOST = {
    'TRIPLE_RESONANCE': 0.15,        # 三周期共振加成
    'HIGH_CONFIDENCE_MIN': 0.75,     # 高信心最低门槛
    'LOW_CONFIDENCE_MAX': 0.45,      # 低信心最高门槛
}
```

---

## 🎯 实施优先级

| 优先级 | 项目 | 复杂度 | 预期收益 |
|--------|------|--------|----------|
| 1 | 动态 VIX 阈值 | 低 | 高 |
| 2 | 动态仓位计算 | 中 | 高 |
| 3 | 止盈机制 | 中 | 中 |
| 4 | 信心度优化 | 低 | 中 |

---

## 📝 总结

1. **止盈**: 建议设置 8-12% 固定止盈 + 3% 移动止盈
2. **仓位**: 建议 2%-20% 动态范围，结合信心度、市场环境、VIX 综合计算
3. **VIX 阈值**: 建议分时段设置 (盘前/盘后 35, 盘中 30, 收盘 25)

这套优化方案可在保持现有风控框架的基础上，大幅提升风险收益比。
