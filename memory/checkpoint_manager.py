#!/usr/bin/env python3
"""
TradeMaster v2 - Checkpoint Manager
斷點續傳管理器

功能:
- 保存回測進度到 checkpoint.json
- 支援 restart 重新開始
- 自動跳過已完成的項目
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Checkpoint 檔案路徑
CHECKPOINT_DIR = Path(__file__).parent / "memory"
CHECKPOINT_FILE = CHECKPOINT_DIR / "checkpoint.json"


class CheckpointManager:
    """斷點續傳管理器"""
    
    def __init__(self, checkpoint_file: Path = None):
        self.checkpoint_file = checkpoint_file or CHECKPOINT_FILE
        self.checkpoint_dir = self.checkpoint_file.parent
        self._ensure_dir()
        
    def _ensure_dir(self):
        """確保目錄存在"""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    def init_checkpoint(self, task_name: str, symbols: List[str], strategies: List[Dict], 
                        total_backtests: int = None) -> Dict:
        """
        初始化 checkpoint
        
        Args:
            task_name: 任務名稱
            symbols: 股票清單
            strategies: 策略清單
            total_backtests: 總回測次數（可選，自動計算）
        """
        if total_backtests is None:
            total_backtests = len(symbols) * len(strategies)
            
        checkpoint = {
            "task_name": task_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "status": "in_progress",
            "progress": {
                "current_symbol_index": 0,
                "current_strategy_index": 0,
                "current_symbol": symbols[0] if symbols else None,
                "total_symbols": len(symbols),
                "total_strategies": len(strategies),
                "total_backtests": total_backtests,
                "completed_backtests": 0,
                "failed_backtests": 0
            },
            "symbols": symbols,
            "strategies": strategies,
            "completed": {},  # {"symbol_strategy_key": result_summary}
            "results": []    # 完整結果列表
        }
        
        self.save(checkpoint)
        logger.info(f"📍 Checkpoint 初始化: {task_name}")
        logger.info(f"   總回測次數: {total_backtests}")
        
        return checkpoint
    
    def load(self) -> Optional[Dict]:
        """載入 checkpoint"""
        if not self.checkpoint_file.exists():
            return None
            
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ 載入 checkpoint 失敗: {e}")
            return None
    
    def save(self, checkpoint: Dict):
        """保存 checkpoint"""
        checkpoint["updated_at"] = datetime.now().isoformat()
        
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 保存 checkpoint 失敗: {e}")
    
    def update_progress(self, symbol: str, strategy_rank: int, result: Dict = None):
        """
        更新進度
        
        Args:
            symbol: 股票代碼
            strategy_rank: 策略排名
            result: 回測結果（可選）
        """
        checkpoint = self.load()
        if not checkpoint:
            return
            
        key = f"{symbol}_{strategy_rank}"
        checkpoint["progress"]["completed_backtests"] += 1
        
        if result:
            checkpoint["completed"][key] = {
                "completed_at": datetime.now().isoformat(),
                "sharpe": result.get("sharpe"),
                "return": result.get("annual_return"),
                "success": result.get("success", True)
            }
            checkpoint["results"].append(result)
        
        # 更新當前位置
        current_idx = checkpoint["progress"]["current_strategy_index"]
        if current_idx < len(checkpoint["strategies"]) - 1:
            checkpoint["progress"]["current_strategy_index"] += 1
            next_strategy = checkpoint["strategies"][checkpoint["progress"]["current_strategy_index"]]
            checkpoint["progress"]["current_symbol"] = next_strategy.get("symbol", symbol)
        
        self.save(checkpoint)
        
        # 顯示進度
        total = checkpoint["progress"]["total_backtests"]
        completed = checkpoint["progress"]["completed_backtests"]
        percent = (completed / total * 100) if total > 0 else 0
        print(f"\r📍 進度: {completed}/{total} ({percent:.1f}%)", end="", flush=True)
    
    def mark_completed(self, symbol: str, strategy_rank: int, result: Dict = None):
        """標記為已完成"""
        self.update_progress(symbol, strategy_rank, result)
    
    def mark_failed(self, symbol: str, strategy_rank: int, error: str = None):
        """標記為失敗"""
        checkpoint = self.load()
        if not checkpoint:
            return
            
        key = f"{symbol}_{strategy_rank}"
        checkpoint["progress"]["failed_backtests"] += 1
        checkpoint["completed"][key] = {
            "completed_at": datetime.now().isoformat(),
            "success": False,
            "error": error
        }
        
        self.save(checkpoint)
    
    def is_completed(self, symbol: str, strategy_rank: int) -> bool:
        """檢查是否已完成"""
        checkpoint = self.load()
        if not checkpoint:
            return False
            
        key = f"{symbol}_{strategy_rank}"
        return key in checkpoint.get("completed", {})
    
    def get_completed_count(self) -> int:
        """獲取已完成數量"""
        checkpoint = self.load()
        if not checkpoint:
            return 0
        return checkpoint.get("progress", {}).get("completed_backtests", 0)
    
    def get_status(self) -> Dict:
        """獲取狀態"""
        checkpoint = self.load()
        if not checkpoint:
            return {"status": "not_found"}
            
        return {
            "task_name": checkpoint.get("task_name"),
            "status": checkpoint.get("status"),
            "created_at": checkpoint.get("created_at"),
            "updated_at": checkpoint.get("updated_at"),
            "progress": checkpoint.get("progress"),
            "completed_count": len(checkpoint.get("completed", {}))
        }
    
    def complete(self):
        """標記任務完成"""
        checkpoint = self.load()
        if not checkpoint:
            return
            
        checkpoint["status"] = "completed"
        checkpoint["completed_at"] = datetime.now().isoformat()
        self.save(checkpoint)
        logger.info("✅ 回測任務完成!")
    
    def restart(self) -> bool:
        """
        重新開始
        
        Returns:
            True: 需要重新開始
            False: 有未完成的任務，應該繼續
        """
        checkpoint = self.load()
        if not checkpoint:
            return True
            
        if checkpoint.get("status") == "completed":
            logger.info("🔄 之前的任務已完成，可以重新開始")
            return True
            
        # 檢查是否有未完成的任務
        completed = len(checkpoint.get("completed", {}))
        total = checkpoint.get("progress", {}).get("total_backtests", 0)
        
        if completed > 0 and completed < total:
            logger.info(f"⚠️ 發現未完成的任務: {completed}/{total} 已完成")
            logger.info("💡 使用 --restart 參數從頭開始")
            return False
        
        return True
    
    def clear(self):
        """清除 checkpoint"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            logger.info("🗑️ Checkpoint 已清除")
    
    def get_next_task(self) -> Optional[Dict]:
        """獲取下一個任務"""
        checkpoint = self.load()
        if not checkpoint:
            return None
            
        # 檢查是否已完成
        if checkpoint.get("status") == "completed":
            return None
            
        symbols = checkpoint.get("symbols", [])
        strategies = checkpoint.get("strategies", [])
        completed = checkpoint.get("completed", {})
        
        for i, strategy in enumerate(strategies):
            symbol = strategy.get("symbol", "")
            rank = strategy.get("rank", i + 1)
            key = f"{symbol}_{rank}"
            
            if key not in completed:
                return {
                    "symbol": symbol,
                    "strategy": strategy,
                    "strategy_index": i
                }
        
        return None
    
    def get_progress_percentage(self) -> float:
        """獲取進度百分比"""
        checkpoint = self.load()
        if not checkpoint:
            return 0.0
            
        progress = checkpoint.get("progress", {})
        completed = progress.get("completed_backtests", 0)
        total = progress.get("total_backtests", 1)
        return (completed / total * 100) if total > 0 else 0


