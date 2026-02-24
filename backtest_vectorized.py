"""
Vectorized Backtest Engine v2
效能優化版 - 保留 Kelly 計算，但優化信號生成與回測循環
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from enum import Enum
import copy


class PositionType(Enum):
    NONE = 0
    LONG = 1
    SHORT = -1


class SignalResult:
    def __init__(self, signal: str = "HOLD", confidence: float = 0.0):
        self.signal = signal
        self.confidence = confidence


@dataclass
class BacktestResult:
    symbol: str = ""
    strategy: str = ""
    period: str = ""
    total_return: float = 0.0
    annualized_return: float = 0.0
    volatility: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    trades: List = None
    equity_curve: List = None
    kelly_position: float = 0.2
    
    def __post_init__(self):
        if self.trades is None:
            self.trades = []
        if self.equity_curve is None:
            self.equity_curve = []


def calculate_indicators(data: pd.DataFrame) -> dict:
    """從價格數據計算常用技術指標（向量化版本）"""
    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume = data.get("Volume", pd.Series([1000000] * len(close)))
    
    indicators = {}
    
    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    indicators["RSI"] = {"rsi": rs.fillna(50)}
    
    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    indicators["MACD"] = {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": macd_line - signal_line
    }
    
    # ADX
    period = 14
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    atr = (high - low).rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(window=period).mean()
    indicators["ADX"] = {
        "adx": adx.fillna(15),
        "plus_di": plus_di.fillna(20),
        "minus_di": minus_di.fillna(20)
    }
    
    # SMA
    sma50 = close.rolling(window=50).mean()
    indicators["SMA"] = {
        "sma": sma50,
        "price_vs_sma": (close - sma50) / sma50.replace(0, 1)
    }
    
    # EMA
    indicators["EMA"] = {"ema": close.ewm(span=50, adjust=False).mean()}
    
    # Bollinger Bands
    sma20 = close.rolling(window=20).mean()
    std20 = close.rolling(window=20).std()
    indicators["BollingerBands"] = {
        "upper": sma20 + 2 * std20,
        "middle": sma20,
        "lower": sma20 - 2 * std20,
        "percent": (close - (sma20 - 2 * std20)) / (4 * std20).replace(0, 0.5)
    }
    
    # Stochastic
    lowest14 = low.rolling(window=14).min()
    highest14 = high.rolling(window=14).max()
    stoch_k = 100 * (close - lowest14) / (highest14 - lowest14).replace(0, np.nan)
    stoch_d = stoch_k.rolling(window=3).mean()
    indicators["Stochastic"] = {
        "stoch_k": stoch_k.fillna(50),
        "stoch_d": stoch_d.fillna(50)
    }
    
    # Williams %R
    indicators["WilliamsR"] = {
        "williams_r": -100 * (highest14 - close) / (highest14 - lowest14).replace(0, 1)
    }
    
    # CCI
    typical_price = (high + low + close) / 3
    sma_tp = typical_price.rolling(window=20).mean()
    mad = typical_price.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean())
    indicators["CCI"] = {
        "cci": (typical_price - sma_tp) / (0.015 * mad).replace(0, 1)
    }
    
    # Momentum
    indicators["Momentum"] = {"momentum": close - close.shift(10)}
    
    # ATR
    indicators["ATR"] = {"atr": atr.fillna(atr.mean() if len(atr.dropna()) > 0 else 1)}
    
    # Volume EMA
    indicators["VolumeEMA"] = {"volume_ratio": volume / volume.ewm(span=20, adjust=False).mean()}
    
    # OBV
    obv = (np.sign(close.diff()) * volume).cumsum()
    indicators["OBV"] = {"obv": obv}
    
    return indicators


class VectorizedBacktestEngine:
    """向量化回測引擎 - 效能優化版"""
    
    DEFAULT_COMMISSION = 0.0001  # 1 bps (Futuo US stock)
    DEFAULT_SLIPPAGE = 0.001  # 10 bps
    
    def __init__(self, initial_capital: float = 100000, 
                 commission: float = None, 
                 slippage: float = None, 
                 kelly_fraction: float = 0.25,
                 use_atr_stop: bool = False,
                 atr_multiplier: float = 2.0):
        self.initial_capital = initial_capital
        self.commission = commission or self.DEFAULT_COMMISSION
        self.slippage = slippage or self.DEFAULT_SLIPPAGE
        self.kelly_fraction = kelly_fraction
        self.use_atr_stop = use_atr_stop
        self.atr_multiplier = atr_multiplier
    
    def run(self, symbol: str, strategy, data: pd.DataFrame, strategy_name: str = "Unknown") -> BacktestResult:
        """運行向量化回測（保留 Kelly）"""
        df = self._prepare_data(data.copy())
        df_index = pd.to_datetime(df.index)
        
        # 預先計算所有指標
        all_indicators = calculate_indicators(df)
        
        # Kelly 計算（保留）
        import copy
        temp_strategy = copy.copy(strategy)
        kelly_position = self._calculate_kelly_position_vectorized(temp_strategy, df, all_indicators)
        
        # Kelly 計算後重置狀態（與原始版本一致）
        # 原始版本會重置 position = NONE
        
        # 預先生成所有信號（向量化優化）
        signals = self._generate_signals_fast(strategy, df, all_indicators)
        
        # 向量化回測
        result = self._run_backtest_vectorized(df, df_index, signals, all_indicators, kelly_position, strategy_name)
        result.kelly_position = kelly_position
        
        return result
    
    def _prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [c.capitalize() for c in df.columns]
        if 'Volume' not in df.columns:
            df['Volume'] = 1000000
        return df
    
    def _calculate_kelly_position_vectorized(self, strategy, df: pd.DataFrame, all_indicators: dict) -> float:
        """優化的 Kelly 計算 - 與主回測邏輯一致"""
        n = len(df)
        prices = df['Close'].values
        
        capital = self.initial_capital
        position = PositionType.NONE
        entry_price = 0.0
        shares = 0
        trades_pnl = []
        
        for i in range(n - 1):
            ind = self._get_indicators_at(all_indicators, i)
            signal = strategy.generate_signal(ind, df.iloc[:i+1])
            current_price = prices[i]
            
            # 與主回測一致的邏輯
            if signal.signal == "LONG" and position != PositionType.LONG:
                if position == PositionType.SHORT:
                    # 平 SHORT
                    exit_price = current_price * (1 + self.slippage)  # 買回
                    pnl = (entry_price - exit_price) * shares
                    trades_pnl.append(pnl)
                    capital += pnl
                # 做多
                shares = int(capital * self.kelly_fraction / current_price)
                entry_price = current_price * (1 + self.slippage)  # 買入
                position = PositionType.LONG
            
            elif signal.signal == "SHORT" and position != PositionType.SHORT:
                if position == PositionType.LONG:
                    # 平多
                    exit_price = current_price * (1 - self.slippage)  # 賣出
                    pnl = (exit_price - entry_price) * shares
                    trades_pnl.append(pnl)
                    capital += pnl
                # 做空
                shares = int(capital * self.kelly_fraction / current_price)
                entry_price = current_price * (1 - self.slippage)  # 賣出
                position = PositionType.SHORT
        
        if trades_pnl:
            wins = [p for p in trades_pnl if p > 0]
            losses = [p for p in trades_pnl if p <= 0]
            p = len(wins) / len(trades_pnl) if trades_pnl else 0
            avg_win = np.mean(wins) if wins else 0
            avg_loss = abs(np.mean(losses)) if losses else 1
            b = avg_win / avg_loss if avg_loss > 0 else 1
            kelly_pct = p - (1 - p) / b
            kelly_pct = kelly_pct * self.kelly_fraction
            kelly_pct = max(0.05, min(0.50, kelly_pct))
            return kelly_pct
        
        return self.kelly_fraction
    
    def _get_indicators_at(self, all_indicators: dict, i: int) -> dict:
        """快速獲取指標"""
        ind = {}
        for ind_name, ind_values in all_indicators.items():
            ind[ind_name] = {}
            for key, series in ind_values.items():
                if hasattr(series, 'iloc'):
                    ind[ind_name][key] = series.iloc[:i+1].reset_index(drop=True)
        return ind
    
    def _generate_signals_fast(self, strategy, df: pd.DataFrame, all_indicators: dict) -> np.ndarray:
        """快速生成所有信號"""
        n = len(df)
        signals = np.zeros(n, dtype=object)
        
        for i in range(n - 1):
            ind = self._get_indicators_at(all_indicators, i)
            signal = strategy.generate_signal(ind, df.iloc[:i+1])
            signals[i] = signal.signal
        
        signals[n-1] = "HOLD"
        return signals
    
    def _run_backtest_vectorized(self, df: pd.DataFrame, df_index, signals: np.ndarray, 
                                  all_indicators: dict, kelly_position: float, strategy_name: str = "Unknown") -> BacktestResult:
        """向量化回測"""
        n = len(df)
        prices = df['Close'].values
        atr = all_indicators['ATR']['atr'].values if self.use_atr_stop else None
        
        capital = self.initial_capital
        position = PositionType.NONE
        entry_price = 0.0
        entry_idx = 0
        shares = 0
        
        trades = []
        equity = np.zeros(n)
        equity[0] = capital
        
        for i in range(n - 1):
            current_price = prices[i]
            
            # ATR 止損
            if self.use_atr_stop and position != PositionType.NONE and atr is not None:
                atr_val = atr[i]
                if not np.isnan(atr_val):
                    atr_stop_distance = atr_val * self.atr_multiplier
                    
                    if position == PositionType.LONG:
                        stop_price = entry_price - atr_stop_distance
                        if current_price < stop_price:
                            exit_price = current_price * (1 - self.slippage)
                            pnl = (exit_price - entry_price) * shares
                            capital += pnl - (entry_price * shares + exit_price * shares) * self.commission
                            trades.append({"type": "LONG_ATR", "pnl": pnl})
                            position = PositionType.NONE
                            shares = 0
            
            # 信號交易
            # 原始邏輯：只有 signal="SHORT" 時 LONG exit，只有 signal="LONG" 時 SHORT exit
            signal = signals[i]
            
            # 處理反向倉位：SHORT -> LONG 或 LONG -> SHORT
            if position != PositionType.NONE:
                if (position == PositionType.SHORT and signal == "LONG") or \
                   (position == PositionType.LONG and signal == "SHORT"):
                    # 先平倉
                    if position == PositionType.SHORT:
                        exit_price = current_price * (1 + self.slippage)
                        pnl = (entry_price - exit_price) * shares
                        capital += pnl - (entry_price * shares + exit_price * shares) * self.commission
                        trades.append({"type": "SHORT_EXIT", "pnl": pnl})
                    else:  # LONG
                        exit_price = current_price * (1 - self.slippage)
                        pnl = (exit_price - entry_price) * shares
                        capital += pnl - (entry_price * shares + exit_price * shares) * self.commission
                        trades.append({"type": "LONG_EXIT", "pnl": pnl})
                    position = PositionType.NONE
                    shares = 0
            
            # 進場：只有 signal=LONG 或 signal=SHORT 才進場
            if position == PositionType.NONE:
                if signal == "LONG":
                    trades.append({"type": "LONG_ENTRY", "price": current_price})
                    position = PositionType.LONG
                    entry_price = current_price * (1 + self.slippage)
                    entry_idx = i
                    shares = int(capital * kelly_position / entry_price)
                    capital -= shares * entry_price  # 買入花錢
                elif signal == "SHORT":
                    trades.append({"type": "SHORT_ENTRY", "price": current_price})
                    position = PositionType.SHORT
                    entry_price = current_price * (1 - self.slippage)
                    entry_idx = i
                    shares = int(capital * kelly_position / entry_price)
                    capital += shares * entry_price  # 賣出賺錢
            
            # 更新權益
            if position == PositionType.LONG:
                equity[i + 1] = capital + shares * current_price
            elif position == PositionType.SHORT:
                # 做空：capital 是賣出獲得的資金
                # 未實現盈虧 = shares × (賣出價 - 買入價)
                unrealized_pnl = shares * (entry_price - current_price)
                equity[i + 1] = capital + unrealized_pnl
            else:
                equity[i + 1] = capital
        
        # 最後平倉 - 與原始版本一致：當有持倉時平倉，type 為 LONG_EXIT / SHORT_EXIT
        if position == PositionType.LONG and shares > 0:
            exit_price = prices[-1] * (1 - self.slippage)
            pnl = (exit_price - entry_price) * shares
            capital += pnl - (entry_price * shares + exit_price * shares) * self.commission
            trades.append({"type": "LONG_EXIT", "pnl": pnl})
        
        if position == PositionType.SHORT and shares > 0:
            exit_price = prices[-1] * (1 + self.slippage)
            pnl = (entry_price - exit_price) * shares
            capital += pnl - (entry_price * shares + exit_price * shares) * self.commission
            trades.append({"type": "SHORT_EXIT", "pnl": pnl})
        
        equity[-1] = capital
        
        # 計算指標
        total_return = (capital - self.initial_capital) / self.initial_capital
        
        returns = np.diff(equity) / equity[:-1]
        returns = returns[returns != 0]
        
        if len(returns) > 0 and equity[0] > 0:
            days = (df_index[-1] - df_index[0]).days
            annualized_return = ((1 + total_return) ** (365 / max(days, 1))) - 1 if total_return > -1 else -1
            volatility = np.std(returns) * np.sqrt(252 * 78)
            sharpe_ratio = (annualized_return - 0.02) / volatility if volatility > 0 else 0
            
            # Max DD
            peak = equity[0]
            max_dd = 0
            for e in equity:
                if e > peak:
                    peak = e
                dd = (peak - e) / peak if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd
            max_dd = min(max_dd, 1.0)
        else:
            annualized_return = -1
            volatility = 0
            sharpe_ratio = 0
            max_dd = 1
        
        win_trades = [t for t in trades if t.get('pnl', 0) > 0]
        win_rate = len(win_trades) / len(trades) if trades else 0
        
        result = BacktestResult(
            symbol=df.get('Symbol', [''])[0] if hasattr(df.get('Symbol', ['']), '__getitem__') else '',
            strategy=strategy_name,
            period=f"{df_index[0]} to {df_index[-1]}",
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=len(trades),
            trades=trades,
            equity_curve=equity.tolist()
        )
        
        return result
