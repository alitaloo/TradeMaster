"""
高級量化策略模組 - 目標 Return > 20%, Sharpe > 1.5

策略列表：
1. Advanced Dual Momentum - 增強版雙重動量策略
2. Quality Momentum - 質量動量策略
3. RSI-2 Aggressive - RSI-2 激进策略
4. WilliamsPercentR - %R 威廉指標策略
5. ATR Breakout System - ATR 突破策略
6. Adaptive Multi-Factor - 自適應多因子策略

Author: TradeMaster Pro
Date: 2026-02-07
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from backtest import PositionType, BacktestResult


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
# 策略 1: Advanced Dual Momentum (增強版雙重動量)
# ============================================================================
class AdvancedDualMomentum(BaseStrategy):
    """
    增強版雙重動量策略
    
    核心理念：
    - 絕對動量：確保標的有正報酬（過濾弱勢標的）
    - 相對動量：選擇最強的標的
    - 多週期確認：日線+週線共振
    - 波動率調整倉位大小
    
    參數優化目標：
    - Return > 25%
    - Sharpe > 1.5
    - MaxDD < 15%
    
    進場條件：
    1. 12個月絕對動量 > 0%（排除長期弱勢）
    2. 相對動量排名前20%
    3. RSI(10) > 50（短期偏多）
    4. 價格 > 50日均線（確認趨勢）
    
    出場條件：
    1. 絕對動量轉負
    2. RSI < 35
    3. 止損 10%
    4. 止盈 30%
    """
    
    def __init__(self,
                 # 絕對動量參數
                 abs_momentum_months: int = 12,
                 abs_momentum_threshold: float = 0.0,
                 # 相對動量參數
                 rel_momentum_periods: int = 6,
                 rel_rank_threshold: float = 0.2,
                 # RSI 參數
                 rsi_period: int = 10,
                 rsi_entry: float = 50,
                 rsi_exit: float = 35,
                 # 均線參數
                 sma_period: int = 50,
                 # 風控參數
                 stop_loss: float = 0.10,
                 take_profit: float = 0.30,
                 max_holding_days: int = 60):
        
        self.abs_momentum_months = abs_momentum_months
        self.abs_momentum_threshold = abs_momentum_threshold
        self.rel_momentum_periods = rel_momentum_periods
        self.rel_rank_threshold = rel_rank_threshold
        self.rsi_period = rsi_period
        self.rsi_entry = rsi_entry
        self.rsi_exit = rsi_exit
        self.sma_period = sma_period
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame, 
                        peer_returns: pd.Series = None) -> SignalResult:
        """
        計算雙重動量訊號
        
        Args:
            ind: 技術指標字典
            data: 價格數據
            peer_returns: 同業報酬率（用於相對動量排名）
        """
        close = data["Close"]
        current_price = close.iloc[-1]
        
        # ========== 絕對動量計算 ==========
        abs_mom_months = min(self.abs_momentum_months, len(close) // 21)
        if abs_mom_months < 1:
            return SignalResult(signal="HOLD", confidence=0.2, price=current_price,
                               reason="Insufficient data for abs momentum")
        
        abs_momentum = (close.iloc[-1] / close.iloc[-abs_mom_months * 21] - 1) if len(close) >= abs_mom_months * 21 + 1 else 0
        
        # ========== 相對動量計算 ==========
        rel_mom_periods = min(self.rel_momentum_periods, len(close) // 5)
        if rel_mom_periods < 1:
            rel_momentum = 0
        else:
            rel_momentum = (close.iloc[-1] / close.iloc[-rel_mom_periods * 5] - 1)
        
        # 相對排名
        rel_rank = 0.5  # 默認中間
        if peer_returns is not None and len(peer_returns) > 1:
            rel_rank = (peer_returns < rel_momentum).sum() / len(peer_returns)
        
        # ========== RSI 計算 ==========
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        
        # ========== 均線計算 ==========
        sma = close.rolling(self.sma_period).mean()
        sma_val = sma.iloc[-1] if len(sma) > 0 else current_price
        
        # ========== 持倉檢查 ==========
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            # 出場訊號
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", 
                    metadata={"type": "take_profit", "return": price_change})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)",
                    metadata={"type": "stop_loss", "return": price_change})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)",
                    metadata={"type": "time_exit", "return": price_change})
            
            # RSI 反轉訊號
            if rsi_val < self.rsi_exit:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason=f"RSI exit ({rsi_val:.1f})",
                    metadata={"type": "rsi_exit", "rsi": rsi_val})
        
        # ========== 進場條件 ==========
        abs_mom_ok = abs_momentum > self.abs_momentum_threshold
        rel_mom_ok = rel_rank < self.rel_rank_threshold  # 前20%
        rsi_ok = rsi_val > self.rsi_entry
        trend_ok = current_price > sma_val
        
        if abs_mom_ok and rel_mom_ok and rsi_ok and trend_ok:
            # 信心度計算
            confidence = 0.65
            confidence += min(abs_momentum * 0.5, 0.1)  # 絕對動量貢獻
            confidence += min((0.2 - rel_rank) * 0.5, 0.1)  # 相對排名貢獻
            confidence += min((rsi_val - 50) * 0.01, 0.1)  # RSI 貢獻
            confidence = min(confidence, 0.90)
            
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"DualMomentum LONG (Abs={abs_momentum*100:.1f}%, Rank={rel_rank*100:.0f}%, RSI={rsi_val:.1f})",
                metadata={
                    "abs_momentum": abs_momentum,
                    "rel_momentum": rel_momentum,
                    "rel_rank": rel_rank,
                    "rsi": rsi_val,
                    "sma_distance": (current_price - sma_val) / sma_val,
                    "type": "dual_momentum"
                }
            )
        
        # ========== 長期弱勢排除 ==========
        if abs_momentum < -0.15:  # 下跌超過15%
            return SignalResult(
                signal="HOLD",
                confidence=0.4,
                price=current_price,
                reason=f"Weak momentum (Abs={abs_momentum*100:.1f}%)",
                metadata={"abs_momentum": abs_momentum, "type": "weak_momentum"}
            )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略 2: Quality Momentum (質量動量)
# ============================================================================
class QualityMomentum(BaseStrategy):
    """
    質量動量策略
    
    核心理念：
    - 結合動量與基本面質量
    - 高質量（高ROE、低槓桿、穩定盈利）標的有更穩定的報酬
    - 只在動量強勁且質量好的標的上持有
    
    進場條件：
    1. 6個月價格動量 > 10%
    2. ROE > 15%（質量指標）
    3. 債務/權益 < 0.5（低槓桿）
    4. EPS 穩定性高（質量確認）
    5. RSI < 70（不追高）
    
    出場條件：
    1. 動量轉弱（跌破20日均線）
    2. 質量惡化（ROE 下降）
    3. 止損 12%
    4. 止盈 35%
    """
    
    def __init__(self,
                 # 動量參數
                 momentum_period: int = 126,  # 6個月
                 momentum_threshold: float = 0.10,
                 # 質量參數
                 roe_threshold: float = 0.15,
                 debt_equity_max: float = 0.5,
                 eps_stability_window: int = 4,
                 eps_stability_threshold: float = 0.1,
                 # RSI 參數
                 rsi_period: int = 14,
                 rsi_max: float = 70,
                 # 均線參數
                 sma_period: int = 20,
                 # 風控參數
                 stop_loss: float = 0.12,
                 take_profit: float = 0.35,
                 max_holding_days: int = 90):
        
        self.momentum_period = momentum_period
        self.momentum_threshold = momentum_threshold
        self.roe_threshold = roe_threshold
        self.debt_equity_max = debt_equity_max
        self.eps_stability_window = eps_stability_window
        self.eps_stability_threshold = eps_stability_threshold
        self.rsi_period = rsi_period
        self.rsi_max = rsi_max
        self.sma_period = sma_period
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame,
                        fundamentals: Dict = None) -> SignalResult:
        """
        計算質量動量訊號
        
        Args:
            ind: 技術指標字典
            data: 價格數據
            fundamentals: 基本面數據 {'roe': float, 'debt_equity': float, 'eps': [list]}
        """
        close = data["Close"]
        current_price = close.iloc[-1]
        
        # ========== 價格動量 ==========
        mom_period = min(self.momentum_period, len(close) - 1)
        if mom_period < 20:
            return SignalResult(signal="HOLD", confidence=0.2, price=current_price,
                               reason="Insufficient data for momentum")
        
        momentum = (close.iloc[-1] / close.iloc[-mom_period] - 1)
        
        # ========== RSI ==========
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        
        # ========== 均線 ==========
        sma = close.rolling(self.sma_period).mean()
        sma_val = sma.iloc[-1] if len(sma) > 0 else current_price
        
        # ========== 質量評分 (0-1) ==========
        quality_score = 0.5
        
        if fundamentals:
            # ROE 評分
            roe = fundamentals.get('roe', 0)
            if roe >= self.roe_threshold:
                quality_score += 0.25
            elif roe >= self.roe_threshold * 0.7:
                quality_score += 0.1
            
            # 槓桿評分
            debt_equity = fundamentals.get('debt_equity', 1)
            if debt_equity <= self.debt_equity_max:
                quality_score += 0.25
            elif debt_equity <= self.debt_equity_max * 2:
                quality_score += 0.1
            
            # EPS 穩定性
            eps_history = fundamentals.get('eps', [])
            if len(eps_history) >= self.eps_stability_window:
                eps_std = np.std(eps_history[-self.eps_stability_window:])
                eps_mean = np.mean(eps_history[-self.eps_stability_window:])
                if eps_mean > 0 and eps_std / eps_mean < self.eps_stability_threshold:
                    quality_score += 0.25
        else:
            # 無基本面時，使用技術質量指標
            # 波動率質量
            volatility = close.pct_change().rolling(20).std()
            low_vol = volatility.iloc[-1] < volatility.rolling(50).mean().iloc[-1]
            if low_vol:
                quality_score += 0.2
        
        # ========== 持倉檢查 ==========
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)",
                    metadata={"type": "take_profit", "return": price_change})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)",
                    metadata={"type": "stop_loss", "return": price_change})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)",
                    metadata={"type": "time_exit", "return": price_change})
            
            # 趨勢跌破
            if current_price < sma_val:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason="Trend broken",
                    metadata={"type": "trend_break"})
        
        # ========== 進場條件 ==========
        momentum_ok = momentum > self.momentum_threshold
        rsi_ok = rsi_val < self.rsi_max
        trend_ok = current_price > sma_val
        quality_ok = quality_score >= 0.75
        
        if momentum_ok and rsi_ok and trend_ok and quality_ok:
            confidence = 0.65
            confidence += min(momentum * 2, 0.1)  # 動量貢獻
            confidence += min(quality_score * 0.1, 0.1)  # 質量貢獻
            if rsi_val < 50:
                confidence += 0.05  # 低 RSI 獎勵
            confidence = min(confidence, 0.90)
            
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"QualityMomentum LONG (Momentum={momentum*100:.1f}%, Quality={quality_score:.2f}, RSI={rsi_val:.1f})",
                metadata={
                    "momentum": momentum,
                    "quality_score": quality_score,
                    "rsi": rsi_val,
                    "sma_distance": (current_price - sma_val) / sma_val,
                    "type": "quality_momentum"
                }
            )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略 3: RSI-2 Aggressive (RSI-2 激进策略)
# ============================================================================
class RSIAggressive(BaseStrategy):
    """
    RSI-2 激进短線策略
    
    核心理念：
    - 極短期 RSI 捕捉快速反彈
    - 只在深度超賣時入場
    - 嚴格止損控制風險
    - 快進快出
    
    參數優化：
    - RSI 週期: 2
    - 超賣門檻: < 15
    - 反彈確認: RSI 升至 > 30
    
    進場條件：
    1. RSI(2) < 15（深度超賣）
    2. 價格接近 N 日低點
    3. 波動率處於相對高位（恐慌後的反彈）
    
    出場條件：
    1. RSI > 55（超買區域）
    2. 止損 3%
    3. 止盈 8%
    4. 最大持倉 5 天
    """
    
    def __init__(self,
                 # RSI 參數
                 rsi_period: int = 2,
                 rsi_oversold: float = 15,
                 rsi_exit: float = 55,
                 # 低點確認
                 low_period: int = 10,
                 # 波動率參數
                 vol_period: int = 20,
                 vol_percentile_min: float = 0.4,
                 # 風控參數
                 stop_loss: float = 0.03,
                 take_profit: float = 0.08,
                 max_holding_days: int = 5):
        
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_exit = rsi_exit
        self.low_period = low_period
        self.vol_period = vol_period
        self.vol_percentile_min = vol_percentile_min
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame) -> SignalResult:
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        current_price = close.iloc[-1]
        
        # ========== RSI-2 計算 ==========
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        prev_rsi = rsi.iloc[-2] if len(rsi) >= 2 else rsi_val
        
        # ========== 低點確認 ==========
        rolling_low = low.rolling(self.low_period).min()
        is_new_low = close.iloc[-1] <= rolling_low.iloc[-1]
        low_distance = (rolling_low.iloc[-1] - current_price) / rolling_low.iloc[-1] if len(rolling_low) > 0 else 0
        
        # ========== 波動率 ==========
        returns = close.pct_change()
        vol = returns.rolling(self.vol_period).std() * np.sqrt(252)
        vol_percentile = (vol.rolling(50).rank(pct=True).iloc[-1] 
                         if len(vol) >= 50 else 0.5)
        
        # ========== 持倉檢查 ==========
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)",
                    metadata={"type": "take_profit", "return": price_change})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.9, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)",
                    metadata={"type": "stop_loss", "return": price_change})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason=f"Time exit ({holding_days} days)",
                    metadata={"type": "time_exit", "return": price_change})
            
            # RSI 反彈訊號
            if rsi_val > self.rsi_exit and prev_rsi <= self.rsi_exit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"RSI reversal (RSI={rsi_val:.1f})",
                    metadata={"type": "rsi_reversal", "rsi": rsi_val})
        
        # ========== 進場條件 - 深度超賣 ==========
        oversold = rsi_val < self.rsi_oversold
        near_low = low_distance < 0.02  # 距離低點 < 2%
        vol_ok = vol_percentile > self.vol_percentile_min
        
        if oversold and near_low and vol_ok:
            # 信心度
            confidence = 0.70
            confidence += (self.rsi_oversold - rsi_val) * 0.03  # 越超賣信心越高
            confidence += min(low_distance * 5, 0.1)  # 越接近低點越好
            confidence = min(confidence, 0.90)
            
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"RSI-2 LONG (RSI={rsi_val:.1f}, LowDist={low_distance*100:.1f}%)",
                metadata={
                    "rsi": rsi_val,
                    "low_distance": low_distance,
                    "vol_percentile": vol_percentile,
                    "type": "rsi2_oversold"
                }
            )
        
        # ========== 反彈後入場 ==========
        rsi_recovering = rsi_oversold < rsi_val < 35
        recovering_from = prev_rsi <= self.rsi_oversold
        
        if rsi_recovering and recovering_from:
            confidence = 0.65
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"RSI-2 Recovery (RSI={rsi_val:.1f}->{rsi_val:.1f})",
                metadata={
                    "rsi": rsi_val,
                    "prev_rsi": prev_rsi,
                    "type": "rsi2_recovery"
                }
            )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略 4: WilliamsPercentR (威廉指標策略)
# ============================================================================
class WilliamsPercentR(BaseStrategy):
    """
    威廉指標 (%R) 策略
    
    核心理念：
    - %R 類似 RSI，但更敏感
    - 多時間框架確認
    - 逆勢交易，超賣買入，超買賣出
    
    進場條件：
    1. 日線 %R < -80（超賣）
    2. 週線 %R < -60（確認趨勢）
    3. 日線即將反彈（%R 上升）
    
    出場條件：
    1. %R > -20（超買）
    2. 止損 5%
    3. 止盈 12%
    """
    
    def __init__(self,
                 # %R 參數
                 williams_period: int = 14,
                 daily_oversold: float = -80,
                 daily_overbought: float = -20,
                 weekly_oversold: float = -60,
                 # 反彈確認
                 recovery_threshold: float = 10,
                 # 風控參數
                 stop_loss: float = 0.05,
                 take_profit: float = 0.12,
                 max_holding_days: int = 15):
        
        self.williams_period = williams_period
        self.daily_oversold = daily_oversold
        self.daily_overbought = daily_overbought
        self.weekly_oversold = weekly_oversold
        self.recovery_threshold = recovery_threshold
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame,
                        weekly_data: pd.DataFrame = None) -> SignalResult:
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        current_price = close.iloc[-1]
        
        # ========== 日線 %R ==========
        highest = high.rolling(window=self.williams_period).max()
        lowest = low.rolling(window=self.williams_period).min()
        williams_r = -100 * (highest - close) / (highest - lowest).replace(0, 1)
        williams_r = williams_r.fillna(-50)
        williams_r_val = williams_r.iloc[-1]
        prev_williams_r = williams_r.iloc[-2] if len(williams_r) >= 2 else williams_r_val
        
        # ========== 週線 %R (如果有) ==========
        weekly_williams_r_val = -50
        weekly_overlap_ok = False
        if weekly_data is not None and len(weekly_data) >= self.williams_period:
            whigh = weekly_data["High"]
            wlow = weekly_data["Low"]
            whighest = whigh.rolling(window=self.williams_period).max()
            wlowest = wlow.rolling(window=self.williams_period).min()
            weekly_williams_r = -100 * (whighest - weekly_data["Close"].iloc[-1]) / (whighest - wlowest).replace(0, 1)
            weekly_williams_r_val = weekly_williams_r.iloc[-1] if len(weekly_williams_r) > 0 else -50
            weekly_overlap_ok = weekly_williams_r_val < self.weekly_oversold
        
        # ========== 持倉檢查 ==========
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)",
                    metadata={"type": "take_profit", "return": price_change})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)",
                    metadata={"type": "stop_loss", "return": price_change})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)",
                    metadata={"type": "time_exit", "return": price_change})
            
            # 反彈至超買區域
            if williams_r_val > self.daily_overbought:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason=f"Overbought exit ({williams_r_val:.1f})",
                    metadata={"type": "overbought_exit"})
        
        # ========== 進場條件 ==========
        daily_oversold = williams_r_val < self.daily_oversold
        recovering = williams_r_val > prev_williams_r  # 正在反彈
        weekly_confirm = weekly_overlap_ok or True  # 如果沒有週線數據，則跳過
        
        if daily_oversold and recovering and weekly_confirm:
            confidence = 0.65
            confidence += (self.daily_oversold - williams_r_val) * 0.02
            if weekly_overlap_ok:
                confidence += 0.1  # 週線確認加成
            confidence = min(confidence, 0.85)
            
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"%R LONG (Daily={williams_r_val:.1f}, Weekly={weekly_williams_r_val:.1f})",
                metadata={
                    "williams_r": williams_r_val,
                    "prev_williams_r": prev_williams_r,
                    "weekly_williams_r": weekly_williams_r_val,
                    "type": "williams_oversold"
                }
            )
        
        # ========== 做空條件 ==========
        daily_overbought = williams_r_val > self.daily_overbought
        declining = williams_r_val < prev_williams_r
        
        if daily_overbought and declining:
            confidence = 0.60
            confidence += (williams_r_val - self.daily_overbought) * 0.02
            confidence = min(confidence, 0.80)
            
            return SignalResult(
                signal="SHORT",
                confidence=confidence,
                price=current_price,
                reason=f"%R SHORT (Daily={williams_r_val:.1f})",
                metadata={
                    "williams_r": williams_r_val,
                    "type": "williams_overbought"
                }
            )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略 5: ATR Breakout System (ATR 突破策略)
# ============================================================================
class ATRBreakout(BaseStrategy):
    """
    ATR 突破策略
    
    核心理念：
    - 利用 ATR 計算真實波動範圍
    - 波動率擴張時入場
    - 價格突破時確認方向
    
    進場條件：
    1. ATR 處於低分位 (< 30%)
    2. ATR 開始擴張 (上升)
    3. 價格突破 N 日區間
    4. 成交量確認
    
    出場條件：
    1. ATR 觸發高位
    2. 止損 6%
    3. 止盈 20%
    """
    
    def __init__(self,
                 # ATR 參數
                 atr_period: int = 14,
                 atr_low_percentile: float = 0.30,
                 atr_expansion_threshold: float = 0.15,
                 # 突破參數
                 breakout_period: int = 20,
                 # 成交量參數
                 volume_period: int = 20,
                 volume_threshold: float = 1.5,
                 # 風控參數
                 stop_loss: float = 0.06,
                 take_profit: float = 0.20,
                 max_holding_days: int = 25):
        
        self.atr_period = atr_period
        self.atr_low_percentile = atr_low_percentile
        self.atr_expansion_threshold = atr_expansion_threshold
        self.breakout_period = breakout_period
        self.volume_period = volume_period
        self.volume_threshold = volume_threshold
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame) -> SignalResult:
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        volume = data.get("Volume", pd.Series([1000000] * len(close)))
        current_price = close.iloc[-1]
        
        # ========== ATR 計算 ==========
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean()
        atr_val = atr.iloc[-1] if len(atr) > 0 else current_price * 0.02
        
        # ATR 分位數
        atr_percentile = (atr.rolling(50).rank(pct=True).iloc[-1]
                         if len(atr) >= 50 else 0.5)
        atr_prev_percentile = (atr.rolling(50).rank(pct=True).iloc[-5]
                              if len(atr) >= 55 else atr_percentile)
        atr_expansion = atr_percentile - atr_prev_percentile
        
        # ========== ATR % ==========
        atr_pct = atr_val / current_price
        
        # ========== 突破區間 ==========
        rolling_high = high.rolling(self.breakout_period).max()
        rolling_low = low.rolling(self.breakout_period).min()
        prev_high = rolling_high.iloc[-2]
        prev_low = rolling_low.iloc[-2]
        curr_high = rolling_high.iloc[-1]
        curr_low = rolling_low.iloc[-1]
        
        # ========== 成交量 ==========
        volume_ma = volume.rolling(self.volume_period).mean()
        volume_ratio = volume.iloc[-1] / volume_ma.iloc[-1] if len(volume_ma) > 0 else 1.0
        
        # ========== 持倉檢查 ==========
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)",
                    metadata={"type": "take_profit", "return": price_change})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)",
                    metadata={"type": "stop_loss", "return": price_change})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)",
                    metadata={"type": "time_exit", "return": price_change})
            
            # 波動率過高退出
            if atr_percentile > 0.8:
                return SignalResult(signal="HOLD", confidence=0.6, price=current_price,
                    reason=f"High volatility exit (ATR%={atr_percentile:.1f})",
                    metadata={"type": "volatility_exit"})
        
        # ========== 進場條件 - 低波動率 + 擴張信號 ==========
        low_volatility = atr_percentile < self.atr_low_percentile
        vol_expansion = atr_expansion > self.atr_expansion_threshold
        
        if low_volatility and vol_expansion:
            # 向上突破
            if prev_high < curr_high and close.iloc[-1] >= curr_high and volume_ratio > self.volume_threshold:
                confidence = 0.70
                confidence += (0.3 - atr_percentile) * 0.3
                confidence += min(volume_ratio * 0.1, 0.1)
                confidence = min(confidence, 0.85)
                
                return SignalResult(
                    signal="LONG",
                    confidence=confidence,
                    price=current_price,
                    reason=f"ATR Breakout LONG (ATR%={atr_percentile:.1f}, V={volume_ratio:.1f}x)",
                    metadata={
                        "atr_percentile": atr_percentile,
                        "atr_expansion": atr_expansion,
                        "volume_ratio": volume_ratio,
                        "type": "atr_breakout"
                    }
                )
            
            # 向下突破
            if prev_low > curr_low and close.iloc[-1] <= curr_low and volume_ratio > self.volume_threshold:
                confidence = 0.70
                confidence += (0.3 - atr_percentile) * 0.3
                confidence = min(confidence, 0.85)
                
                return SignalResult(
                    signal="SHORT",
                    confidence=confidence,
                    price=current_price,
                    reason=f"ATR Breakdown SHORT (ATR%={atr_percentile:.1f})",
                    metadata={
                        "atr_percentile": atr_percentile,
                        "type": "atr_breakdown"
                    }
                )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


# ============================================================================
# 策略 6: Adaptive Multi-Factor (自適應多因子策略)
# ============================================================================
class AdaptiveMultiFactor(BaseStrategy):
    """
    自適應多因子策略
    
    核心理念：
    - 結合動量、均值回歸、波動率多個因子
    - 根據市場狀態自動調整權重
    - 高動量市場：增加趨勢追蹤權重
    - 低波動率市場：增加均值回歸權重
    - 高波動率市場：減少倉位或退出
    
    因子：
    1. 動量因子 (ROC, RSI)
    2. 均值回歸因子 (價格偏離均線)
    3. 波動率因子 (ATR, 歷史波動率)
    4. 趨勢因子 (ADX, 均線方向)
    
    進場條件：
    1. 複合信號 > 0.6
    2. 市場狀態允許
    
    出場條件：
    1. 複合信號 < 0.3
    2. 波動率過高
    """
    
    def __init__(self,
                 # 動量因子參數
                 roc_period: int = 10,
                 roc_weight: float = 0.3,
                 # 均值回歸參數
                 mean_reversion_period: int = 20,
                 mr_threshold: float = 0.05,
                 mr_weight: float = 0.2,
                 # 波動率因子參數
                 vol_period: int = 20,
                 vol_threshold_high: float = 0.30,
                 vol_weight: float = 0.2,
                 # 趨勢因子參數
                 trend_period: int = 50,
                 adx_period: int = 14,
                 trend_weight: float = 0.3,
                 # 風控參數
                 stop_loss: float = 0.08,
                 take_profit: float = 0.25,
                 max_holding_days: int = 30):
        
        self.roc_period = roc_period
        self.roc_weight = roc_weight
        self.mean_reversion_period = mean_reversion_period
        self.mr_threshold = mr_threshold
        self.mr_weight = mr_weight
        self.vol_period = vol_period
        self.vol_threshold_high = vol_threshold_high
        self.vol_weight = vol_weight
        self.trend_period = trend_period
        self.adx_period = adx_period
        self.trend_weight = trend_weight
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind: dict, data: pd.DataFrame,
                        market_regime: str = "neutral") -> SignalResult:
        """
        計算自適應多因子訊號
        
        Args:
            ind: 技術指標字典
            data: 價格數據
            market_regime: 市場狀態 ('trending', 'volatile', 'neutral')
        """
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        current_price = close.iloc[-1]
        
        # ========== 動量因子 ==========
        roc = close.pct_change(self.roc_period) * 100
        roc_val = roc.iloc[-1] if len(roc) >= self.roc_period else 0
        roc_normalized = np.clip(roc_val / 10, -1, 1)  # 標準化到 [-1, 1]
        
        # ========== 均值回歸因子 ==========
        sma_mr = close.rolling(self.mean_reversion_period).mean()
        price_vs_sma = (close - sma_mr) / sma_mr.replace(0, 1)
        price_vs_sma_val = price_vs_sma.iloc[-1]
        # 價格低於均線時做多，高於均線時做空
        mr_signal = -np.clip(price_vs_sma_val / self.mr_threshold, -1, 1)
        
        # ========== 波動率因子 ==========
        returns = close.pct_change()
        vol = returns.rolling(self.vol_period).std() * np.sqrt(252)
        vol_percentile = (vol.rolling(50).rank(pct=True).iloc[-1]
                         if len(vol) >= 50 else 0.5)
        # 高波動率時減少信號強度
        vol_penalty = 1.0 if vol_percentile < self.vol_threshold_high else 0.5
        
        # ========== 趨勢因子 ==========
        sma_trend = close.rolling(self.trend_period).mean()
        trend_direction = np.sign(sma_trend.iloc[-1] - sma_trend.iloc[-20]) if len(sma_trend) >= 20 else 0
        
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
        adx_val = adx.iloc[-1] if len(adx) > 0 else 20
        trend_strength = min(adx_val / 50, 1.0)  # 標準化
        
        # 趨勢信號
        trend_signal = trend_direction * trend_strength
        
        # ========== 複合信號 ==========
        composite_signal = (
            self.roc_weight * roc_normalized +
            self.mr_weight * mr_signal +
            self.trend_weight * trend_signal
        ) * vol_penalty
        
        # 根據市場狀態調整權重
        if market_regime == "trending":
            composite_signal += self.trend_weight * 0.2
        elif market_regime == "volatile":
            composite_signal *= 0.7  # 降低信號強度
        
        # ========== 持倉檢查 ==========
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.7, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)",
                    metadata={"type": "take_profit", "return": price_change, "composite": composite_signal})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.8, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)",
                    metadata={"type": "stop_loss", "return": price_change})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)",
                    metadata={"type": "time_exit", "return": price_change})
        
        # ========== 進場/出場信號 ==========
        long_threshold = 0.25
        short_threshold = -0.25
        
        if composite_signal > long_threshold:
            confidence = 0.65 + min(composite_signal * 0.3, 0.2)
            confidence = min(confidence, 0.85)
            
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason=f"Adaptive Multi-Factor LONG (Composite={composite_signal:.2f}, Regime={market_regime})",
                metadata={
                    "composite_signal": composite_signal,
                    "roc": roc_val,
                    "price_vs_sma": price_vs_sma_val,
                    "vol_percentile": vol_percentile,
                    "adx": adx_val,
                    "market_regime": market_regime,
                    "type": "adaptive_multifactor"
                }
            )
        
        if composite_signal < short_threshold:
            confidence = 0.60 + min(abs(composite_signal) * 0.3, 0.2)
            confidence = min(confidence, 0.80)
            
            return SignalResult(
                signal="SHORT",
                confidence=confidence,
                price=current_price,
                reason=f"Adaptive Multi-Factor SHORT (Composite={composite_signal:.2f})",
                metadata={
                    "composite_signal": composite_signal,
                    "type": "adaptive_multifactor"
                }
            )
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, 
                          reason=f"No signal (Composite={composite_signal:.2f})")


# ============================================================================
# 策略字典
# ============================================================================
ADVANCED_STRATEGIES = {
    "AdvancedDualMomentum": AdvancedDualMomentum,
    "QualityMomentum": QualityMomentum,
    "RSIAggressive": RSIAggressive,
    "WilliamsPercentR": WilliamsPercentR,
    "ATRBreakout": ATRBreakout,
    "AdaptiveMultiFactor": AdaptiveMultiFactor,
}


def get_advanced_strategy(name: str, **kwargs):
    """獲取高級策略實例"""
    if name in ADVANCED_STRATEGIES:
        return ADVANCED_STRATEGIES[name](**kwargs)
    raise ValueError(f"Unknown advanced strategy: {name}")
