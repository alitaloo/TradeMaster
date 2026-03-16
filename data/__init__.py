# Data module - 本地數據 + MySQL K線快取（富途數據）
# 2026-03-06: 已移除 yfinance / Yahoo Finance 依賴，改用富途數據
# - 日線 CSV: data/historical/
# - 即時/歷史 K線: MySQL kline_cache 表（由 futu_polling.py 維護）
# - 富途 SDK: 見 api/futu_kline.py 及 scripts/backfill_futu_kline_mysql.py

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import logging
import sys
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 導入 MySQL 配置
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from config.database import get_db_connection
    _MYSQL_AVAILABLE = True
except ImportError:
    _MYSQL_AVAILABLE = False


class DataEngine:
    """數據引擎 - 優先本地 CSV，次選 MySQL kline_cache（富途數據）"""

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
        """獲取日線數據（本地 CSV → MySQL kline_cache）"""
        try:
            # 優先從本地 CSV 讀取
            local_data = self._load_local_data(symbol)
            if local_data is not None and not local_data.empty:
                if start_date:
                    local_data = local_data[local_data.index >= pd.to_datetime(start_date)]
                if end_date:
                    local_data = local_data[local_data.index <= pd.to_datetime(end_date)]
                if not local_data.empty:
                    logger.info(f"使用本地數據: {symbol} ({len(local_data)} rows)")
                    return local_data

            # 次選 MySQL kline_cache（由富途 SDK 寫入）
            mysql_data = self._load_mysql_data(symbol, interval, start_date, end_date)
            if mysql_data is not None and not mysql_data.empty:
                logger.info(f"使用 MySQL kline_cache: {symbol} ({len(mysql_data)} rows)")
                return mysql_data

            # 無數據可用，不再使用 yfinance/Yahoo Finance
            logger.warning(
                f"無本地或 MySQL 數據: {symbol}。"
                f"請執行 scripts/backfill_futu_kline_mysql.py 補充富途歷史數據。"
            )
            return None

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    def _load_local_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """從本地 CSV 加載數據"""
        try:
            filepath = Path(self.cache_dir) / f"{symbol}.csv"
            if filepath.exists():
                df = pd.read_csv(filepath)

                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'])
                    df = df.set_index('Date')
                elif df.index.name and df.index.name != '':
                    df.index = pd.to_datetime(df.index)

                if not isinstance(df.index, pd.DatetimeIndex):
                    return None

                cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                if all(c in df.columns for c in cols):
                    df = df[cols]

                return df
            return None
        except Exception as e:
            logger.error(f"Error loading local data for {symbol}: {e}")
            return None

    def _load_mysql_data(
        self,
        symbol: str,
        interval: str = "1d",
        start_date: str = None,
        end_date: str = None
    ) -> Optional[pd.DataFrame]:
        """從 MySQL kline_cache 加載數據（富途數據）"""
        if not _MYSQL_AVAILABLE:
            return None
        try:
            # 富途代碼格式: US.AAPL
            futu_symbol = f"US.{symbol}" if not symbol.startswith("US.") else symbol

            conditions = ["symbol = %s", "interval_val = %s"]
            params = [futu_symbol, interval]

            if start_date:
                conditions.append("timestamp >= %s")
                params.append(start_date)
            if end_date:
                conditions.append("timestamp <= %s")
                params.append(end_date)

            query = (
                "SELECT timestamp, open_price AS Open, high_price AS High, "
                "low_price AS Low, close_price AS Close, volume AS Volume "
                f"FROM kline_cache WHERE {' AND '.join(conditions)} ORDER BY timestamp"
            )

            with get_db_connection() as conn:
                df = pd.read_sql(query, conn, params=params,
                                 index_col='timestamp', parse_dates=['timestamp'])
            return df if not df.empty else None
        except Exception as e:
            logger.debug(f"MySQL kline_cache load failed for {symbol}: {e}")
            return None

    def get_intraday_data(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """獲取分時數據（從 MySQL kline_cache，富途數據）"""
        # 計算 start_date
        days_map = {"1d": 1, "5d": 5, "1mo": 30}
        days = days_map.get(period, 1)
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        return self._load_mysql_data(symbol, interval, start_date=start_date)

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
        """獲取市場指數（從 MySQL kline_cache 最新收盤價）
        注意: 指數數據需富途訂閱支援，若無數據請通過富途 SDK 補充。
        """
        # 已移除 yfinance 調用，富途數據由 futu_polling.py 維護
        indices = {"SPY": "US.SPY", "QQQ": "US.QQQ", "DIA": "US.DIA", "IWM": "US.IWM"}
        results = {}

        if not _MYSQL_AVAILABLE:
            return results

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                for name, futu_code in indices.items():
                    cursor.execute(
                        "SELECT close_price FROM kline_cache "
                        "WHERE symbol = %s AND interval_val = '1d' "
                        "ORDER BY timestamp DESC LIMIT 1",
                        (futu_code,)
                    )
                    row = cursor.fetchone()
                    if row:
                        results[name] = float(row['close_price'])
        except Exception as e:
            logger.debug(f"get_market_indices failed: {e}")

        return results

    def get_market_status(self) -> Dict:
        """檢查市場狀態"""
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()

        is_trading = (
            weekday < 5 and
            (hour >= 14 or (hour >= 9 and hour < 4))
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
        df = df.dropna()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna()
        return df


class DataCache:
    """數據緩存"""

    def __init__(self, ttl: int = 300):
        self.cache = {}
        self.ttl = ttl

    def get(self, key: str) -> Optional[pd.DataFrame]:
        if key in self.cache:
            data, timestamp = self.cache[key]
            if (datetime.now() - timestamp).seconds < self.ttl:
                return data
            del self.cache[key]
        return None

    def set(self, key: str, data: pd.DataFrame):
        self.cache[key] = (data, datetime.now())

    def clear(self):
        self.cache.clear()


class DataStorage:
    """數據持久化存儲"""

    def __init__(self, storage_dir: str = "data/historical"):
        os.makedirs(storage_dir, exist_ok=True)
        self.storage_dir = storage_dir

    def save_data(self, symbol: str, df: pd.DataFrame, data_type: str = "daily"):
        """保存數據"""
        import gzip
        filename = f"{self.storage_dir}/{symbol}_{data_type}.csv.gz"
        df.to_csv(filename, compression='gzip')
        logger.info(f"Saved {symbol} data to {filename}")

    def load_data(self, symbol: str, data_type: str = "daily") -> Optional[pd.DataFrame]:
        """加載數據"""
        filename = f"{self.storage_dir}/{symbol}_{data_type}.csv.gz"
        try:
            return pd.read_csv(filename, index_col=0, parse_dates=True)
        except Exception:
            return None
