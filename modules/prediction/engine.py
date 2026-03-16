#!/usr/bin/env python3
"""
預測引擎 - 主預測處理模組
"""

import pandas as pd
from typing import Dict, Optional, Literal, Tuple
from datetime import datetime, timezone, timedelta
from loguru import logger
import uuid

from .calculator import ProbabilityCalculator, PredictionResult
from .factors import FactorAnalyzer


class PredictionEngine:
    """預測引擎"""
    
    def __init__(
        self,
        data_engine=None,
        weights: Optional[Dict[str, float]] = None
    ):
        """
        初始化
        
        Args:
            data_engine: 數據引擎實例 (可選)
            weights: 概率計算權重
        """
        self.data_engine = data_engine
        self.calculator = ProbabilityCalculator(weights)
        self.analyzer = FactorAnalyzer(weights)
        
        logger.info("預測引擎初始化完成")
    
    def predict(
        self,
        symbol: str,
        direction: Literal["UP", "DOWN", "VOLATILITY"],
        threshold: float = 10.0,
        period_days: int = 5
    ) -> Dict:
        """
        執行價格預測
        
        Args:
            symbol: 股票代碼 (如 TSLA, AAPL)
            direction: 預測方向
            threshold: 漲跌幅度百分比
            period_days: 預測週期 (天數)
            
        Returns:
            預測結果字典
        """
        try:
            logger.info(f"開始預測: {symbol} {direction} {threshold}% {period_days}天")
            
            # 1. 獲取價格數據
            df = self._get_price_data(symbol, period_days + 30)  # 需要更多歷史數據
            
            if df is None or len(df) < 20:
                logger.warning(f"無法獲取 {symbol} 的足夠數據")
                return self._error_response(symbol, direction, threshold, period_days, "數據不足")
            
            # 2. 因素分析
            factors = self.analyzer.analyze(df)
            logger.debug(f"因素分析結果: {factors}")
            
            # 3. 計算概率
            result = self.calculator.calculate(factors, direction, threshold, period_days)
            result.symbol = symbol
            
            # 4. 格式化輸出
            response = {
                "success": True,
                "data": {
                    "symbol": result.symbol,
                    "direction": result.direction,
                    "threshold": result.threshold,
                    "period_days": result.period_days,
                    "probability": result.probability,
                    "confidence": result.confidence,
                    "factors": result.factors,
                    "timestamp": result.timestamp,
                    "expires_at": self._get_expires_at()
                }
            }
            
            logger.info(f"預測完成: {symbol} {result.direction} 概率={result.probability:.2%} 置信度={result.confidence}")
            return response
            
        except Exception as e:
            logger.error(f"預測錯誤: {e}")
            return self._error_response(symbol, direction, threshold, period_days, str(e))
    
    def predict_from_command(self, command: str) -> Dict:
        """
        從指令格式解析並預測
        
        指令格式: 代碼/方向/幅度/時間
        範例: TSLA/📈/10/5
        
        Args:
            command: 預測指令
            
        Returns:
            預測結果
        """
        try:
            # 解析指令
            parts = command.strip().split("/")
            
            if len(parts) != 4:
                return {
                    "success": False,
                    "error": "指令格式錯誤",
                    "hint": "正確格式: 代碼/方向/幅度/時間\n範例: TSLA/📈/10/5"
                }
            
            symbol = parts[0].upper().strip()
            direction_emoji = parts[1].strip()
            threshold = float(parts[2].strip())
            period_days = int(parts[3].strip())
            
            # 解析方向
            direction = self._parse_direction(direction_emoji)
            if direction is None:
                return {
                    "success": False,
                    "error": "方向解析失敗",
                    "hint": "支持的方向: 📈 (上漲), 📉 (下跌), 📊 (波動)"
                }
            
            # 執行預測
            return self.predict(symbol, direction, threshold, period_days)
            
        except ValueError as e:
            return {
                "success": False,
                "error": f"參數解析錯誤: {e}",
                "hint": "正確格式: 代碼/幅度/時間\n範例: TSLA/10/5"
            }
        except Exception as e:
            logger.error(f"指令處理錯誤: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def batch_predict(
        self,
        symbols: list,
        direction: Literal["UP", "DOWN", "VOLATILITY"],
        threshold: float = 10.0,
        period_days: int = 5
    ) -> list:
        """
        批量預測
        
        Args:
            symbols: 股票代碼列表
            direction: 預測方向
            threshold: 漲跌幅度百分比
            period_days: 預測週期
            
        Returns:
            預測結果列表
        """
        results = []
        for symbol in symbols:
            result = self.predict(symbol, direction, threshold, period_days)
            results.append(result)
        
        logger.info(f"批量預測完成: {len(results)} 個標的")
        return results
    
    def _get_price_data(self, symbol: str, days: int) -> Optional[pd.DataFrame]:
        """獲取價格數據"""
        if self.data_engine:
            return self.data_engine.get_daily_data(symbol, period=f"{days}d")

        # yfinance / Yahoo Finance 已移除 (2026-03-06)
        # 改用富途數據：從 MySQL kline_cache 讀取（由 scripts/futu_polling.py 維護）
        # 若無數據引擎，嘗試直接從 MySQL 讀取
        try:
            import sys, os
            from pathlib import Path
            proj_root = str(Path(__file__).parent.parent.parent)
            if proj_root not in sys.path:
                sys.path.insert(0, proj_root)
            from config.database import get_db_connection
            import pandas as pd
            from datetime import datetime, timedelta
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            futu_symbol = f"US.{symbol}" if not symbol.startswith("US.") else symbol
            with get_db_connection() as conn:
                df = pd.read_sql(
                    "SELECT timestamp, open_price AS Open, high_price AS High, "
                    "low_price AS Low, close_price AS Close, volume AS Volume "
                    "FROM kline_cache WHERE symbol = %s AND interval_val = '1d' "
                    "AND timestamp >= %s ORDER BY timestamp",
                    conn, params=(futu_symbol, start_date),
                    index_col='timestamp', parse_dates=['timestamp']
                )
            
            if df is None or df.empty:
                logger.warning(f"⚠️ {symbol}: 無法從 kline_cache 獲取數據（數據庫為空）")
                return None
            
            # 檢查數據可用性
            if len(df) < 20:
                logger.warning(f"⚠️ {symbol}: 數據不足 {len(df)} 條（需要至少 20 條）")
                return None
            
            logger.info(f"✅ {symbol}: 成功獲取 {len(df)} 條 K 線數據")
            return df
            
        except Exception as e:
            logger.error(f"⚠️ {symbol}: 獲取數據失敗 - {str(e)}")
            return None
    
    def _parse_direction(self, emoji: str) -> Optional[str]:
        """解析方向 emoji"""
        direction_map = {
            "📈": "UP",
            "📉": "DOWN",
            "📊": "VOLATILITY",
            "↑": "UP",
            "↓": "DOWN",
            "~": "VOLATILITY",
            "UP": "UP",
            "DOWN": "DOWN",
            "VOLATILITY": "VOLATILITY"
        }
        return direction_map.get(emoji.upper())
    
    def _get_expires_at(self) -> str:
        """計算過期時間"""
        expires = datetime.now(timezone.utc) + timedelta(hours=4)
        return expires.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def _error_response(
        self,
        symbol: str,
        direction: str,
        threshold: float,
        period_days: int,
        error: str
    ) -> Dict:
        """返回錯誤響應"""
        return {
            "success": False,
            "error": error,
            "data": {
                "symbol": symbol,
                "direction": direction,
                "threshold": threshold,
                "period_days": period_days,
                "probability": None,
                "confidence": "LOW",
                "factors": None,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "error": error
            }
        }
    
    def get_statistics(self) -> Dict:
        """獲取引擎統計"""
        return {
            "weights": self.calculator.get_weights_info(),
            "analyzer_type": type(self.analyzer).__name__
        }
