"""
ATR-Based Stop Loss 止損模組

使用方法:
    from risk.atr_stop_loss import ATRStopLoss
    
    atr_sl = ATRStopLoss(period=14, multiplier=2.5, trailing=True)
    atr_values = atr_sl.calculate(df)
    stop_price = atr_sl.get_stop_loss(entry_price=100, direction='long', current_atr=2.5)
    new_stop = atr_sl.update_trailing(current_price=105, existing_stop=97.5)
"""

import pandas as pd
import numpy as np
from typing import Optional, Union


class ATRStopLoss:
    """
    ATR-Based Stop Loss 止損策略
    
    特性:
    - 使用 Average True Range 計算動態止損距離
    - 支援固定止損和移動止損 (trailing stop)
    - 多單: 止損設在進場價下方
    - 空單: 止損設在進場價上方
    """
    
    def __init__(self, period: int = 14, multiplier: float = 2.5, trailing: bool = True):
        """
        初始化 ATR 止損
        
        Args:
            period: ATR 計算週期 (預設 14)
            multiplier: ATR 倍數 (預設 2.5)
            trailing: 是否啟用移動止損 (預設 True)
        """
        self.period = period
        self.multiplier = multiplier
        self.trailing = trailing
        self._atr_cache = None
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        """
        計算 True Range 和 ATR
        
        Args:
            df: 必須包含 High, Low, Close 欄位
            
        Returns:
            ATR Series
        """
        self.validate_data(df)
        
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        # True Range = max(H-L, |H-PC|, |L-PC|)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR = TR 的週期平均
        atr = tr.rolling(window=self.period).mean()
        
        self._atr_cache = atr
        
        return atr
    
    def get_atr(self, df: pd.DataFrame) -> float:
        """
        取得最新的 ATR 值
        
        Args:
            df: 必須包含 High, Low, Close 欄位
            
        Returns:
            最新的 ATR 值
        """
        atr = self.calculate(df)
        return float(atr.iloc[-1])
    
    def get_stop_loss(self, 
                      entry_price: float, 
                      direction: str, 
                      current_atr: Optional[float] = None,
                      df: Optional[pd.DataFrame] = None) -> float:
        """
        計算止損價格
        
        Args:
            entry_price: 進場價格
            direction: 'long' 或 'short'
            current_atr: 當前 ATR 值 (如果未提供會從 df 計算)
            df: 價格數據 (用於計算 ATR)
            
        Returns:
            止損價格
        """
        if current_atr is None:
            if df is None:
                raise ValueError("必須提供 current_atr 或 df")
            current_atr = self.get_atr(df)
        
        stop_distance = current_atr * self.multiplier
        
        if direction.lower() == 'long':
            # 多單: entry_price - multiplier * ATR
            stop_price = entry_price - stop_distance
        elif direction.lower() == 'short':
            # 空單: entry_price + multiplier * ATR
            stop_price = entry_price + stop_distance
        else:
            raise ValueError(f"direction 必須是 'long' 或 'short', 收到: {direction}")
        
        return round(stop_price, 4)
    
    def update_trailing(self, 
                        current_price: float, 
                        existing_stop: float, 
                        direction: str,
                        current_atr: Optional[float] = None) -> float:
        """
        更新移動止損
        
        移動止損邏輯:
        - 多單: 如果 current_price 上漲, 提高止損 (向有利方向移動)
        - 空單: 如果 current_price 下跌, 降低止損 (向有利方向移動)
        
        Args:
            current_price: 當前價格
            existing_stop: 現有止損價格
            direction: 'long' 或 'short'
            current_atr: 當前 ATR 值
            
        Returns:
            更新後的止損價格
        """
        if not self.trailing:
            return existing_stop
        
        if current_atr is None:
            # 使用預設的 ATR 計算
            current_atr = self._atr_cache.iloc[-1] if self._atr_cache is not None else 1.0
        
        if direction.lower() == 'long':
            # 多單: 只在價格上漲時提高止損
            # 新止損 = current_price - multiplier * ATR
            # 但不能低於現有止損
            new_stop = current_price - (self.multiplier * current_atr)
            return max(existing_stop, round(new_stop, 4))
            
        elif direction.lower() == 'short':
            # 空單: 只在價格下跌時降低止損
            new_stop = current_price + (self.multiplier * current_atr)
            return min(existing_stop, round(new_stop, 4))
        else:
            raise ValueError(f"direction 必須是 'long' 或 'short', 收到: {direction}")
    
    def _get_implied_atr(self, current_price: float, stop_price: float, direction: str) -> float:
        """
        從價格差計算隱含的 ATR 值 (用於移動止損)
        """
        price_diff = abs(current_price - stop_price)
        # 假設 ATR 倍數為 multiplier
        implied_atr = price_diff / self.multiplier
        return max(implied_atr, 0.01)  # 最小 ATR 值
    
    def get_trailing_stop(self,
                          entry_price: float,
                          current_price: float,
                          direction: str,
                          current_atr: Optional[float] = None,
                          df: Optional[pd.DataFrame] = None) -> float:
        """
        計算移動止損價格 (入口方法)
        
        Args:
            entry_price: 進場價格
            current_price: 當前價格
            direction: 'long' 或 'short'
            current_atr: 當前 ATR 值
            df: 價格數據
            
        Returns:
            移動止損價格
        """
        if current_atr is None:
            if df is None:
                raise ValueError("必須提供 current_atr 或 df")
            current_atr = self.get_atr(df)
        
        # 初始止損
        initial_stop = self.get_stop_loss(entry_price, direction, current_atr)
        
        # 計算移動止損
        if self.trailing:
            return self.update_trailing(current_price, initial_stop, direction, current_atr)
        else:
            return initial_stop
    
    @staticmethod
    def validate_data(df: pd.DataFrame) -> None:
        """驗證輸入數據"""
        required_cols = ['High', 'Low', 'Close']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"缺少必要欄位: {missing}")
        
        if len(df) < 14:
            raise ValueError(f"數據長度不足，至少需要 14 筆資料，現在只有 {len(df)} 筆")


