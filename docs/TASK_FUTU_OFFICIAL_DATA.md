# TradeMaster 富途牛牛官方 API 整合與數據持久化任務

**任務目標：**
1. 安裝富途牛牛官方 Python 庫
2. 修改數據獲取邏輯：開盤時間持續落數據，支援所有時間週期

---

## 任務 1：安裝富途牛牛官方 Python 庫

### 步驟 1：獲取官方庫

**方法 A：從富途官網下載**
1. 打開富途牛牛客戶端
2. 前往「開放平台」或「API 設置」
3. 下載 Python SDK（通常是 `futu_api_pip_xxx.tar.gz`）

**方法 B：如果官網提供 pip 安裝**
```bash
pip3 install futu-openapi
# 或
pip3 install futu-api
```

### 步驟 2：安裝
```bash
cd /Users/alita/.openclaw/workspace/codes/TradeMaster_v2
pip3 install /path/to/futu_api_pip_xxx.tar.gz
```

### 步驟 3：驗證安裝
```bash
python3 -c "import futu as ft; print('版本:', ft.__version__); print('屬性:', dir(ft))"
```

### 步驟 4：更新代碼
更新 `api/futu_kline.py` 以使用官方 API

---

## 任務 2：修改數據獲取邏輯

### 新策略邏輯

```
┌─────────────────────────────────────────────────────────────┐
│                    數據獲取策略                              │
└─────────────────────────────────────────────────────────────┘

開盤時間（美股 9:30-16:00 ET）：
  │
  ├── 每 5 分鐘自動獲取最新 K 線
  ├── 存入本地數據庫（SQLite）
  ├── 支援時間週期：1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M
  └── 用於：實盤信號計算

非開盤時間：
  │
  ├── 使用本地快取數據
  ├── 不請求外部 API
  └── 用於：查看歷史、訓練模型
```

### 數據持久化設計

```python
# SQLite 表結構
CREATE TABLE kline_data (
    symbol TEXT NOT NULL,           # 股票代號 (US.AAPL)
    interval TEXT NOT NULL,         # 時間週期 (1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M)
    timestamp TEXT NOT NULL,         # K 線時間戳
    open REAL,                      # 開盤價
    high REAL,                      # 最高價
    low REAL,                       # 最低價
    close REAL,                     # 收盤價
    volume INTEGER,                 # 成交量
    updated_at TEXT NOT NULL,       # 更新時間
    PRIMARY KEY (symbol, interval, timestamp)
);

CREATE TABLE stock_metadata (
    symbol TEXT NOT NULL,
    exchange TEXT,                  # 交易所 (US, HK, SH, SZ)
    company_name TEXT,             # 公司名稱
    last_data_update TEXT,          # 最後數據更新時間
    PRIMARY KEY (symbol)
);
```

### 數據獲取腳本

```python
#!/usr/bin/env python3
"""
數據獲取服務
開盤時間持續落數據
"""

import schedule
from datetime import datetime, timezone
import sqlite3

# 市場時間配置
MARKET_HOURS_ET = {
    'US': {'open': '09:30', 'close': '16:00'},
    'HK': {'open': '09:30', 'close': '16:00'},
    'SH': {'open': '09:30', 'close': '15:00'},
    'SZ': {'open': '09:30', 'close': '15:00'}
}

# 支援的時間週期
INTERVALS = ['1m', '5m', '15m', '30m', '1h', '1d', '1w', '1M']

# 股票池
STOCK_POOL = [
    # 美股
    'US.AAPL', 'US.MSFT', 'US.NVDA', 'US.GOOGL', 'US.AMZN',
    'US.META', 'US.TSM', 'US.AMD', 'US.MU', 'US.ORCL',
    'US.GOOG', 'US.NFLX', 'US.ADBE', 'US.CRM', 'US.QCOM',
    'US.TXN', 'US.AVGO', 'US.COIN', 'US.MSTR', 'US.UBER',
    # 港股
    'HK.00700', 'HK.03690', 'HK.00981', 'HK.01810', 'HK.02282',
    # A 股
    'SH.600519', 'SZ.000001'
]

def fetch_all_klines():
    """獲取所有股票的 K 線數據"""
    print(f"[{datetime.now()}] 開始獲取 K 線數據...")
    
    for symbol in STOCK_POOL:
        for interval in INTERVALS:
            try:
                # 從富途獲取數據
                data = get_futu_kline(symbol, interval)
                
                if data:
                    # 存入本地數據庫
                    save_to_db(symbol, interval, data)
                    print(f"  ✅ {symbol} {interval}: {len(data)} 筆")
                else:
                    print(f"  ❌ {symbol} {interval}: 無數據")
                    
            except Exception as e:
                print(f"  ❌ {symbol} {interval}: {e}")
    
    print(f"[{datetime.now()}] K 線數據獲取完成")

def save_to_db(symbol, interval, klines):
    """存入本地數據庫"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    for kline in klines:
        cursor.execute('''
            INSERT OR REPLACE INTO kline_data
            (symbol, interval, timestamp, open, high, low, close, volume, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            symbol, interval, kline['timestamp'],
            kline['open'], kline['high'], kline['low'], kline['close'],
            kline['volume'], now
        ))
    
    conn.commit()
    conn.close()

# 定時任務
schedule.every().day.at("09:25").do(fetch_all_klines)  # 開盤前 5 分鐘
schedule.every().day.at("09:35").do(fetch_all_klines)  # 開盤後首次
schedule.every(5).minutes.do(fetch_all_klines)          # 之後每 5 分鐘
schedule.every().day.at("16:05").do(fetch_all_klines)   # 收盤後清理

if __name__ == '__main__':
    print("啟動數據獲取服務...")
    print(f"股票池: {len(STOCK_POOL)} 支")
    print(f"時間週期: {len(INTERVALS)} 種")
    
    # 立即執行一次
    fetch_all_klines()
    
    # 進入定時循環
    while True:
        schedule.run_pending()
        sleep(60)
```

