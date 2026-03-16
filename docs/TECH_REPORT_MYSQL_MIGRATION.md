# Tech Report: SQLite → MySQL 遷移 & yfinance 移除

**日期:** 2026-03-06  
**執行:** tm-engineer subagent  
**狀態:** ✅ 完成

---

## 1. SQLite → MySQL 遷移

### 受影響模組（已改為 MySQL）

| 模組 | 原 SQLite 資源 | 改動說明 |
|------|--------------|---------|
| `middleware/auth.py` | `data/trademaster.db` → `api_keys` 表 | 改用 `config.database.get_db_cursor/get_db_connection` |
| `core/position_manager.py` | `data/trademaster.db` → `positions` 表 | 全面改用 MySQL，返回格式相容（`dict`） |
| `api/news_bp.py` | `data/trademaster.db` → `news` 表 | 改用 MySQL，`%s` placeholder，`DATE_SUB(NOW(), INTERVAL N HOUR)` |
| `migrations/migrate_v2.py` | SQLite migrate runner | 全面改用 `mysql.connector`，執行 `migrations/*.sql` |
| `tools/analyze_strategies.py` | `data/trademaster.db` → `stock_*` 表 | 改從 MySQL `kline_cache` 讀取 |
| `scripts/fetch_futu_simple.py` | `data/kline_cache.db` | 改寫入 MySQL `kline_cache` 表 |
| `scripts/fetch_futu_5intervals.py` | `data/kline_cache.db` | 改寫入 MySQL `kline_cache` 表 |
| `scripts/futu_polling.py` | `data/kline_cache.db` (realtime_quote) | `update_quotes()` 改寫入 MySQL `realtime_quote` 表 |

### 新增 Migration

| 文件 | 內容 |
|------|------|
| `migrations/005_api_keys_kline_cache.sql` | `api_keys` / `kline_cache` / `realtime_quote` 三張表 |

### 所有 Migration 文件已更新為 MySQL 語法

- `001_signals.sql` – `INT AUTO_INCREMENT`, `ENGINE=InnoDB`
- `002_positions.sql` – 同上，`ON UPDATE CURRENT_TIMESTAMP`
- `003_orders.sql` – 同上
- `004_news_notifications_risk.sql` – 同上，`news` 表增加 `content`, `url` 欄位

---

## 2. 執行資料庫遷移

```bash
cd /path/to/TradeMaster_v2
python3 migrations/migrate_v2.py
```

腳本會：
1. 連線 MySQL（讀取 `config/database.py` 設定）
2. 建立 `schema_migrations` 紀錄表
3. 按順序執行 001 ~ 005 的 SQL 文件（已執行過的跳過）

**MySQL 環境變數（可覆蓋預設）：**
```bash
MYSQL_HOST=localhost
MYSQL_USER=alita
MYSQL_PASSWORD=alitamysql
MYSQL_DATABASE=trademaster
```

---

## 3. yfinance / Yahoo Finance 移除

### 移除檔案清單

| 檔案 | 處理方式 | 替代數據源 |
|------|---------|-----------|
| `data/__init__.py` | 完全重寫，移除 `import yfinance` | 本地 CSV → MySQL `kline_cache`（富途） |
| `signal_generator.py` | 移除 yfinance import 及 `yf.Ticker` 呼叫 | MySQL `kline_cache` 5m K線（富途） |
| `modules/prediction/engine.py` | 移除 `import yfinance` fallback | MySQL `kline_cache` 1d K線（富途） |
| `scripts/yfinance_update.py` | 改為廢棄腳本（顯示提示訊息） | `scripts/backfill_futu_kline_mysql.py` |
| `scripts/fetch_history_all.py` | 改為廢棄腳本（顯示提示訊息） | `scripts/fetch_futu_5intervals.py` |

### 保留（archive 目錄，不執行）
- `backtests/archive/run_high_sharpe_backtest.py` – 歷史存檔，不納入主流程

---

## 4. 新聞模塊（配合 MySQL）

- `api/news_bp.py` 已全面改用 MySQL
- `/api/v1/news` – 支援 `symbol`, `limit`, `sentiment` 過濾
- `/api/v1/news/weight/<symbol>` – 改用 `DATE_SUB(NOW(), INTERVAL N HOUR)`（原 SQLite `datetime('now', '...')` 語法已替換）
- 未設計新的新聞來源（由 tm-news-finance agent 負責）

---

## 5. 風險提示

| 風險 | 描述 | 處理建議 |
|------|------|---------|
| archive 腳本殘留 | `scripts/archive/` 下多個腳本仍有 SQLite 引用 | 已歸檔，不執行；可整批刪除 |
| backtest .py.bak 等備份 | `backtest.py.bak/old/orig` 含舊邏輯 | 非執行路徑，建議清理 |
| `download_data.py` | 根目錄存在，待確認是否使用 yfinance | 需單獨審查 |
| `scripts/test_aapl.py` | 仍有 SQLite `kline_cache.db` 引用 | 測試腳本，建議更新或刪除 |
| `data/kline_cache.db`, `paper_trading.db`, `trademaster.db` | SQLite 檔仍存在磁碟 | 可在確認 MySQL 正常後刪除 |

---

## 6. 建議後續步驟

1. **執行遷移:** `python3 migrations/migrate_v2.py`
2. **驗證 API:** 啟動 API server 測試 `/api/v1/news`, `/api/v1/news/weight/AAPL`
3. **清理舊 .db 檔:**
   ```bash
   rm data/trademaster.db data/kline_cache.db data/paper_trading.db
   ```
   （建議先確認 MySQL 數據正確後再刪除）
4. **清理 archive 腳本:** `scripts/archive/` 可視情況刪除
5. **更新 `requirements.txt`:** 移除 `yfinance`，確保 `mysql-connector-python` 已列入