# ============ 測試 ============

if __name__ == "__main__":
    # 創建測試數據
    np.random.seed(42)
    n = 50
    
    data = {
        'High': 100 + np.cumsum(np.random.randn(n) * 2),
        'Low': 95 + np.cumsum(np.random.randn(n) * 2),
        'Close': 98 + np.cumsum(np.random.randn(n) * 2)
    }
    # 確保 High >= Close, Low <= Close
    for i in range(n):
        data['High'][i] = max(data['High'][i], data['Close'][i], data['Low'][i])
        data['Low'][i] = min(data['Low'][i], data['Close'][i], data['High'][i])
    
    df = pd.DataFrame(data)
    
    print("=" * 50)
    print("ATR Stop Loss 測試")
    print("=" * 50)
    
    # 測試 ATR 計算
    atr_sl = ATRStopLoss(period=14, multiplier=2.5, trailing=True)
    atr_values = atr_sl.calculate(df)
    current_atr = float(atr_values.iloc[-1])
    
    print(f"\n1. ATR 計算 (period={atr_sl.period})")
    print(f"   最新 ATR: {current_atr:.4f}")
    
    # 測試止損計算
    entry_price = 100.0
    direction = 'long'
    
    stop_loss = atr_sl.get_stop_loss(entry_price, direction, current_atr)
    print(f"\n2. 止損計算 (entry={entry_price}, direction={direction})")
    print(f"   multiplier: {atr_sl.multiplier}")
    print(f"   止損距離: {current_atr * atr_sl.multiplier:.4f}")
    print(f"   止損價格: {stop_loss:.4f}")
    
    # 測試空單止損
    short_stop = atr_sl.get_stop_loss(entry_price, 'short', current_atr)
    print(f"\n3. 空單止損 (entry={entry_price}, direction=short)")
    print(f"   止損價格: {short_stop:.4f}")
    
    # 測試移動止損
    current_price = 105.0
    existing_stop = stop_loss
    
    trailing_stop = atr_sl.update_trailing(current_price, existing_stop, direction)
    print(f"\n4. 移動止損 (current_price={current_price})")
    print(f"   原有止損: {existing_stop:.4f}")
    print(f"   新止損: {trailing_stop:.4f}")
    
    # 測試完整流程
    print(f"\n5. 完整流程測試")
    final_stop = atr_sl.get_trailing_stop(
        entry_price=100.0,
        current_price=105.0,
        direction='long',
        current_atr=current_atr
    )
    print(f"   最終止損: {final_stop:.4f}")
    
    print("\n" + "=" * 50)
    print("測試完成!")
    print("=" * 50)