---

## 任務 3：更新 API 端點

### 新增端點

```python
# 獲取已持久化的 K 線數據
@futu_bp.route('/api/v1/kline/persisted', methods=['GET'])
def get_persisted_kline():
    """從本地數據庫獲取 K 線數據"""
    symbol = request.args.get('symbol', 'US.AAPL')
    interval = request.args.get('interval', '5m')
    limit = int(request.args.get('limit', 100))
    
    # 優先從本地數據庫獲取
    data = get_from_db(symbol, interval, limit)
    
    if data:
        return jsonify({
            "source": "persisted",
            "symbol": symbol,
            "interval": interval,
            "count": len(data),
            "data": data
        })
    
    # 如果本地沒有，嘗試從富途獲取
    data = get_futu_kline(symbol, interval)
    if data:
        save_to_db(symbol, interval, data)
        return jsonify({
            "source": "futu",
            "symbol": symbol,
            "interval": interval,
            "count": len(data),
            "data": data
        })
    
    return jsonify({"error": "No data"}), 404

# 數據獲取狀態
@futu_bp.route('/api/v1/kline/status', methods=['GET'])
def get_data_status():
    """查看數據持久化狀態"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            symbol,
            interval,
            COUNT(*) as count,
            MAX(updated_at) as last_update
        FROM kline_data
        GROUP BY symbol, interval
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "total_records": len(rows),
        "records": [
            {
                "symbol": r[0],
                "interval": r[1],
                "count": r[2],
                "last_update": r[3]
            }
            for r in rows
        ]
    })

# 觸發數據更新
@futu_bp.route('/api/v1/kline/fetch', methods=['POST'])
def trigger_fetch():
    """手動觸發數據獲取"""
    symbol = request.args.get('symbol')
    
    if symbol:
        data = get_futu_kline(symbol, '5m')
        if data:
            save_to_db(symbol, '5m', data)
            return jsonify({"status": "ok", "symbol": symbol, "count": len(data)})
    
    # 獲取所有
    fetch_all_klines()
    return jsonify({"status": "ok", "message": "All data fetched"})
```

---

## 驗收標準

### 任務 1
- [ ] 官方 futu 庫安裝成功
- [ ] `import futu` 可正常運行
- [ ] `ft.OpenQuoteContext` 可正常調用

### 任務 2
- [ ] 開盤時間每 5 分鐘自動落數據
- [ ] 支援時間週期：1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M
- [ ] 數據正確存入 SQLite
- [ ] 非開盤時間使用本地快取

### 任務 3
- [ ] `/api/v1/kline/persisted` 端點正常
- [ ] `/api/v1/kline/status` 顯示數據狀態
- [ ] `/api/v1/kline/fetch` 可觸發手動更新

---

## Deliverable

1. **富途官方庫安裝驗證**
2. **數據持久化腳本** (`scripts/fetch_klines.py`)
3. **更新的 API 端點**
4. **測試報告**

---

## 參考資料

- **富途牛牛 API 文檔**: https://futapi.github.io/
- **原代碼**: `/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/api/futu_kline.py`
