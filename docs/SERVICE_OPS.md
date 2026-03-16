# TradeMaster 服務常駐標準化文檔

> 最後更新: 2026-03-13

## 架構概覽

```
┌─────────────────────────────────────────────────────────┐
│                    macOS launchd                        │
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │ com.trademaster.api │  │ com.trademaster.view     │  │
│  │ python3 api_server  │  │ python3 serve.py         │  │
│  │ :8080               │  │ :3000                    │  │
│  └─────────────────────┘  └──────────────────────────┘  │
│                               │                         │
│                          /api/* proxy → :8080            │
│                          /* → dist/index.html (SPA)     │
├─────────────────────────────────────────────────────────┤
│  MySQL :3306  │  OpenClaw Cron (13+ jobs)               │
└─────────────────────────────────────────────────────────┘
```

## 一、服務管理 (tm-ctl.sh)

統一管理腳本位於 `scripts/tm-ctl.sh`。

### 常用命令

```bash
# 查看所有服務狀態（API + View + MySQL + Cron）
bash scripts/tm-ctl.sh status

# 啟動/停止/重啟
bash scripts/tm-ctl.sh start          # 全部
bash scripts/tm-ctl.sh start api      # 只啟 API
bash scripts/tm-ctl.sh start view     # 只啟 View
bash scripts/tm-ctl.sh stop
bash scripts/tm-ctl.sh restart

# 快速健康檢查（返回 0/1）
bash scripts/tm-ctl.sh health

# 查看日誌
bash scripts/tm-ctl.sh logs api
bash scripts/tm-ctl.sh logs view
```

### 手動驗證

```bash
# API 健康檢查
curl -sf http://127.0.0.1:8080/health
# 預期: {"service":"TradeMaster v2.0 API","status":"ok","version":"2.0.0"}

# View 健康檢查（含 upstream 狀態）
curl -sf http://127.0.0.1:3000/health
# 預期: {"service":"TradeMasterView","status":"ok","view_server":"ok","api_upstream":"ok",...}

# API proxy 驗證
curl -sf http://127.0.0.1:3000/api/v1/signals | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])"

# SPA fallback 驗證（深層路由應返回 index.html）
curl -sf http://127.0.0.1:3000/signals | head -1
# 預期: <!DOCTYPE html>
```

## 二、TradeMaster API (port 8080)

### launchd 配置

- **plist**: `~/Library/LaunchAgents/com.trademaster.api.plist`
- **程式**: `/usr/local/bin/python3 api_server.py`
- **工作目錄**: `~/.openclaw/workspace/codes/TradeMaster_v2`
- **KeepAlive**: SuccessfulExit=false（非正常退出自動重啟）
- **ThrottleInterval**: 10s
- **日誌**:
  - stdout: `logs/api_launchd.log`
  - stderr: `logs/api_launchd_err.log`

### 啟動流程

1. launchd 啟動 python3 → 載入 Flask app
2. 初始化 DataEngine、PredictionEngine
3. 註冊所有 blueprints（signals, positions, orders, news, market...）
4. 綁定 `0.0.0.0:8080`

### 常見問題排查

```bash
# 查看進程
ps aux | grep api_server

# 查看 launchd 狀態
launchctl list com.trademaster.api

# 重新載入 plist（修改後）
launchctl unload ~/Library/LaunchAgents/com.trademaster.api.plist
launchctl load ~/Library/LaunchAgents/com.trademaster.api.plist

# 查看錯誤日誌
tail -100 logs/api_launchd_err.log
```

## 三、TradeMasterView (port 3000)

### 方案說明

使用 **Python serve.py** 作為生產級 SPA 伺服器：

1. **靜態檔案**: 直接從 `dist/` 提供
2. **SPA Fallback**: 任何非檔案路由 → `dist/index.html`（支援 Vue Router `createWebHistory`）
3. **API 反向代理**: `/api/*` → `http://127.0.0.1:8080`（前端無需硬編碼 API URL）
4. **健康端點**: `/health` 同時檢查自身和上游 API

### 為什麼選這個方案

| 方案 | 優點 | 缺點 |
|------|------|------|
| ✅ **serve.py** | 零依賴、SPA fallback、API proxy 一體化 | 非 async，高並發不適用（但本機使用足夠） |
| vite preview | 開發工具，不適合常駐 | 無 API proxy |
| nginx | 效能好 | macOS 需額外安裝維護 |
| Node http-server | 無 SPA fallback | 需額外配置 |

### 前端構建

```bash
cd ~/.openclaw/workspace/codes/TradeMasterView

# 開發環境（帶 HMR + vite proxy）
npm run dev

# 生產構建
npm run build

# 重啟 View 服務以載入新 dist
bash ../TradeMaster_v2/scripts/tm-ctl.sh restart view
```

