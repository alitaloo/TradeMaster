"""
高夏普比率策略模組
目標：Sharpe > 1.5, Return > 20%, MaxDD < 20%

基於量化機構常用的高效策略：
1. Enhanced Momentum - 多週期動量 + 波動率調整
2. Mean Reversion RSI - RSI 超賣 + 確認訊號
3. Trend Filtered Breakout - 趨勢濾網 + 突破交易

Author: TradeMaster Pro
Date: 2026-02-07
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from backtest import PositionType, BacktestResult, BacktestEngine


class SignalResult:
    """訊號結果"""
    def __init__(self, signal: str, confidence: float = 0.5, price: float = 0.0, 
                 reason: str = "", metadata: Dict = None):
        self.signal = signal  # "LONG", "SHORT", "HOLD"
        self.confidence = confidence
        self.price = price
        self.reason = reason
        self.metadata = metadata or {}


class BaseStrategy:
    """策略基類"""
    def __init__(self, **kwargs):
        pass
    
    def generate_signal(self, ind: dict, data: pd.DataFrame) -> SignalResult:
        return SignalResult(signal="HOLD", confidence=0.0, reason="Base strategy")


# ============================================================================
# 策略 1: Enhanced Momentum Strategy (增強動量策略)
# ============================================================================
class EnhancedMomentum(BaseStrategy):
    """
    增強動量策略
    
    核心理念：
    - 多時間框架確認（避免假突破）
    - 波動率調整倉位（風險控制）
    - 相對強度篩選（只做強勢標的）
    
    進場條件：
    1. 價格 > 50日均線 (確認趨勢向上)
    2. 20日 ROC > 0 (短期動量為正)
    3. RSI > 50 但 < 70 (偏多但未超買)
    4. ATR 波動率處於中低位 (避免高波動時期)
    
    出場條件：
    1. 價格跌破 20日均線
    2. RSI < 30
    3. 止損 8%
    4. 止盈 20%
    """
    
    def __init__(self,
                 # 趨勢參數
                 sma_short: int = 20,
                 sma_long: int = 50,
                 # 動量參數
                 roc_period: int = 20,
                 roc_threshold: float = 3.0,
                 # RSI 參數
                 rsi_period: int = 14,
                 rsi_oversold: float = 30,
                 rsi_overbought: float = 70,
                 # 波動率參數
                 atr_period: int = 14,
                 atr_percentile_window: int = 50,
                 atr_volatility_threshold: float = 0.5,
                 # 風控參數
                 stop_loss: float = 0.08,
                 take_profit: float = 0.20,
                 max_holding_days: int = 30):
        
        self.sma_short = sma_short
        self.sma_long = sma_long
        self.roc_period = roc_period
        self.roc_threshold = roc_threshold
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_period = atr_period
        self.atr_percentile_window = atr_percentile_window
        self.atr_volatility_threshold = atr_volatility_threshold
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame) -> SignalResult:
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        current_price = close.iloc[-1]
        
        # 計算指標
        sma_short = close.rolling(self.sma_short).mean()
        sma_long = close.rolling(self.sma_long).mean()
        roc = ((close - close.shift(self.roc_period)) / close.shift(self.roc_period)) * 100
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        
        # ATR 波動率
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean()
        atr_percentile = (atr.rolling(self.atr_percentile_window).rank(pct=True).iloc[-1] 
                         if len(atr) >= self.atr_percentile_window else 0.5)
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            # 出場訊號
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
            
            # 移動止損
            atr_val = atr.iloc[-1] if len(atr) > 0 else current_price * 0.02
            trailing_stop = current_price - atr_val * 2
            if current_price < trailing_stop:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason="Trailing stop hit", metadata={"type": "trailing_stop"})
        
        # 檢查數據是否足夠
        if len(close) < max(self.sma_long, self.roc_period, self.rsi_period) + 5:
            return SignalResult(signal="HOLD", confidence=0.2, price=current_price, 
                               reason="Insufficient data")
        
        # 進場條件
        trend_up = current_price > sma_long.iloc[-1] and sma_short.iloc[-1] > sma_long.iloc[-1]
        momentum_positive = roc.iloc[-1] > self.roc_threshold
        rsi_ok = self.rsi_oversold < rsi_val < self.rsi_overbought
        volatility_ok = atr_percentile < self.atr_volatility_threshold
        
        if trend_up and momentum_positive and rsi_ok and volatility_ok:
            confidence = 0.6 + (rsi_val - self.rsi_oversold) * 0.01 + min(roc.iloc[-1] * 0.02, 0.15)
            confidence = min(confidence, 0.85)
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"Momentum LONG (ROC={roc.iloc[-1]:.1f}%, RSI={rsi_val:.1f})",
                metadata={
                    "roc": roc.iloc[-1],
                    "rsi": rsi_val,
                    "atr_percentile": atr_percentile,
                    "type": "bullish_momentum"
                }
            )
        
        # 反向條件做空
        trend_down = current_price < sma_long.iloc[-1] and sma_short.iloc[-1] < sma_long.iloc[-1]
        momentum_negative = roc.iloc[-1] < -self.roc_threshold
        rsi_bearish = rsi_val < 100 - self.rsi_overbought
        
        if trend_down and momentum_negative and rsi_bearish:
            confidence = 0.6 + abs(roc.iloc[-1]) * 0.02 + (100 - rsi_val) * 0.01
            confidence = min(confidence, 0.85)
            return SignalResult(
                signal="SHORT",
                confidence=confidence,
                price=current_price,
                reason=f"Momentum SHORT (ROC={roc.iloc[-1]:.1f}%, RSI={rsi_val:.1f})",
                metadata={
                    "roc": roc.iloc[-1],
                    "rsi": rsi_val,
                    "type": "bearish_momentum"
                }
            )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略 2: Mean Reversion RSI (均值回歸 RSI)
# ============================================================================
class MeanReversionRSI(BaseStrategy):
    """
    均值回歸 RSI 策略
    
    核心理念：
    - RSI 超賣時買入，反彈後獲利了結
    - 多重確認避免抄底失敗
    - 嚴格止損控制風險
    
    進場條件：
    1. RSI < 25 (深度超賣)
    2. 價格接近 50日均線支撐 (確認估值合理)
    3. 波動率處於高位後收斂 (VIX 反轉)
    4. 近期有支撐測試
    
    出場條件：
    1. RSI > 55 (超買區域)
    2. 止損 5%
    3. 止盈 10%
    4. 時間退出 15天
    """
    
    def __init__(self,
                 # RSI 參數
                 rsi_period: int = 14,
                 rsi_oversold: float = 25,
                 rsi_exit: float = 55,
                 # 均線參數
                 sma_period: int = 50,
                 price_vs_sma_max: float = 0.10,
                 # 波動率參數
                 hv_period: int = 20,
                 hv_lookback: int = 50,
                 hv_percentile_threshold: float = 0.7,
                 # 風控參數
                 stop_loss: float = 0.05,
                 take_profit: float = 0.10,
                 max_holding_days: int = 15):
        
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_exit = rsi_exit
        self.sma_period = sma_period
        self.price_vs_sma_max = price_vs_sma_max
        self.hv_period = hv_period
        self.hv_lookback = hv_lookback
        self.hv_percentile_threshold = hv_percentile_threshold
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame) -> SignalResult:
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        current_price = close.iloc[-1]
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        
        # 均線
        sma = close.rolling(self.sma_period).mean()
        sma_val = sma.iloc[-1] if len(sma) > 0 else current_price
        price_vs_sma = (current_price - sma_val) / sma_val
        
        # 歷史波動率
        log_returns = np.log(close / close.shift(1))
        hv = log_returns.rolling(window=self.hv_period).std() * np.sqrt(252)
        hv_percentile = (hv.rolling(self.hv_lookback).rank(pct=True).iloc[-1]
                        if len(hv) >= self.hv_lookback else 0.5)
        
        # HV 正在下降（波動率收斂）
        hv_change = (hv.iloc[-1] - hv.iloc[-5]) / hv.iloc[-5] if len(hv) >= 5 else 0
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
            
            # RSI 反轉訊號
            prev_rsi = rsi.iloc[-5] if len(rsi) >= 5 else rsi_val
            if rsi_val > self.rsi_exit and prev_rsi <= self.rsi_exit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"RSI reversal (RSI={rsi_val:.1f})", metadata={"type": "rsi_reversal"})
        
        # 檢查數據
        if len(close) < max(self.rsi_period, self.sma_period) + 10:
            return SignalResult(signal="HOLD", confidence=0.2, price=current_price,
                               reason="Insufficient data")
        
        # 進場條件
        oversold = rsi_val < self.rsi_oversold
        near_sma = price_vs_sma < self.price_vs_sma_max and price_vs_sma > -0.15
        hv_high = hv_percentile > self.hv_percentile_threshold
        hv_compressing = hv_change < -0.05
        
        if oversold and near_sma and hv_high:
            confidence = 0.65 + (self.rsi_oversold - rsi_val) * 0.03
            if hv_compressing:
                confidence += 0.1
            confidence = min(confidence, 0.85)
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"RSI Mean Reversion (RSI={rsi_val:.1f}, HV%={hv_percentile:.1f})",
                metadata={
                    "rsi": rsi_val,
                    "hv_percentile": hv_percentile,
                    "price_vs_sma": price_vs_sma,
                    "type": "mean_reversion"
                }
            )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略 3: Trend Filtered Breakout (趨勢濾網突破)
# ============================================================================
class TrendFilteredBreakout(BaseStrategy):
    """
    趨勢濾網突破策略
    
    核心理念：
    - 只在確認的趨勢中交易突破
    - ADX 確認趨勢強度
    - 多重時間框架驗證
    
    進場條件：
    1. ADX > 25 (確認趨勢存在)
    2. +DI > -DI (上升趨勢)
    3. 價格突破 20日高點
    4. 成交量確認 (> 20日均值)
    
    出場條件：
    1. 價格跌破 10日低點
    2. ADX < 20 (趨勢消失)
    3. 止損 6%
    4. 止盈 15%
    """
    
    def __init__(self,
                 # 突破參數
                 breakout_period: int = 20,
                 # ADX 參數
                 adx_period: int = 14,
                 adx_threshold: float = 25,
                 # 成交量參數
                 volume_period: int = 20,
                 volume_multiplier: float = 1.2,
                 # 風控參數
                 stop_loss: float = 0.06,
                 take_profit: float = 0.15,
                 max_holding_days: int = 25):
        
        self.breakout_period = breakout_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.volume_period = volume_period
        self.volume_multiplier = volume_multiplier
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame) -> SignalResult:
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        volume = data.get("Volume", pd.Series([1000000] * len(close)))
        current_price = close.iloc[-1]
        
        # ADX
        period = self.adx_period
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        atr = (high - low).rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(window=period).mean()
        
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        plus_di_val = plus_di.iloc[-1] if len(plus_di) > 0 else 20
        minus_di_val = minus_di.iloc[-1] if len(minus_di) > 0 else 20
        
        # 突破高點
        rolling_high = high.rolling(self.breakout_period).max()
        prev_high = rolling_high.iloc[-2]
        curr_high = rolling_high.iloc[-1]
        
        # 突破低點
        rolling_low = low.rolling(self.breakout_period // 2).min()
        prev_low = rolling_low.iloc[-2]
        
        # 成交量
        volume_ma = volume.rolling(self.volume_period).mean()
        volume_ratio = volume.iloc[-1] / volume_ma.iloc[-1] if len(volume_ma) > 0 else 1.0
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
            
            # 趨勢結束訊號
            if adx_val < self.adx_threshold - 5:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason="ADX trend weakness", metadata={"type": "trend_weakness"})
        
        # 檢查數據
        if len(close) < max(self.breakout_period, self.adx_period, self.volume_period) + 5:
            return SignalResult(signal="HOLD", confidence=0.2, price=current_price,
                               reason="Insufficient data")
        
        # 進場條件 - 做多突破
        trend_strong = adx_val > self.adx_threshold
        uptrend = plus_di_val > minus_di_val
        breakout = prev_high < curr_high and close.iloc[-1] >= curr_high
        volume_confirm = volume_ratio > self.volume_multiplier
        
        if trend_strong and uptrend and breakout and volume_confirm:
            confidence = 0.65 + (adx_val - self.adx_threshold) * 0.02
            confidence = min(confidence, 0.85)
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"Trend Breakout (ADX={adx_val:.1f}, V={volume_ratio:.1f}x)",
                metadata={
                    "adx": adx_val,
                    "plus_di": plus_di_val,
                    "minus_di": minus_di_val,
                    "volume_ratio": volume_ratio,
                    "type": "breakout"
                }
            )
        
        # 做空條件
        downtrend = minus_di_val > plus_di_val
        breakdown = prev_low > rolling_low.iloc[-1] and close.iloc[-1] <= rolling_low.iloc[-1]
        
        if trend_strong and downtrend and breakdown and volume_confirm:
            confidence = 0.65 + (adx_val - self.adx_threshold) * 0.02
            confidence = min(confidence, 0.85)
            return SignalResult(
                signal="SHORT",
                confidence=confidence,
                price=current_price,
                reason=f"Bearish Breakout (ADX={adx_val:.1f})",
                metadata={
                    "adx": adx_val,
                    "type": "breakdown"
                }
            )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略 4: Volatility Regime Switch (波動率 regime 切換)
# ============================================================================
class VolatilityRegimeSwitch(BaseStrategy):
    """
    波動率 Regime 切換策略
    
    核心理念：
    - 低波動率時入場（市場盤整即將突破）
    - 高波動率時減倉或退出
    - 利用波動率收斂後的突破
    
    進場條件：
    1. ATR 處於 20日低 25% 分位
    2. ATR 正在上升（波動率擴張）
    3. 價格在布林帶中軌附近
    4. 趨勢方向與突破方向一致
    
    出場條件：
    1. ATR 觸及 80% 分位
    2. 價格觸及布林帶外軌
    3. 止損 4%
    4. 止盈 12%
    """
    
    def __init__(self,
                 # 布林帶參數
                 bb_period: int = 20,
                 bb_std: float = 2.0,
                 # ATR 參數
                 atr_period: int = 14,
                 atr_percentile_low: float = 0.25,
                 atr_percentile_high: float = 0.80,
                 atr_expansion_threshold: float = 0.1,
                 # 風控參數
                 stop_loss: float = 0.04,
                 take_profit: float = 0.12,
                 max_holding_days: int = 20):
        
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.atr_percentile_low = atr_percentile_low
        self.atr_percentile_high = atr_percentile_high
        self.atr_expansion_threshold = atr_expansion_threshold
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame) -> SignalResult:
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        current_price = close.iloc[-1]
        
        # 布林帶
        bb_sma = close.rolling(self.bb_period).mean()
        bb_std = close.rolling(self.bb_period).std()
        bb_upper = bb_sma + self.bb_std * self.bb_std
        bb_lower = bb_sma - self.bb_std * self.bb_std
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower).replace(0, 0.5)
        
        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean()
        
        # ATR 分位數
        atr_percentile = (atr.rolling(50).rank(pct=True).iloc[-1]
                         if len(atr) >= 50 else 0.5)
        atr_prev_percentile = (atr.rolling(50).rank(pct=True).iloc[-5]
                              if len(atr) >= 55 else atr_percentile)
        atr_expansion = atr_percentile - atr_prev_percentile
        
        # ATR 絕對值
        atr_val = atr.iloc[-1] if len(atr) > 0 else current_price * 0.02
        atr_pct = atr_val / current_price
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
            
            # 波動率過高退出
            if atr_percentile > self.atr_percentile_high:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason="High volatility exit", metadata={"type": "volatility_exit"})
            
            # 價格突破布林帶
            if current_price >= bb_upper.iloc[-1]:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason="BB upper touch", metadata={"type": "bb_touch"})
            if current_price <= bb_lower.iloc[-1]:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason="BB lower touch", metadata={"type": "bb_touch"})
        
        # 檢查數據
        if len(close) < max(self.bb_period, self.atr_period) + 10:
            return SignalResult(signal="HOLD", confidence=0.2, price=current_price,
                               reason="Insufficient data")
        
        # 低波動率 + 波動率即將擴張
        low_volatility = atr_percentile < self.atr_percentile_low
        vol_expansion = atr_expansion > self.atr_expansion_threshold
        bb_middle = bb_position.iloc[-1] > 0.3 and bb_position.iloc[-1] < 0.7
        
        if low_volatility and vol_expansion and bb_middle:
            # 判斷方向
            bb_sma_trend = bb_sma.iloc[-1] > bb_sma.iloc[-5] if len(bb_sma) >= 5 else True
            bb_sma_trend_short = bb_sma.iloc[-1] < bb_sma.iloc[-5] if len(bb_sma) >= 5 else False
            
            if bb_sma_trend:
                return SignalResult(
                    signal="LONG",
                    confidence=0.70,
                    price=current_price,
                    reason=f"Volatility Expansion LONG (ATR%={atr_percentile:.2f})",
                    metadata={
                        "atr_percentile": atr_percentile,
                        "bb_position": bb_position.iloc[-1],
                        "type": "volatility_play"
                    }
                )
            elif bb_sma_trend_short:
                return SignalResult(
                    signal="SHORT",
                    confidence=0.70,
                    price=current_price,
                    reason=f"Volatility Expansion SHORT (ATR%={atr_percentile:.2f})",
                    metadata={
                        "atr_percentile": atr_percentile,
                        "type": "volatility_play"
                    }
                )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略字典，方便調用
# ============================================================================
STRATEGIES = {
    "EnhancedMomentum": EnhancedMomentum,
    "MeanReversionRSI": MeanReversionRSI,
    "TrendFilteredBreakout": TrendFilteredBreakout,
    "VolatilityRegimeSwitch": VolatilityRegimeSwitch,
}


def get_strategy(name: str, **kwargs):
    """獲取策略實例"""
    if name in STRATEGIES:
        return STRATEGIES[name](**kwargs)
    raise ValueError(f"Unknown strategy: {name}")
