# MySQL Logger - 記錄回測結果到 MySQL

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
import json

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.database import get_db_cursor, get_connection

logger = logging.getLogger(__name__)


@dataclass
class StrategyRecord:
    """策略記錄"""
    symbol: str
    timeframe: str
    indicator: str
    params: Dict[str, Any]
    sharpe: float
    return_pct: float
    win_rate: float
    trades: int
    id: int = None
    created_at: datetime = None
    updated_at: datetime = None


class MySQLStrategyLogger:
    """MySQL 策略記錄器"""
    
    TABLE_NAME = "stock_strategies"
    
    def __init__(self):
        self._ensure_table()
    
    def _ensure_table(self):
        """確保表存在"""
        try:
            with get_db_cursor(dictionary=False) as cursor:
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        symbol VARCHAR(20) NOT NULL,
                        timeframe VARCHAR(5) NOT NULL,
                        indicator VARCHAR(50) NOT NULL,
                        params LONGTEXT,
                        sharpe DECIMAL(10,4),
                        return_pct DECIMAL(10,4),
                        win_rate DECIMAL(5,4),
                        trades INT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_symbol (symbol),
                        INDEX idx_indicator (indicator),
                        INDEX idx_sharpe (sharpe)
                    )
                """)
            logger.info(f"Table {self.TABLE_NAME} ensured")
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
    
    def save(
        self,
        symbol: str,
        timeframe: str,
        indicator: str,
        params: Dict[str, Any] = None,
        sharpe: float = None,
        return_pct: float = None,
        win_rate: float = None,
        trades: int = None
    ) -> int:
        """保存或更新策略記錄"""
        params_json = json.dumps(params, ensure_ascii=False) if params else None
        
        try:
            with get_db_cursor(dictionary=False) as cursor:
                query = f"""
                    INSERT INTO {self.TABLE_NAME}
                    (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    sharpe = VALUES(sharpe),
                    return_pct = VALUES(return_pct),
                    win_rate = VALUES(win_rate),
                    trades = VALUES(trades),
                    params = VALUES(params),
                    updated_at = NOW()
                """
                cursor.execute(query, (
                    symbol,
                    timeframe,
                    indicator,
                    params_json,
                    sharpe,
                    return_pct,
                    win_rate,
                    trades
                ))
                
                # 獲取插入/更新的 ID
                cursor.execute("SELECT LAST_INSERT_ID()")
                result = cursor.fetchone()
                return result[0] if result else None
                
        except Exception as e:
            logger.error(f"Failed to save strategy record: {e}")
            raise
    
    def save_batch(self, records: List[Dict]) -> int:
        """批量保存記錄"""
        if not records:
            return 0
        
        count = 0
        for record in records:
            try:
                self.save(
                    symbol=record.get("symbol"),
                    timeframe=record.get("timeframe"),
                    indicator=record.get("strategy_name") or record.get("indicator"),
                    params=record.get("params"),
                    sharpe=record.get("sharpe_ratio") or record.get("sharpe"),
                    return_pct=record.get("total_return") or record.get("return_pct"),
                    win_rate=record.get("win_rate"),
                    trades=record.get("total_trades") or record.get("trades")
                )
                count += 1
            except Exception as e:
                logger.error(f"Failed to save record: {e}")
        
        return count
    
    def get(
        self,
        symbol: str = None,
        timeframe: str = None,
        indicator: str = None,
        min_sharpe: float = None,
        limit: int = 100
    ) -> List[StrategyRecord]:
        """獲取策略記錄"""
        conditions = []
        params = []
        
        if symbol:
            conditions.append("symbol = %s")
            params.append(symbol)
        
        if timeframe:
            conditions.append("timeframe = %s")
            params.append(timeframe)
        
        if indicator:
            conditions.append("indicator = %s")
            params.append(indicator)
        
        if min_sharpe is not None:
            conditions.append("sharpe >= %s")
            params.append(min_sharpe)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        query = f"""
            SELECT * FROM {self.TABLE_NAME}
            {where_clause}
            ORDER BY sharpe DESC
            LIMIT %s
        """
        params.append(limit)
        
        try:
            with get_db_cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                records = []
                for row in rows:
                    params_dict = None
                    if row.get("params"):
                        try:
                            params_dict = json.loads(row["params"])
                        except:
                            pass
                    
                    records.append(StrategyRecord(
                        id=row["id"],
                        symbol=row["symbol"],
                        timeframe=row["timeframe"],
                        indicator=row["indicator"],
                        params=params_dict,
                        sharpe=float(row["sharpe"]) if row["sharpe"] else None,
                        return_pct=float(row["return_pct"]) if row["return_pct"] else None,
                        win_rate=float(row["win_rate"]) if row["win_rate"] else None,
                        trades=row["trades"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"]
                    ))
                
                return records
                
        except Exception as e:
            logger.error(f"Failed to get strategy records: {e}")
            return []
    
    def get_best_strategies(
        self,
        symbol: str = None,
        timeframe: str = None,
        top_n: int = 10
    ) -> List[StrategyRecord]:
        """獲取最佳策略"""
        conditions = []
        params = []
        
        if symbol:
            conditions.append("symbol = %s")
            params.append(symbol)
        
        if timeframe:
            conditions.append("timeframe = %s")
            params.append(timeframe)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        query = f"""
            SELECT * FROM {self.TABLE_NAME}
            {where_clause}
            ORDER BY sharpe DESC
            LIMIT %s
        """
        params.append(top_n)
        
        try:
            with get_db_cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                records = []
                for row in rows:
                    params_dict = None
                    if row.get("params"):
                        try:
                            params_dict = json.loads(row["params"])
                        except:
                            pass
                    
                    records.append(StrategyRecord(
                        id=row["id"],
                        symbol=row["symbol"],
                        timeframe=row["timeframe"],
                        indicator=row["indicator"],
                        params=params_dict,
                        sharpe=float(row["sharpe"]) if row["sharpe"] else None,
                        return_pct=float(row["return_pct"]) if row["return_pct"] else None,
                        win_rate=float(row["win_rate"]) if row["win_rate"] else None,
                        trades=row["trades"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"]
                    ))
                
                return records
                
        except Exception as e:
            logger.error(f"Failed to get best strategies: {e}")
            return []
    
    def delete(
        self,
        symbol: str = None,
        timeframe: str = None,
        indicator: str = None
    ) -> int:
        """刪除記錄"""
        conditions = []
        params = []
        
        if symbol:
            conditions.append("symbol = %s")
            params.append(symbol)
        
        if timeframe:
            conditions.append("timeframe = %s")
            params.append(timeframe)
        
        if indicator:
            conditions.append("indicator = %s")
            params.append(indicator)
        
        if not conditions:
            logger.warning("No conditions specified for delete")
            return 0
        
        where_clause = f"WHERE {' AND '.join(conditions)}"
        
        try:
            with get_db_cursor(dictionary=False) as cursor:
                cursor.execute(f"DELETE FROM {self.TABLE_NAME} {where_clause}", params)
                return cursor.rowcount
                
        except Exception as e:
            logger.error(f"Failed to delete records: {e}")
            return 0
    
    def clear_all(self) -> int:
        """清空所有記錄"""
        try:
            with get_db_cursor(dictionary=False) as cursor:
                cursor.execute(f"DELETE FROM {self.TABLE_NAME}")
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to clear records: {e}")
            return 0
    
    def get_stats(self) -> Dict:
        """獲取統計信息"""
        query = f"""
            SELECT 
                COUNT(*) as total,
                AVG(sharpe) as avg_sharpe,
                AVG(return_pct) as avg_return,
                AVG(win_rate) as avg_win_rate,
                SUM(trades) as total_trades
            FROM {self.TABLE_NAME}
        """
        
        try:
            with get_db_cursor() as cursor:
                cursor.execute(query)
                row = cursor.fetchone()
                
                return {
                    "total_records": row["total"] or 0,
                    "avg_sharpe": float(row["avg_sharpe"]) if row["avg_sharpe"] else 0,
                    "avg_return": float(row["avg_return"]) if row["avg_return"] else 0,
                    "avg_win_rate": float(row["avg_win_rate"]) if row["avg_win_rate"] else 0,
                    "total_trades": row["total_trades"] or 0
                }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


# 便捷函數
_logger = None


def get_strategy_logger() -> MySQLStrategyLogger:
    """獲取策略日誌記錄器單例"""
    global _logger
    if _logger is None:
        _logger = MySQLStrategyLogger()
    return _logger


def save_strategy_result(
    symbol: str,
    timeframe: str,
    indicator: str,
    params: Dict = None,
    sharpe: float = None,
    return_pct: float = None,
    win_rate: float = None,
    trades: int = None
) -> int:
    """便捷函數：保存策略結果"""
    return get_strategy_logger().save(
        symbol=symbol,
        timeframe=timeframe,
        indicator=indicator,
        params=params,
        sharpe=sharpe,
        return_pct=return_pct,
        win_rate=win_rate,
        trades=trades
    )


def get_best_strategies(
    symbol: str = None,
    timeframe: str = None,
    top_n: int = 10
) -> List[StrategyRecord]:
    """便捷函數：獲取最佳策略"""
    return get_strategy_logger().get_best_strategies(
        symbol=symbol,
        timeframe=timeframe,
        top_n=top_n
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    logger = MySQLStrategyLogger()
    
    # 測試統計
    stats = logger.get_stats()
    print(f"Stats: {stats}")
    
    # 測試獲取最佳策略
    best = logger.get_best_strategies(symbol="2330.TW", top_n=5)
    print(f"\nBest strategies for 2330.TW:")
    for s in best:
        print(f"  {s.indicator}: Sharpe={s.sharpe}, Return={s.return_pct}%")
