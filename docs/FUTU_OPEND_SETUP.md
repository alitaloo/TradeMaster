# 富途 OpenD 模擬交易配置

## 系統架構

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  TradeMaster │────▶│  富途 OpenD  │────▶│  富途伺服器  │
│  (本專案)    │     │  (本地代理)  │     │  (模擬環境) │
└─────────────┘     └─────────────┘     └─────────────┘
```

## 安裝步驟

### 1. 下載富途 OpenD

前往富途官網下載 OpenD：
- macOS: https://www.futunn.com/OpenAPI
- 或使用: `brew install futunn`

### 2. 啟動 OpenD

```bash
# 啟動 OpenD (默認端口 11111)
/Applications/OpenD.app/Contents/MacOS/OpenD

# 或後台運行
nohup /Applications/OpenD.app/Contents/MacOS/OpenD > /tmp/opend.log 2>&1 &
```

### 3. 配置富途賬號

在富途牛牛 App 中：
1. 點「我的」→「OpenAPI」
2. 申請 OpenAPI 權限
3. 獲取 UID

### 4. 安裝 Python SDK

```bash
pip install futu-api
```

### 5. 測試連接

```bash
cd ~/.openclaw/workspace/codes/TradeMaster_v2
python3 -c "
from futu import TradeContext, TrdEnv
ctx = TradeContext(host='127.0.0.1', port=11111, trd_env=TrdEnv.SIMULATE)
print('✅ 連接成功')
ctx.close()
"
```

## 配置項

### 環境變數

```bash
# 可選配置
export FUTU_HOST=127.0.0.1
export FUTU_PORT=11111
```

### 交易模式

- `TrdEnv.SIMULATE`: 模擬交易 (預設)
- `TrdEnv.REAL`: 真實交易 ⚠️ 小心使用

## 常見問題

### Q: OpenD 連接失敗？
A: 確保 OpenD 已啟動並監聽 11111 端口
```bash
lsof -i :11111
```

### Q: 模擬交易沒有資金？
A: 富途模擬帳戶有預設 100 萬港幣，可在牛牛 App 查看

### Q: 如何切換到真實交易？
A: 修改 `paper_trading.py` 中的 `trd_env` 為 `TrdEnv.REAL`
⚠️ **警告**: 這會使用真實資金交易！

## 相關檔案

- `paper_trading.py` - 主要交易邏輯
- `cron_paper_poll.py` - 訂單輪詢
- `cron_paper_daily.py` - 每日結算

## 參考文檔

- 富途 OpenAPI: https://openapi.futunn.com/
- Python SDK: https://github.com/FutunnOpen/py-futu-api
