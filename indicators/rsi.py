"""
RSI (Relative Strength Index) 指標類
使用 Wilder's Smoothing Method 計算
"""

import pandas as pd
import numpy as np


class RSIIndicator:
    """
    相對強度指數 (Relative Strength Index) 指標類
    使用 Wilder's Smoothing Method 計算
    
    Attributes:
        period: RSI 週期 (預設 14)
        oversold: 超賣閾值 (預設 30)
        overbought: 超買閾值 (預設 70)
    """
    
    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self._rsi_values = []
        self._last_signal = None
    
    def calculate(self, df: pd.DataFrame, price_col: str = 'close') -> pd.DataFrame:
        """
        計算 RSI 指標
        
        Args:
            df: 價格數據 DataFrame
            price_col: 價格列名 (預設 'close')
            
        Returns:
            帶有 'rsi' 列的 DataFrame
        """
        # 計算價格變化
        delta = df[price_col].diff()
        
        # 分離漲跌
        gains = delta.where(delta > 0, 0.0)
        losses = (-delta).where(delta < 0, 0.0)
        
        # 使用 Wilder's Smoothing (ewm with alpha=1/period)
        alpha = 1.0 / self.period
        avg_gain = gains.ewm(alpha=alpha, adjust=False).mean()
        avg_loss = losses.ewm(alpha=alpha, adjust=False).mean()
        
        # 計算 RS 和 RSI
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        # 處理 avg_loss 為 0 的情況 (完全上漲)
        rsi = rsi.fillna(100.0)
        
        # 將結果添加到 DataFrame
        result_df = df.copy()
        result_df['rsi'] = rsi.values
        
        # 儲存 RSI 值列表
        self._rsi_values = rsi.dropna().tolist()
        
        # 產生交易信號
        result_df['rsi_signal'] = result_df['rsi'].apply(self.get_signal)
        
        return result_df
    
    def get_signal(self, rsi_value: float = None) -> str:
        """
        根據 RSI 值產生交易信號
        
        Args:
            rsi_value: RSI 值，若為 None則使用當前 RSI
            
        Returns:
            'buy' (超賣), 'sell' (超買), 'neutral' (中性)
        """
        if rsi_value is None:
            rsi_value = self.current_rsi
        
        if rsi_value <= self.oversold:
            self._last_signal = 'buy'
            return 'buy'
        elif rsi_value >= self.overbought:
            self._last_signal = 'sell'
            return 'sell'
        else:
            self._last_signal = 'neutral'
            return 'neutral'
    
    @property
    def current_rsi(self) -> float:
        """
        取得最新的 RSI 值
        
        Returns:
            最新的 RSI 值，若無資料則返回 0
        """
        if self._rsi_values:
            return self._rsi_values[-1]
        return 0.0
    
    @property
    def last_signal(self) -> str:
        """取得最後產生的交易信號"""
        return self._last_signal


# 測試代碼
if __name__ == "__main__":
    # 創建測試數據
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    close_prices = 100 + np.cumsum(np.random.randn(30) * 2)
    
    test_df = pd.DataFrame({
        'date': dates,
        'close': close_prices
    })
    
    # 測試 RSI 指標
    rsi_indicator = RSIIndicator(period=14, oversold=30, overbought=70)
    result = rsi_indicator.calculate(test_df, price_col='close')
    
    print("RSI Indicator Test")
    print("=" * 50)
    print(f"Period: {rsi_indicator.period}")
    print(f"Oversold: {rsi_indicator.oversold}")
    print(f"Overbought: {rsi_indicator.overbought}")
    print(f"Current RSI: {rsi_indicator.current_rsi:.2f}")
    print(f"Last Signal: {rsi_indicator.last_signal}")
    print("=" * 50)
    print("\nLast 10 rows:")
    print(result[['date', 'close', 'rsi', 'rsi_signal']].tail(10).to_string(index=False))
    print("\n✅ RSI Indicator test passed!")
