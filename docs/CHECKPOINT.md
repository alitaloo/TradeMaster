# TradeMaster v2 - Checkpoint/Resume 功能

## 概述

實現了斷點續傳機制，讓回測失敗後可以從最後成功的位置繼續。

## 檔案位置

- **Checkpoint Manager**: `TradeMaster_v2/memory/checkpoint_manager.py`
- **Checkpoint 檔案**: `TradeMaster_v2/memory/checkpoint.json`

## 使用方法

### 1. 查看 checkpoint 狀態

```bash
python backtests/run_production_backtest.py --status
```

### 2. 繼續執行回測（從上次中斷處繼續）

```bash
python backtests/run_production_backtest.py
```

### 3. 重新開始（清除現有 checkpoint）

```bash
python backtests/run_production_backtest.py --restart
```

## API 使用

```python
from memory.checkpoint_manager import CheckpointManager, create_checkpoint

# 建立 checkpoint
manager = create_checkpoint("my_task", symbols, strategies, total_backtests)

# 標記完成
manager.mark_completed("AAPL", 1, {"sharpe": 1.8, "return": 0.25})

# 檢查是否完成
if manager.is_completed("AAPL", 1):
    print("已完成的任務")

# 獲取狀態
status = manager.get_status()

# 獲取下一個任務
next_task = manager.get_next_task()

# 清除 checkpoint
manager.clear()
```

## Checkpoint 格式

```json
{
  "task_name": "production_backtest_v2",
  "status": "in_progress",
  "progress": {
    "current_symbol_index": 0,
    "current_strategy_index": 5,
    "total_symbols": 15,
    "total_strategies": 10,
    "total_backtests": 150,
    "completed_backtests": 45,
    "failed_backtests": 2
  },
  "completed": {
    "AAPL_1": {
      "completed_at": "2026-02-08T01:30:00",
      "sharpe": 1.8,
      "success": true
    }
  }
}
```

## 功能特點

1. ✅ **自動保存進度** - 每完成一個回測就寫入 checkpoint
2. ✅ **自動跳過已完成的任務** - 不會重複執行
3. ✅ **restart 指令** - 可選擇重新開始
4. ✅ **清晰的日誌輸出** - 顯示進度百分比
5. ✅ **JSON 格式** - 方便讀取和調試

## 支援的腳本

- `backtests/run_production_backtest.py` - 正式回測
- `backtest_v2.py` - 高夏普策略回測系統