def create_checkpoint(task_name: str, symbols: List[str], strategies: List[Dict], 
                     total_backtests: int = None) -> CheckpointManager:
    """建立 checkpoint"""
    manager = CheckpointManager()
    manager.init_checkpoint(task_name, symbols, strategies, total_backtests)
    return manager


def load_checkpoint() -> Optional[Dict]:
    """載入 checkpoint"""
    manager = CheckpointManager()
    return manager.load()


def print_checkpoint_status():
    """顯示 checkpoint 狀態"""
    manager = CheckpointManager()
    status = manager.get_status()
    
    if status["status"] == "not_found":
        print("📭 沒有找到 checkpoint")
        return
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    📍 Checkpoint 狀態                       ║
╠══════════════════════════════════════════════════════════════╣
║ 任務名稱:     {status.get('task_name', 'N/A'):<40}║
║ 狀態:         {'🔄 進行中' if status.get('status') == 'in_progress' else '✅ 完成':<40}║
╠══════════════════════════════════════════════════════════════╣
║ 進度:         {status.get('progress', {}).get('completed_backtests', 0)}/{status.get('progress', {}).get('total_backtests', 0):<40}║
║ 百分比:       {manager.get_progress_percentage():.1f}%{' '*35}║
║ 建立時間:     {status.get('created_at', 'N/A'):<40}║
║ 更新時間:     {status.get('updated_at', 'N/A'):<40}║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    # 測試 checkpoint 功能
    print("="*60)
    print("🧪 Checkpoint Manager 測試")
    print("="*60)
    
    # 測試建立
    manager = CheckpointManager()
    
    symbols = ["AAPL", "TSLA", "SPY"]
    strategies = [
        {"rank": 1, "symbol": "AAPL", "params": "RSI(7/35/80)"},
        {"rank": 2, "symbol": "AAPL", "params": "RSI(14/35/65)"},
        {"rank": 3, "symbol": "SPY", "params": "MA(10/50)"}
    ]
    
    print("\n1. 建立 checkpoint...")
    manager.init_checkpoint("test_backtest", symbols, strategies)
    
    print("\n2. 模擬完成一些任務...")
    manager.mark_completed("AAPL", 1, {"sharpe": 1.8, "return": 0.25})
    manager.mark_completed("AAPL", 2, {"sharpe": 1.5, "return": 0.20})
    
    print("\n3. 獲取狀態...")
    print_checkpoint_status()
    
    print("\n4. 獲取下一個任務...")
    next_task = manager.get_next_task()
    print(f"   下一個任務: {next_task}")
    
    print("\n5. 標記完成...")
    if next_task:
        manager.mark_completed(next_task["symbol"], next_task["strategy"]["rank"], {"sharpe": 2.0})
    
    print("\n6. 最終狀態...")
    print_checkpoint_status()
    
    print("\n7. 清除 checkpoint...")
    manager.clear()
