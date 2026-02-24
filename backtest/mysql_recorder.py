# MySQL Recorder - 回測結果記錄到 MySQL

import pymysql
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# MySQL 配置
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'alita',
    'password': 'alitamysql',
    'database': 'trademaster',
    'charset': 'utf8mb4'
}


@dataclass
class BacktestRecord:
    """回測記錄數據類"""
    id: Optional[int] = None
    batch_id: str = ""
    task_id: str = ""
    strategy_name: str = ""
    symbol: str = ""
    timeframe: str = ""
    start_date: str = ""
    end_date: str = ""
    
    # 參數
    params_json: str = ""
    
    # 指標
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_trade_return: float = 0.0
    avg_holding_days: float = 0.0
    
    # 額外指標
    metrics_json: str = ""
    
    # 狀態
    status: str = "pending"
    error_message: str = ""
    duration_seconds: float = 0.0
    
    # 時間
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "task_id": self.task_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "params": json.loads(self.params_json) if self.params_json else {},
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class MySQLBacktestRecorder:
    """MySQL 回測記錄器"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化 MySQL 記錄器
        
        Args:
            config: MySQL 配置，默認使用全局配置
        """
        self.config = config or MYSQL_CONFIG
        self._ensure_table()
    
    def _get_connection(self) -> pymysql.Connection:
        """獲取數據庫連接"""
        return pymysql.connect(**self.config)
    
    def _close_connection(self, conn: Optional[pymysql.Connection]):
        """安全關閉連接"""
        if conn:
            try:
                if conn.open:
                    conn.close()
            except Exception:
                pass
    
    def _ensure_table(self):
        """確保回測結果表存在"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INT AUTO_INCREMENT PRIMARY KEY,
            batch_id VARCHAR(50) NOT NULL,
            task_id VARCHAR(50) NOT NULL,
            strategy_name VARCHAR(100) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            timeframe VARCHAR(10) NOT NULL,
            start_date DATE,
            end_date DATE,
            
            -- 參數 (JSON)
            params_json TEXT,
            
            -- 指標
            total_return DECIMAL(10,4) DEFAULT 0,
            sharpe_ratio DECIMAL(10,4) DEFAULT 0,
            sortino_ratio DECIMAL(10,4) DEFAULT 0,
            max_drawdown DECIMAL(10,4) DEFAULT 0,
            win_rate DECIMAL(5,4) DEFAULT 0,
            profit_factor DECIMAL(10,4) DEFAULT 0,
            total_trades INT DEFAULT 0,
            avg_trade_return DECIMAL(10,4) DEFAULT 0,
            avg_holding_days DECIMAL(10,2) DEFAULT 0,
            
            -- 額外指標 (JSON)
            metrics_json TEXT,
            
            -- 狀態
            status VARCHAR(20) DEFAULT 'pending',
            error_message TEXT,
            duration_seconds DECIMAL(10,2) DEFAULT 0,
            
            -- 時間戳
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            
            INDEX idx_batch_id (batch_id),
            INDEX idx_strategy_name (strategy_name),
            INDEX idx_symbol (symbol),
            INDEX idx_status (status),
            INDEX idx_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(create_table_sql)
            conn.commit()
            logger.info("backtest_results table ensured")
        finally:
            self._close_connection(conn)
    
    def save_task_result(
        self,
        task_result: Dict[str, Any],
        batch_id: str = ""
    ) -> int:
        """
        保存單個任務結果
        
        Args:
            task_result: 任務結果字典
            batch_id: 批次 ID
            
        Returns:
            記錄 ID
        """
        # Extract metrics
        metrics = task_result.get("result", {})
        if not metrics:
            metrics = task_result
        
        params = task_result.get("params", {})
        
        record = BacktestRecord(
            batch_id=batch_id or task_result.get("batch_id", ""),
            task_id=task_result.get("task_id", ""),
            strategy_name=task_result.get("strategy_name", ""),
            symbol=task_result.get("symbol", ""),
            timeframe=task_result.get("timeframe", ""),
            start_date=task_result.get("start_date", ""),
            end_date=task_result.get("end_date", ""),
            params_json=json.dumps(params, ensure_ascii=False),
            total_return=metrics.get("total_return", 0) or metrics.get("return", 0) or 0,
            sharpe_ratio=metrics.get("sharpe_ratio", 0) or metrics.get("sharpe", 0) or 0,
            sortino_ratio=metrics.get("sortino_ratio", 0) or 0,
            max_drawdown=metrics.get("max_drawdown", 0) or metrics.get("drawdown", 0) or 0,
            win_rate=metrics.get("win_rate", 0) or metrics.get("winrate", 0) or 0,
            profit_factor=metrics.get("profit_factor", 0) or metrics.get("profitfactor", 0) or 0,
            total_trades=metrics.get("total_trades", 0) or metrics.get("trades", 0) or 0,
            avg_trade_return=metrics.get("avg_trade_return", 0) or 0,
            avg_holding_days=metrics.get("avg_holding_days", 0) or 0,
            metrics_json=json.dumps(metrics, ensure_ascii=False),
            status=task_result.get("status", "completed"),
            error_message=task_result.get("error", ""),
            duration_seconds=task_result.get("duration_seconds", 0) or 0
        )
        
        return self._insert_record(record)
    
    def save_batch_results(
        self,
        batch_result: Dict[str, Any]
    ) -> int:
        """
        保存批次結果
        
        Args:
            batch_result: BatchResult 字典或 to_dict() 結果
            
        Returns:
            保存的記錄數
        """
        batch_id = batch_result.get("batch_id", "")
        tasks = batch_result.get("tasks", [])
        
        saved_count = 0
        for task in tasks:
            task["batch_id"] = batch_id
            try:
                self.save_task_result(task, batch_id)
                saved_count += 1
            except Exception as e:
                logger.error(f"Failed to save task {task.get('task_id')}: {e}")
        
        return saved_count
    
    def _insert_record(self, record: BacktestRecord) -> int:
        """插入記錄"""
        sql = """
        INSERT INTO backtest_results (
            batch_id, task_id, strategy_name, symbol, timeframe,
            start_date, end_date, params_json,
            total_return, sharpe_ratio, sortino_ratio, max_drawdown,
            win_rate, profit_factor, total_trades, avg_trade_return,
            avg_holding_days, metrics_json, status, error_message,
            duration_seconds
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        """
        
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (
                    record.batch_id,
                    record.task_id,
                    record.strategy_name,
                    record.symbol,
                    record.timeframe,
                    record.start_date or None,
                    record.end_date or None,
                    record.params_json,
                    record.total_return,
                    record.sharpe_ratio,
                    record.sortino_ratio,
                    record.max_drawdown,
                    record.win_rate,
                    record.profit_factor,
                    record.total_trades,
                    record.avg_trade_return,
                    record.avg_holding_days,
                    record.metrics_json,
                    record.status,
                    record.error_message,
                    record.duration_seconds
                ))
                record_id = cursor.lastrowid
            conn.commit()
            return record_id
        finally:
            self._close_connection(conn)
    
    def query_results(
        self,
        batch_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[BacktestRecord]:
        """查詢回測結果"""
        conditions = []
        params = []
        
        if batch_id:
            conditions.append("batch_id = %s")
            params.append(batch_id)
        if strategy_name:
            conditions.append("strategy_name = %s")
            params.append(strategy_name)
        if symbol:
            conditions.append("symbol = %s")
            params.append(symbol)
        if status:
            conditions.append("status = %s")
            params.append(status)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        sql = f"""
        SELECT * FROM backtest_results
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s
        """
        params.append(limit)
        
        conn = self._get_connection()
        try:
            df = pd.read_sql(sql, conn, params=params)
        finally:
            self._close_connection(conn)
        
        records = []
        for _, row in df.iterrows():
            record = BacktestRecord(
                id=row['id'],
                batch_id=row['batch_id'],
                task_id=row['task_id'],
                strategy_name=row['strategy_name'],
                symbol=row['symbol'],
                timeframe=row['timeframe'],
                start_date=str(row['start_date']) if pd.notna(row['start_date']) else "",
                end_date=str(row['end_date']) if pd.notna(row['end_date']) else "",
                params_json=row['params_json'] or "",
                total_return=float(row['total_return']) if pd.notna(row['total_return']) else 0,
                sharpe_ratio=float(row['sharpe_ratio']) if pd.notna(row['sharpe_ratio']) else 0,
                sortino_ratio=float(row['sortino_ratio']) if pd.notna(row['sortino_ratio']) else 0,
                max_drawdown=float(row['max_drawdown']) if pd.notna(row['max_drawdown']) else 0,
                win_rate=float(row['win_rate']) if pd.notna(row['win_rate']) else 0,
                profit_factor=float(row['profit_factor']) if pd.notna(row['profit_factor']) else 0,
                total_trades=int(row['total_trades']) if pd.notna(row['total_trades']) else 0,
                avg_trade_return=float(row['avg_trade_return']) if pd.notna(row['avg_trade_return']) else 0,
                avg_holding_days=float(row['avg_holding_days']) if pd.notna(row['avg_holding_days']) else 0,
                metrics_json=row['metrics_json'] or "",
                status=row['status'],
                error_message=row['error_message'] or "",
                duration_seconds=float(row['duration_seconds']) if pd.notna(row['duration_seconds']) else 0,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            records.append(record)
        
        return records
    
    def get_best_results(
        self,
        strategy_name: Optional[str] = None,
        symbol: Optional[str] = None,
        metric: str = "sharpe_ratio",
        top_n: int = 10
    ) -> List[BacktestRecord]:
        """獲取最佳結果"""
        conditions = ["status = 'completed'"]
        params = []
        
        if strategy_name:
            conditions.append("strategy_name = %s")
            params.append(strategy_name)
        if symbol:
            conditions.append("symbol = %s")
            params.append(symbol)
        
        where_clause = " AND ".join(conditions)
        
        # Validate metric
        valid_metrics = [
            'total_return', 'sharpe_ratio', 'sortino_ratio',
            'max_drawdown', 'win_rate', 'profit_factor'
        ]
        if metric not in valid_metrics:
            metric = 'sharpe_ratio'
        
        sql = f"""
        SELECT * FROM backtest_results
        WHERE {where_clause}
        ORDER BY {metric} DESC
        LIMIT %s
        """
        params.append(top_n)
        
        conn = self._get_connection()
        try:
            df = pd.read_sql(sql, conn, params=params)
        finally:
            self._close_connection(conn)
        
        records = []
        for _, row in df.iterrows():
            record = BacktestRecord(
                id=row['id'],
                batch_id=row['batch_id'],
                task_id=row['task_id'],
                strategy_name=row['strategy_name'],
                symbol=row['symbol'],
                timeframe=row['timeframe'],
                start_date=str(row['start_date']) if pd.notna(row['start_date']) else "",
                end_date=str(row['end_date']) if pd.notna(row['end_date']) else "",
                params_json=row['params_json'] or "",
                total_return=float(row['total_return']) if pd.notna(row['total_return']) else 0,
                sharpe_ratio=float(row['sharpe_ratio']) if pd.notna(row['sharpe_ratio']) else 0,
                max_drawdown=float(row['max_drawdown']) if pd.notna(row['max_drawdown']) else 0,
                win_rate=float(row['win_rate']) if pd.notna(row['win_rate']) else 0,
                status=row['status'],
                created_at=row['created_at']
            )
            records.append(record)
        
        return records
    
    def delete_batch(self, batch_id: str) -> int:
        """刪除批次結果"""
        sql = "DELETE FROM backtest_results WHERE batch_id = %s"
        
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                deleted = cursor.execute(sql, (batch_id,))
            conn.commit()
            return deleted
        finally:
            self._close_connection(conn)
    
    def get_statistics(self) -> Dict:
        """獲取回測統計"""
        sql = """
        SELECT 
            COUNT(*) as total_runs,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            AVG(total_return) as avg_return,
            AVG(sharpe_ratio) as avg_sharpe,
            AVG(win_rate) as avg_win_rate,
            SUM(total_trades) as total_trades
        FROM backtest_results
        """
        
        conn = self._get_connection()
        try:
            df = pd.read_sql(sql, conn)
            
            if not df.empty:
                row = df.iloc[0]
                return {
                    "total_runs": int(row['total_runs']) if pd.notna(row['total_runs']) else 0,
                    "completed": int(row['completed']) if pd.notna(row['completed']) else 0,
                    "failed": int(row['failed']) if pd.notna(row['failed']) else 0,
                    "avg_return": float(row['avg_return']) if pd.notna(row['avg_return']) else 0,
                    "avg_sharpe": float(row['avg_sharpe']) if pd.notna(row['avg_sharpe']) else 0,
                    "avg_win_rate": float(row['avg_win_rate']) if pd.notna(row['avg_win_rate']) else 0,
                    "total_trades": int(row['total_trades']) if pd.notna(row['total_trades']) else 0
                }
        finally:
            self._close_connection(conn)
        
        return {}


def get_recorder(config: Optional[Dict] = None) -> MySQLBacktestRecorder:
    """工廠函數：獲取記錄器實例"""
    return MySQLBacktestRecorder(config)


# 便捷函數
def save_backtest_result(task_result: Dict, batch_id: str = "") -> int:
    """保存單個回測結果"""
    recorder = get_recorder()
    return recorder.save_task_result(task_result, batch_id)


def save_batch_result(batch_result: Dict) -> int:
    """保存批次回測結果"""
    recorder = get_recorder()
    return recorder.save_batch_results(batch_result)


def query_backtest_results(**kwargs) -> List[BacktestRecord]:
    """查詢回測結果"""
    recorder = get_recorder()
    return recorder.query_results(**kwargs)
