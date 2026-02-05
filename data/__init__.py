# Data module - Yahoo Finance data fetching (with local cache support)

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DataEngine:
    """數據引擎"""

    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or str(Path(__file__).parent / "historical")
        self.cache = {}
    
    def get_daily_data(
        self,
        symbol: str,
        period: str = "3mo",
        interval: str = "1d",
        start_date: str = None,
        end_date: str = None
    ) -> Optional[pd.DataFrame]:
        """獲取日線數據"""
        try:
            # 首先嘗試從本地讀取
            local_data = self._load_local_data(symbol)
            if local_data is not None and not local_data.empty:
                logger.info(f"使用本地數據: {symbol} ({len(local_data)} rows)")
                return local_data

            # 如果本地沒有，再從 yfinance 獲取
            logger.warning(f"本地無 {symbol} 數據，嘗試 yfinance...")
            ticker = yf.Ticker(symbol)

            if start_date and end_date:
                df = ticker.history(
                    start=start_date,
                    end=end_date,
                    interval=interval
                )
            else:
                df = ticker.history(period=period, interval=interval)

            if df.empty:
                logger.warning(f"No data for {symbol}")
                return None

            # 數據清洗
            df = self._clean_data(df)

            return df

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    def _load_local_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """從本地 CSV 加載數據"""
        try:
            filepath = Path(self.cache_dir) / f"{symbol}.csv"
            if filepath.exists():
                df = pd.read_csv(filepath, index_col=0, parse_dates=True)
                # 確保是 DatetimeIndex
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                return df
            return None
        except Exception as e:
            logger.error(f"Error loading local data for {symbol}: {e}")
            return None
    
    def get_intraday_data(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """獲取分時數據"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                return None
            
            return self._clean_data(df)
            
        except Exception as e:
            logger.error(f"Error fetching intraday {symbol}: {e}")
            return None
    
    def get_batch_data(
        self,
        symbols: List[str],
        period: str = "3mo",
        interval: str = "1d",
        max_workers: int = 5
    ) -> Dict[str, pd.DataFrame]:
        """批量獲取多標的數據"""
        results = {}
        
        def fetch_one(symbol):
            return symbol, self.get_daily_data(symbol, period, interval)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(fetch_one, s) for s in symbols]
            for future in futures:
                symbol, df = future.result()
                if df is not None:
                    results[symbol] = df
        
        return results
    
    def get_market_indices(self) -> Dict[str, float]:
        """獲取市場指數"""
        indices = {
            "SPY": "^GSPC",  # S&P 500
            "QQQ": "^IXIC",  # NASDAQ
            "DIA": "^DJI",   # Dow Jones
            "IWM": "^RUT"    # Russell 2000
        }
        
        results = {}
        for name, symbol in indices.items():
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="1d")
                if not df.empty:
                    results[name] = df["Close"].iloc[-1]
            except:
                pass
        
        return results
    
    def get_market_status(self) -> Dict:
        """檢查市場狀態"""
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()
        
        # 紐約時間 (UTC-5/4)
        # 交易時段: 9:30 - 16:00 ET, Mon-Fri
        
        is_trading = (
            weekday < 5 and
            (hour >= 14 or (hour >= 9 and hour < 4))  # UTC 14:00 = 9:30 ET
        )
        
        is_pre_market = (
            weekday < 5 and
            ((hour >= 9 and hour < 14) or (hour >= 0 and hour < 4))
        )
        
        return {
            "is_trading": is_trading,
            "is_pre_market": is_pre_market,
            "timestamp": now.isoformat(),
            "hour_utc": hour,
            "weekday": weekday
        }
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗數據"""
        # 移除無效數據
        df = df.dropna()
        
        # 確保數據類型正確
        df["Open"] = pd.to_numeric(df["Open"], errors='coerce')
        df["High"] = pd.to_numeric(df["High"], errors='coerce')
        df["Low"] = pd.to_numeric(df["Low"], errors='coerce')
        df["Close"] = pd.to_numeric(df["Close"], errors='coerce')
        df["Volume"] = pd.to_numeric(df["Volume"], errors='coerce')
        
        # 再次清理
        df = df.dropna()
        
        return df


class DataCache:
    """數據緩存"""
    
    def __init__(self, ttl: int = 300):  # 5分鐘
        self.cache = {}
        self.ttl = ttl
    
    def get(self, key: str) -> Optional[pd.DataFrame]:
        """獲取緩存"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if (datetime.now() - timestamp).seconds < self.ttl:
                return data
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, data: pd.DataFrame):
        """設置緩存"""
        self.cache[key] = (data, datetime.now())
    
    def clear(self):
        """清空緩存"""
        self.cache.clear()


class DataStorage:
    """數據持久化存儲"""
    
    def __init__(self, storage_dir: str = "data/historical"):
        import os
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
    
    def save_data(
        self, 
        symbol: str, 
        df: pd.DataFrame,
        data_type: str = "daily"
    ):
        """保存數據"""
        import gzip
        
        filename = f"{self.storage_dir}/{symbol}_{data_type}.csv.gz"
        df.to_csv(filename, compression='gzip')
        logger.info(f"Saved {symbol} data to {filename}")
    
    def load_data(
        self, 
        symbol: str, 
        data_type: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """加載數據"""
        import gzip
        
        filename = f"{self.storage_dir}/{symbol}_{data_type}.csv.gz"
        try:
            return pd.read_csv(filename, index_col=0, parse_dates=True)
        except:
            return None
