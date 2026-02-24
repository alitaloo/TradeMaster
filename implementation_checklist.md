# TradeMaster v2 第一階段實施清單 (v2)

## 任務總覽

| ID | 任務 | 優先順序 | 工作量 |
|----|------|----------|--------|
| 1 | 數據庫遷移 | P0 | 🟡 中 |
| 2 | API 端點 (Signals/Positions/Orders) | P0 | 🔴 大 |
| 3 | 風控引擎 | P0 | 🟡 中 |
| 4 | 持倉管理模組 | P1 | 🟡 中 |
| 5 | 認證與權限 | P1 | 🟡 中 |
| 6 | 日誌與監控 | P2 | 🟢 小 |

---

## 任務 1: 數據庫遷移 (P0)

**目標**: 為現有數據庫添加新表和欄位

**注意**: 需要先創建 `migrations/` 目錄

**產出**: `migrations/migrate_v2.py`, `migrations/001_signals.sql`, `migrations/002_positions.sql`, `migrations/003_orders.sql`

### 子任務

| ID | 子任務 | 功能描述 | 產出文件 | 驗收標準 |
|----|--------|----------|----------|----------|
| 1.1 | 創建 signals 表 | 存儲交易信號 | `migrations/001_signals.sql` | 表創建成功，結構正確 |
| 1.2 | 創建 positions 表 | 存儲持倉信息 | `migrations/002_positions.sql` | 表創建成功，結構正確 |
| 1.3 | 創建 orders 表 | 存儲訂單信息 | `migrations/003_orders.sql` | 表創建成功，結構正確 |
| 1.4 | 創建 user_settings 表 | 存儲用戶配置 | `migrations/004_user_settings.sql` | 表創建成功，結構正確 |
| 1.5 | 執行遷移腳本 | 運行 SQL 遷移 | `migrations/migrate_v2.py` | 所有表創建成功 |
| 1.6 | 創建回滾腳本 | 數據回滾能力 | `migrations/rollback_v2.py` | 可完整回滾 |

**驗收標準**:
- [ ] 所有新表創建成功
- [ ] 舊數據正確遷移
- [ ] 回滾腳本可執行

---

## 任務 2: API 端點 (P0)

**目標**: 提供 Signals/Positions/Orders 的 CRUD 接口

**產出**: `api/signals_bp.py`, `api/positions_bp.py`, `api/orders_bp.py`

### 2.1 Signals API

| ID | 子任務 | 功能描述 | 產出文件 | 驗收標準 |
|----|--------|----------|----------|----------|
| 2.1.1 | GET /signals | 獲取信號列表 | `api/signals_bp.py` | 返回信號列表，支持篩選 |
| 2.1.2 | GET /signals/:id | 獲取單個信號 | `api/signals_bp.py` | 返回信號詳情 |
| 2.1.3 | POST /signals | 創建新信號 | `api/signals_bp.py` | 信號創建成功 |
| 2.1.4 | PUT /signals/:id | 更新信號 | `api/signals_bp.py` | 信號更新成功 |
| 2.1.5 | DELETE /signals/:id | 刪除信號 | `api/signals_bp.py` | 信號刪除成功 |
| 2.1.6 | GET /signals/active | 獲取活躍信號 | `api/signals_bp.py` | 返回當前活躍信號 |

### 2.2 Positions API

| ID | 子任務 | 功能描述 | 產出文件 | 驗收標準 |
|----|--------|----------|----------|----------|
| 2.2.1 | GET /positions | 獲取持倉列表 | `api/positions_bp.py` | 返回持倉列表 |
| 2.2.2 | GET /positions/:symbol | 獲取單個持倉 | `api/positions_bp.py` | 返回持倉詳情 |
| 2.2.3 | POST /positions | 創建持倉記錄 | `api/positions_bp.py` | 持倉創建成功 |
| 2.2.4 | PUT /positions/:symbol | 更新持倉 | `api/positions_bp.py` | 持倉更新成功 |
| 2.2.5 | DELETE /positions/:symbol | 刪除持倉 | `api/positions_bp.py` | 持倉刪除成功 |
| 2.2.6 | GET /positions/summary | 持倉摘要 | `api/positions_bp.py` | 返回總市值、盈虧等 |

### 2.3 Orders API

| ID | 子任務 | 功能描述 | 產出文件 | 驗收標準 |
|----|--------|----------|----------|----------|
| 2.3.1 | GET /orders | 獲取訂單列表 | `api/orders_bp.py` | 返回訂單列表 |
| 2.3.2 | GET /orders/:id | 獲取單個訂單 | `api/orders_bp.py` | 返回訂單詳情 |
| 2.3.3 | POST /orders | 創建新訂單 | `api/orders_bp.py` | 訂單創建成功 |
| 2.3.4 | PUT /orders/:id | 更新訂單狀態 | `api/orders_bp.py` | 訂單狀態更新成功 |
| 2.3.5 | DELETE /orders/:id | 取消訂單 | `api/orders_bp.py` | 訂單取消成功 |
| 2.3.6 | GET /orders/status/:status | 按狀態篩選 | `api/orders_bp.py` | 返回指定狀態訂單 |

**驗收標準**:
- [ ] 所有端點返回正確 JSON
- [ ] 錯誤處理完善
- [ ] 單元測試通過 > 80%

