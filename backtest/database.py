# BacktestDB - MySQL 數據庫記錄
# 記錄回測結果到 stock_strategies 表

import sys
import logging
from typing import Dict, List, Optional
from datetime import datetime
import json

import pymysql

logger = logging.getLogger(__name__)


class BacktestDB:
    """MySQL 回測結果數據庫操作"""
    
    def __init__(self, host='localhost', user='alita', password='alitamysql', database='trademaster'):
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database,
            'charset': 'utf8mb4',
            'cursorclass': pymysql.cursors.DictCursor
        }
        self._connection = None
    
    def _get_connection(self):
        """獲取數據庫連接"""
        if self._connection is None or not self._connection.open:
            self._connection = pymysql.connect(**self.config)
        return self._connection
    
    def close(self):
        """關閉數據庫連接"""
        if self._connection and self._connection.open:
            self._connection.close()
            self._connection = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def save_strategy_result(
        self,
        symbol: str,
        timeframe: str,
        indicator: str,
        params: dict,
        sharpe: float = None,
        return_pct: float = None,
        win_rate: float = None,
        trades: int = None,
        batch_id: str = None,
        score: float = None,
        selection_rule: dict = None,
    ) -> Optional[int]:
        """保存策略回測結果到 stock_strategies 表（部署用 best mapping）"""
        conn = self._get_connection()

        sql = """
            INSERT INTO stock_strategies 
            (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades, batch_id, score, selection_rule, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                indicator = VALUES(indicator),
                params = VALUES(params),
                sharpe = VALUES(sharpe),
                return_pct = VALUES(return_pct),
                win_rate = VALUES(win_rate),
                trades = VALUES(trades),
                batch_id = VALUES(batch_id),
                score = VALUES(score),
                selection_rule = VALUES(selection_rule),
                updated_at = NOW()
        """

        params_json = json.dumps(params or {}, ensure_ascii=False)
        selection_rule_json = json.dumps(selection_rule or {}, ensure_ascii=False) if selection_rule is not None else None

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        symbol,
                        timeframe,
                        indicator,
                        params_json,
                        sharpe,
                        return_pct,
                        win_rate,
                        trades,
                        batch_id,
                        score,
                        selection_rule_json,
                    ),
                )
                conn.commit()

                # 獲取插入的 ID
                return cursor.lastrowid if cursor.lastrowid else cursor.rowcount

        except Exception as e:
            logger.error(f"Failed to save strategy result: {e}")
            conn.rollback()
            return None
    
    def save_batch_results(self, results: List[Dict]) -> int:
        """批量保存策略結果"""
        saved_count = 0
        
        for result in results:
            success = self.save_strategy_result(
                symbol=result.get('symbol'),
                timeframe=result.get('timeframe', '1d'),
                indicator=result.get('strategy', result.get('indicator', 'Unknown')),
                params=result.get('params', {}),
                sharpe=result.get('sharpe'),
                return_pct=result.get('return_pct'),
                win_rate=result.get('win_rate'),
                trades=result.get('trades')
            )
            if success:
                saved_count += 1
        
        return saved_count
    
    def get_strategy_results(
        self,
        symbol: str = None,
        indicator: str = None,
        min_sharpe: float = None,
        min_return: float = None,
        limit: int = 100
    ) -> List[Dict]:
        """查詢策略結果"""
        conn = self._get_connection()
        
        conditions = []
        params = []
        
        if symbol:
            conditions.append("symbol = %s")
            params.append(symbol)
        
        if indicator:
            conditions.append("indicator = %s")
            params.append(indicator)
        
        if min_sharpe is not None:
            conditions.append("sharpe >= %s")
            params.append(min_sharpe)
        
        if min_return is not None:
            conditions.append("return_pct >= %s")
            params.append(min_return)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        sql = f"""
            SELECT * FROM stock_strategies
            WHERE {where_clause}
            ORDER BY sharpe DESC, return_pct DESC
            LIMIT %s
        """
        params.append(limit)
        
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()
                
                # 解析 JSON 參數
                for row in results:
                    if row.get('params') and isinstance(row['params'], str):
                        try:
                            row['params'] = json.loads(row['params'])
                        except:
                            pass
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to query strategy results: {e}")
            return []
    
    def get_best_strategies(
        self,
        symbol: str = None,
        top_n: int = 10,
        min_sharpe: float = None
    ) -> List[Dict]:
        """獲取最佳策略"""
        conn = self._get_connection()
        
        conditions = []
        params = []
        
        if symbol:
            conditions.append("symbol = %s")
            params.append(symbol)
        
        if min_sharpe is not None:
            conditions.append("sharpe >= %s")
            params.append(min_sharpe)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        sql = f"""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY symbol, indicator ORDER BY sharpe DESC) as rn
                FROM stock_strategies
                WHERE {where_clause}
            ) ranked
            WHERE rn <= %s
            ORDER BY sharpe DESC
        """
        params.append(top_n)
        
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()
                
                for row in results:
                    if row.get('params') and isinstance(row['params'], str):
                        try:
                            row['params'] = json.loads(row['params'])
                        except:
                            pass
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to query best strategies: {e}")
            return []
    
    def delete_old_results(self, days: int = 90) -> int:
        """刪除舊的策略結果"""
        conn = self._get_connection()
        
        sql = """
            DELETE FROM stock_strategies 
            WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)
        """
        
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (days,))
                conn.commit()
                return cursor.rowcount
                
        except Exception as e:
            logger.error(f"Failed to delete old results: {e}")
            return 0
    
    def get_table_stats(self) -> Dict:
        """獲取表統計信息"""
        conn = self._get_connection()
        
        sql = """
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT symbol) as unique_symbols,
                COUNT(DISTINCT indicator) as unique_strategies,
                AVG(sharpe) as avg_sharpe,
                MAX(sharpe) as max_sharpe,
                AVG(return_pct) as avg_return,
                MAX(return_pct) as max_return
            FROM stock_strategies
        """
        
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                result = cursor.fetchone()
                return result if result else {}
                
        except Exception as e:
            logger.error(f"Failed to get table stats: {e}")
            return {}


# 便捷函數
def get_db():
    """獲取數據庫連接"""
    return BacktestDB()
