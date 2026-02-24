# Technical Indicators - ADX (Average Directional Index)
# 實現標準 Wilder's Smoothing ADX 計算

import pandas as pd
import numpy as np


def wilder_smoothing(series: pd.Series, period: int) -> pd.Series:
    """
    Wilder's Smoothing (Wilder's EMA)
    公式: smoothed[t] = (smoothed[t-1] * (period-1) + value[t]) / period
    這等同於 EMA with alpha = 1/period
    """
    alpha = 1.0 / period
    return series.ewm(alpha=alpha, adjust=False).mean()


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    標準 ADX 計算 (Wilder's Smoothing)
    
    Step 1: True Range (TR)
        TR = max(High - Low, |High - PrevClose|, |Low - PrevClose|)
    
    Step 2: Directional Movement (+DM, -DM)
        +DM = High - PrevHigh (若 >0 且 > -DM，否則 0)
        -DM = PrevLow - Low (若 >0 且 > +DM，否則 0)
    
    Step 3: Directional Indicators (+DI14, -DI14)
        +DI14 = 100 × Smoothed(+DM14) / Smoothed(TR14)
        -DI14 = 100 × Smoothed(-DM14) / Smoothed(TR14)
    
    Step 4: DX
        DX = 100 × |+DI14 - -DI14| / (+DI14 + -DI14)
    
    Step 5: ADX
        ADX = Smoothed(DX14)  // 使用 Wilder's smoothing
    """
    # 確保必要的列存在
    required_cols = ['High', 'Low', 'Close']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame must contain {required_cols}")
    
    df = df.copy()
    
    # 轉換為數值
    df['High'] = pd.to_numeric(df['High'], errors='coerce')
    df['Low'] = pd.to_numeric(df['Low'], errors='coerce')
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    
    # Step 1: True Range (TR)
    prev_close = df['Close'].shift(1)
    tr1 = df['High'] - df['Low']           # High - Low
    tr2 = (df['High'] - prev_close).abs()  # |High - PrevClose|
    tr3 = (df['Low'] - prev_close).abs()   # |Low - PrevClose|
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Step 2: Directional Movement (+DM, -DM)
    high_diff = df['High'] - df['High'].shift(1)  # High - PrevHigh
    low_diff = df['Low'].shift(1) - df['Low']      # PrevLow - Low
    
    # +DM: 只取正值，且必須大於 -DM
    plus_dm = high_diff.where((high_diff > 0) & (high_diff > low_diff), 0)
    
    # -DM: 只取正值，且必須大於 +DM  
    minus_dm = low_diff.where((low_diff > 0) & (low_diff > high_diff), 0)
    
    # Step 3: Wilder's Smoothing for TR, +DM, -DM
    # 初始值使用 SMA，後續使用 Wilder's smoothing
    smoothed_tr = wilder_smoothing(tr, period)
    smoothed_plus_dm = wilder_smoothing(plus_dm, period)
    smoothed_minus_dm = wilder_smoothing(minus_dm, period)
    
    # 避免除零
    smoothed_tr = smoothed_tr.replace(0, np.nan)
    
    # +DI14, -DI14
    plus_di = 100 * smoothed_plus_dm / smoothed_tr
    minus_di = 100 * smoothed_minus_dm / smoothed_tr
    
    # Step 4: DX
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100 * di_diff / di_sum
    
    # Step 5: ADX (Wilder's smoothing of DX)
    adx = wilder_smoothing(dx, period)
    
    # 填充 NaN
    result = pd.DataFrame({
        'ADX': adx.fillna(0),
        'PLUS_DI': plus_di.fillna(0),
        'MINUS_DI': minus_di.fillna(0),
        'TR': tr,
        'ATR': smoothed_tr  # 14-period ATR (byproduct)
    })
    
    return result


def calculate_adx_simple(df: pd.DataFrame, period: int = 14) -> dict:
    """
    簡化版 ADX 計算，返回最新值
    適用於只需要當前 ADX 值的場景
    """
    adx_data = calculate_adx(df, period)
    
    return {
        'adx': adx_data['ADX'].iloc[-1] if len(adx_data) > 0 else 0,
        'plus_di': adx_data['PLUS_DI'].iloc[-1] if len(adx_data) > 0 else 0,
        'minus_di': adx_data['MINUS_DI'].iloc[-1] if len(adx_data) > 0 else 0,
        'atr': adx_data['ATR'].iloc[-1] if len(adx_data) > 0 else 0,
    }