---

## 任務 3: 風控引擎 (P0)

**目標**: 實現交易前的風險檢查

**產出**: `core/risk_engine.py`

| ID | 子任務 | 功能描述 | 產出文件 | 驗收標準 |
|----|--------|----------|----------|----------|
| 3.1 | 單筆金額檢查 | 檢查單筆金額上限 | `core/risk_engine.py` | 超限返回 False |
| 3.2 | 總倉位檢查 | 檢查總持倉上限 | `core/risk_engine.py` | 超限返回 False |
| 3.3 | 止損檢查 | 檢查止損設置 | `core/risk_engine.py` | 未設置返回警告 |
| 3.4 | 杠桿檢查 | 檢查杠桿倍數 | `core/risk_engine.py` | 超限返回 False |
| 3.5 | 風險評分 | 綜合風險評分 | `core/risk_engine.py` | 返回 0-100 評分 |
| 3.6 | 風控攔截 | 整合所有檢查 | `core/risk_engine.py` | 返回通過/攔截結果 |

**驗收標準**:
- [ ] 所有檢查函數可執行
- [ ] 風險評分邏輯正確
- [ ] 單元測試通過

---

## 任務 4: 持倉管理模組 (P1)

**目標**: 實現持倉的完整管理邏輯

**產出**: `core/position_manager.py`

| ID | 子任務 | 功能描述 | 產出文件 | 驗收標準 |
|----|--------|----------|----------|----------|
| 4.1 | 持倉初始化 | 從數據庫加載持倉 | `core/position_manager.py` | 持倉正確加載 |
| 4.2 | 持倉更新 | 更新持倉數據 | `core/position_manager.py` | 數據更新正確 |
| 4.3 | 持倉計算 | 計算持倉價值/盈虧 | `core/position_manager.py` | 計算正確 |
| 4.4 | 持倉同步 | 與券商同步 | `core/position_manager.py` | 同步成功 |
| 4.5 | 持倉報警 | 監控持倉風險 | `core/position_manager.py` | 及時觸發報警 |
| 4.6 | 持倉歷史 | 記錄持倉變更 | `core/position_manager.py` | 記錄完整 |

**驗收標準**:
- [ ] 持倉數據正確
- [ ] 盈虧計算正確
- [ ] 單元測試通過

---

## 任務 5: 認證與權限 (P1)

**目標**: API 安全認證

**產出**: `api/auth_bp.py`, `middleware/auth.py`

| ID | 子任務 | 功能描述 | 產出文件 | 驗收標準 |
|----|--------|----------|----------|----------|
| 5.1 | API Key 認證 | API Key 驗證 | `middleware/auth.py` | Key 正確驗證 |
| 5.2 | 權限檢查 | 檢查用戶權限 | `middleware/auth.py` | 權限正確判斷 |
| 5.3 | 認證 API | 獲取 Access Token | `api/auth_bp.py` | Token 正確頒發 |

**驗收標準**:
- [ ] 認證流程正確
- [ ] 未授權訪問被攔截
- [ ] 單元測試通過

---

## 任務 6: 日誌與監控 (P2)

**目標**: 系統日誌和監控

**產出**: `utils/logger.py`, `utils/metrics.py`

| ID | 子任務 | 功能描述 | 產出文件 | 驗收標準 |
|----|--------|----------|----------|----------|
| 6.1 | 結構化日誌 | 統一日誌格式 | `utils/logger.py` | 日誌正確記錄 |
| 6.2 | API 監控 | 請求/響應監控 | `utils/metrics.py` | 指標正確收集 |
| 6.3 | 錯誤追蹤 | 異常記錄 | `utils/logger.py` | 錯誤正確記錄 |

**驗收標準**:
- [ ] 日誌寫入正常
- [ ] 監控指標正確
- [ ] 錯誤可追蹤

---

## 前端調整對照表

根據改造文檔，前端位於獨立項目 `codes/TradeMasterView/`：

| 前端文件 | 調整內容 | 對應後端 API | 驗收標準 |
|----------|----------|--------------|----------|
| `views/Signals.vue` | 信號列表/詳情 | `/api/v1/signals` | API 調用成功，數據正確顯示 |
| `views/Stocks.vue` | 持倉列表/詳情 | `/api/v1/positions` | API 調用成功，持倉計算正確 |
| `views/Orders.vue` (新建) | 訂單列表/詳情 | `/api/v1/orders` | API 調用成功，狀態正確顯示 |
| `views/RiskDashboard.vue` (新建) | 風控儀表板 | `/api/v1/positions/summary` | 風控指標正確計算 |
| `views/Auth.vue` (新建) | 登入/權限 | `/api/v1/auth` | 認證正確，權限控制生效 |

**前端驗收標準**:
- [ ] 所有新 API 正確調用
- [ ] 錯誤處理完善
- [ ] UI 與后端同步

---

## 部署驗收清單

- [ ] 數據庫遷移腳本執行成功
- [ ] API 端點響應正常 (Signals/Positions/Orders)
- [ ] 風控引擎攔截正確
- [ ] 持倉管理功能完整
- [ ] 認證與權限生效
- [ ] 日誌記錄正常
- [ ] 前端調整完成
- [ ] 單元測試通過率 > 80%
- [ ] API 文檔更新完成