### 環境變數

- `.env.local`: `VITE_API_URL=/api/v1`（開發 - vite proxy）
- `.env.production`: `VITE_API_URL=/api/v1`（生產 - serve.py proxy）

> ⚠️ **重要**: 兩個環境都使用相對路徑 `/api/v1`，確保請求經過代理。
> 不要改成 `http://localhost:8080/api/v1`，否則會繞過代理。

### launchd 配置

- **plist**: `~/Library/LaunchAgents/com.trademaster.view.plist`
- **程式**: `/usr/local/bin/python3 serve.py`
- **工作目錄**: `~/.openclaw/workspace/codes/TradeMasterView`
- **日誌**:
  - stdout: `logs/view_launchd.log`
  - stderr: `logs/view_launchd_err.log`

## 四、OpenClaw Cron 驗證

### 列出所有 cron job

```bash
openclaw cron list
```

### TradeMaster 相關 cron 一覽

| Job | 排程 | 用途 |
|-----|------|------|
| Paper Order Polling | 每分鐘 | 模擬交易訂單輪詢 |
| Watchdog API | 每 30m | API 存活看門狗 |
| TradeMaster News Batch | 每小時 :15 | 新聞批次抓取 |
| Fox - 5min Analysis | 每 3m（盤中） | 即時策略分析 |
| Futu K-Line Update | 每 5m（盤中） | K 線數據更新 |
| Paper Daily Summary | 每日 09:00 | 模擬交易日報 |
| Nightly Build | 每日 03:30 | 夜間建置 |

### 驗證方式

```bash
# 1. 列出全部，檢查 Status 欄
openclaw cron list

# 2. 檢查特定 job 最近日誌
openclaw cron logs <job-id>

# 3. 系統 crontab（傳統 cron）
crontab -l | grep -i trade

# 4. 快速統計
openclaw cron list 2>/dev/null | tail -n +3 | wc -l          # 總數
openclaw cron list 2>/dev/null | grep -c "error"              # 錯誤數
openclaw cron list 2>/dev/null | grep -c "ok\|running"        # 正常數
```

## 五、完整驗證清單

```bash
# === 一鍵驗證腳本 ===
echo "=== TradeMaster Service Verification ==="
echo ""

# 1. API
echo "1. API Health:"
curl -sf http://127.0.0.1:8080/health && echo "" || echo "❌ FAIL"

# 2. View
echo "2. View Health:"
curl -sf http://127.0.0.1:3000/health && echo "" || echo "❌ FAIL"

# 3. SPA Fallback
echo "3. SPA Fallback (/signals):"
curl -sf http://127.0.0.1:3000/signals | grep -q "<!DOCTYPE" && echo "✅ OK" || echo "❌ FAIL"

# 4. API Proxy
echo "4. API Proxy (/api/v1/signals):"
curl -sf http://127.0.0.1:3000/api/v1/signals | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'✅ OK ({d[\"count\"]} signals)')" 2>/dev/null || echo "❌ FAIL"

# 5. MySQL
echo "5. MySQL:"
mysqladmin ping -h 127.0.0.1 -u alita -palitamysql --silent 2>/dev/null && echo "✅ OK" || echo "⚠️ Not running"

# 6. launchd
echo "6. launchd services:"
launchctl list com.trademaster.api &>/dev/null && echo "  API: ✅ loaded" || echo "  API: ❌ not loaded"
launchctl list com.trademaster.view &>/dev/null && echo "  View: ✅ loaded" || echo "  View: ❌ not loaded"

# 7. Cron
echo "7. OpenClaw Cron:"
openclaw cron list 2>/dev/null | tail -n +3 | awk '{print "  " $0}' | head -15
```

## 六、故障恢復

### API 無回應

```bash
# 步驟 1: 檢查進程
ps aux | grep api_server

# 步驟 2: 檢查日誌
tail -50 logs/api_launchd_err.log

# 步驟 3: 強制重啟
bash scripts/tm-ctl.sh restart api
```

### View 無回應

```bash
# 步驟 1: 確認 dist/ 存在
ls dist/index.html

# 步驟 2: 檢查日誌
tail -50 ~/.openclaw/workspace/codes/TradeMasterView/logs/view_launchd_err.log

# 步驟 3: 重啟
bash scripts/tm-ctl.sh restart view
```

### API proxy 502

```bash
# 通常是 API 掛了，View 還活著
curl -sf http://127.0.0.1:8080/health   # 先確認 API
bash scripts/tm-ctl.sh restart api       # 重啟 API
```
