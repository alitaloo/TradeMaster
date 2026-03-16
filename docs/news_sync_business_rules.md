# 新聞同步業務規則定義

## 1. News API Error / Degraded vs 真的 0 News Weight

### 業務語意差別

| 場景 | 業務語意 | API 返回值 |
|------|---------|-----------|
| **RSS API 失敗** (Yahoo/Google 都無法連線) | 同步服務異常，非「無新聞」| 視為 `degraded` 或 `error` 狀態 |
| **RSS 有返回但數據為空** | 該股票確實沒有新聞 | `news_count: 0`，這是正常結果 |
| **News 分析 API 失敗** | 同步中某環節異常 | 仍寫入 DB，weight 預設為 0 |
| **數據庫中無數據** (從未同步過) | 未知狀態 | 需標記為 `unknown` 而非 `quiet` |

### 判斷邏輯

```
IF (RSS fetch error count == 2) THEN:
    → 狀態 = "error" / "degraded"
    → fox analysis 應視為「無法判斷新聞風險」，需告警或繞過

IF (RSS fetch success AND news_count == 0) THEN:
    → 狀態 = "quiet" (真的 0 news weight)
    → fox analysis 正常處理，視為 news:quiet

IF (RSS fetch success AND news_count > 0) THEN:
    → 根據 total_weight 計算風險
```

---

## 2. Fox Analysis 應暴露的狀態欄位

### News API `/news/weight/<symbol>` 現有返回

```json
{
  "status": "ok",
  "symbol": "TSLA",
  "total_weight": 5,
  "news_count": 3,
  "breakdown": {
    "positive": 1,
    "negative": 1,
    "neutral": 1
  },
  "hours": 24
}
```

### 建議新增欄位（最小改動）

```json
{
  "status": "ok",
  "symbol": "TSLA",
  "total_weight": 5,
  "news_count": 3,
  "breakdown": {...},
  "hours": 24,
  // === 新增欄位 ===
  "sync_status": "ok",          // "ok" | "degraded" | "error" | "unknown"
  "sync_error": null,            // 若有錯誤，記錄錯誤訊息
  "last_sync_time": "2026-03-12T22:00:00+08:00",  // 最近同步時間
  "is_stale": false             // 是否過期（超過 6 小時未同步）
}
```

### Fox Analysis 判斷規則

```python
# 當 sync_status != "ok" 時，fox analysis 應：
if news_data.get('sync_status') == 'error':
    # API 完全失敗，不應執行交易
    news_ok = False
    news_reason = "新聞同步失敗，無法評估風險"
elif news_data.get('sync_status') == 'degraded':
    # 部分失敗，降級處理
    news_ok = False
    news_reason = "新聞同步降級，建議謹慎"
elif news_data.get('is_stale'):
    # 數據過期
    news_ok = False
    news_reason = "新聞數據過期，超過 6 小時未更新"
elif news_weight == 0:
    # 真的 0 news weight = quiet
    news_ok = True
    news_reason = "新聞權重為 0 (安靜)"
else:
    # 正常處理
    ...
```

---

## 3. DB 去重策略確認

### 現有策略（fetch_news_rss.py）

- **去重依據**: URL MD5 hash
- **時間窗口**: 最近 24 小時內的 URL 不重複寫入
- **實作**: `NewsDeduplicator` 類別，載入 DB 中 24 小時內的 URL hash

### 業務評估

| 項目 | 評估 |
|------|------|
| **同 URL 視為同新聞** | ✅ 可接受 - URL 是新聞的天然唯一標識 |
| **24 小時窗口** | ✅ 可接受 - 新聞有時效性，24 小時夠用 |
| **風險**: 同一新聞不同來源不同 URL | ⚠️ 輕微風險 - Yahoo/Google 可能抓同一則新聞但 URL 不同 |
| **風險**: 同一新聞更新內容但 URL 不變 | ✅ 可接受 - 視為同一則新聞的更新 |

### 建議

1. **保持現有策略** - URL 去重是業界標準做法
2. **可選優化**: 若要更精確，可加入 `title` + `published` 的去重，但非必要

---

## 4. 最小落地內容

### 4.1 代碼註解（fetch_news_rss.py）

在 `sync_news_for_symbol` 函數開頭加入狀態追蹤：

```python
def sync_news_for_symbol(symbol: str, limit: int = 10, dry_run: bool = False) -> dict:
    """
    為指定股票同步新聞
    
    Returns:
        dict: {
            'synced_count': int,
            'status': 'ok' | 'degraded' | 'error',
            'error': str | None,
            'news_count': int,
            'last_sync': datetime
        }
    """
    # ... existing code ...
```

### 4.2 Fox Analysis 兼容處理

在 `fox_analysis_v2.py` 的 `get_news_weight` 函數中：

```python
def get_news_weight(symbol: str, hours: int = 24) -> Dict:
    """獲取股票新聞權重
    
    注意：
    - news_count == 0 且 sync_status == 'ok' = 真的沒有新聞 (quiet)
    - sync_status == 'error'/'degraded' = 同步失敗，需告警
    - is_stale == True = 數據過期，需重新同步
    """
    # ... existing code ...
    
    # 新增：兼容舊版 API（無 sync_status 欄位）
    if 'sync_status' not in result:
        # 舊版兼容：若 total_weight=0 且 news_count=0，假設為 ok
        result['sync_status'] = 'ok' if result.get('news_count', 0) == 0 else 'ok'
        result['is_stale'] = False
    
    return result
```

---

## 5. 工程注意事項

1. **不要大改 DB schema** - 避免新增欄位，未來可考慮在 sync_checkpoints 表記錄 sync_status
2. **保持向後兼容** - fox_analysis_v2.py 需兼容沒有 sync_status 欄位的舊版 API
3. **錯誤傳遞** - RSS fetch 失敗時需記錄日誌，並在返回值中標記
4. **監控** - 建議監控 `sync_status != 'ok'` 的次數

---

## 6. 交 QA 前檢查清單

- [ ] RSS 全部失敗時，fox analysis 是否阻擋交易？
- [ ] RSS 返回空數據時，fox analysis 是否正常識別為 quiet？
- [ ] News API 完全無法連線時，是否有合理錯誤訊息？
- [ ] 去重邏輯是否正常運作（相同 URL 不會重複寫入）？
- [ ] 向後兼容：無 sync_status 欄位時是否正常運作？

