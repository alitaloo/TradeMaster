# TradeMaster 富途牛牛 API 測試與 K 線圖表優化任務

**任務目標：**
1. 測試富途牛牛客戶端連接
2. 優化 K 線監控頁面，展示詳細數據和圖表

---

## 任務 1：測試富途牛牛 API 連接

### 步驟 1：確保富途牛牛客戶端已開啟
- 打開富途牛牛客戶端
- 確認已登入帳戶
- 檢查 API 端口是否開通（默認 11111）

### 步驟 2：運行測試腳本
```bash
cd /Users/alita/.openclaw/workspace/codes/TradeMaster_v2
python3 scripts/test_futu_api.py
```

### 步驟 3：測試 API 端點

```bash
# 測試連接狀態
curl http://localhost:8080/api/v1/futu/status

# 測試 K 線獲取（美股 AAPL）
curl "http://localhost:8080/api/v1/futu/kline?symbol=US.AAPL&interval=5m"

# 測試實時報價
curl "http://localhost:8080/api/v1/futu/quote?symbols=US.AAPL,US.MSFT,US.NVDA"
```

### 步驟 4：記錄測試結果
- 如果連接成功，記錄輸出
- 如果失敗，記錄錯誤信息

---

## 任務 2：優化 K 線監控頁面

### 優化目標

**當前問題：**
1. 沒有展示 K 線詳細數據（收盤價、最高、最低等）
2. 沒有 Y 軸價格標籤
3. 沒有 X 軸時間標籤
4. 圖表不夠詳細

**目標效果：**
1. 展示 K 線詳細數據表格
2. 完整的 Y 軸價格標籤
3. 完整的 X 軸時間標籤
4. 滑鼠懸停顯示詳細信息
5. 價格區間標記

### 優化內容

#### 2.1 添加 Y 軸價格標籤

```javascript
// 在 Canvas 繪製後添加 Y 軸標籤
function drawYAxisLabels(canvas, data) {
    const ctx = canvas.getContext('2d')
    const prices = data.map(d => d.close)
    const minPrice = Math.min(...prices) * 0.99
    const maxPrice = Math.max(...prices) * 1.01
    const priceRange = maxPrice - minPrice
    const height = canvas.height - 60 // 留出空間
    
    // 繪製 5 個價格標籤
    for (let i = 0; i <= 5; i++) {
        const price = minPrice + (priceRange * i / 5)
        const y = height - (height * i / 5)
        ctx.fillStyle = '#ffffff'
        ctx.font = '12px Arial'
        ctx.fillText('$' + price.toFixed(2), canvas.width - 50, y)
    }
}
```

#### 2.2 添加 X 軸時間標籤

```javascript
// 添加 X 軸時間標籤
function drawXAxisLabels(canvas, data) {
    const ctx = canvas.getContext('2d')
    const width = canvas.width - 60 // 留出空間
    const step = width / (data.length - 1)
    
    // 每 4 個 K 線顯示一個時間標籤
    for (let i = 0; i < data.length; i += 4) {
        const x = 60 + (i * step)
        const time = new Date(data[i].timestamp)
        const timeStr = time.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
        
        ctx.fillStyle = '#ffffff'
        ctx.font = '12px Arial'
        ctx.fillText(timeStr, x, canvas.height - 10)
    }
}
```

#### 2.3 添加詳細數據表格

```vue
<!-- K 線詳細數據 -->
<div class="kline-details" v-if="selectedKline">
  <h3>📊 {{ selectedStock }} K 線詳細數據</h3>
  <table class="data-table">
    <thead>
      <tr>
        <th>時間</th>
        <th>開盤</th>
        <th>最高</th>
        <th>最低</th>
        <th>收盤</th>
        <th>成交量</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="kline in klineData" :key="kline.timestamp"
          :class="{ 'selected': selectedKline === kline }"
          @click="selectKline(kline)">
        <td>{{ formatTime(kline.timestamp) }}</td>
        <td>${{ kline.open }}</td>
        <td>${{ kline.high }}</td>
        <td>${{ kline.low }}</td>
        <td :class="kline.close >= kline.open ? 'up' : 'down'">
          ${{ kline.close }}
        </td>
        <td>{{ formatVolume(kline.volume) }}</td>
      </tr>
    </tbody>
  </table>
</div>
```

#### 2.4 添加滑鼠懸停效果

```javascript
// 滑鼠懸停顯示詳細信息
canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    
    // 找到最近的 K 線
    const klineIndex = Math.floor((x - 60) / klineWidth)
    if (klineIndex >= 0 && klineIndex < klineData.length) {
        const kline = klineData[klineIndex]
        showTooltip(kline, x, y)
    }
})
```

#### 2.5 添加價格區間標記

```javascript
// 繪製支撐/壓力線
function drawPriceLevels(canvas, data) {
    const prices = data.map(d => d.close)
    const avgPrice = prices.reduce((a, b) => a + b) / prices.length
    
    // 繪製平均價格線
    const y = priceToY(avgPrice)
    ctx.strokeStyle = 'rgba(255, 206, 86, 0.5)'
    ctx.setLineDash([5, 5])
    ctx.beginPath()
    ctx.moveTo(60, y)
    ctx.lineTo(canvas.width, y)
    ctx.stroke()
    ctx.setLineDash([])
    
    // 添加標籤
    ctx.fillStyle = '#ffca56'
    ctx.fillText('均價: $' + avgPrice.toFixed(2), 65, y - 5)
}
```

### 2.6 完整的前端組件更新

更新 `RealtimeMonitor.vue`：

```vue
<template>
  <div class="realtime-page">
    <!-- 現有的股票選擇和圖表區域 -->
    
    <!-- 新增：K 線詳細數據表格 -->
    <div class="kline-details-panel">
      <h3>📊 K 線詳細數據</h3>
      <div class="table-container">
        <table class="kline-table">
          <thead>
            <tr>
              <th>時間</th>
              <th>開盤</th>
              <th>最高</th>
              <th>最低</th>
              <th>收盤</th>
              <th>漲跌幅</th>
              <th>成交量</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="k in displayedKlines" :key="k.timestamp"
                :class="{ 'selected': selectedKline?.timestamp === k.timestamp }"
                @click="selectKline(k)">
              <td>{{ formatTime(k.timestamp) }}</td>
              <td>${{ k.open.toFixed(2) }}</td>
              <td class="high">${{ k.high.toFixed(2) }}</td>
              <td class="low">${{ k.low.toFixed(2) }}</td>
              <td :class="getPriceClass(k)">${{ k.close.toFixed(2) }}</td>
              <td :class="getChangeClass(k)">{{ getChangePercent(k) }}%</td>
              <td>{{ formatVolume(k.volume) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
```

### 樣式更新

```css
.kline-details-panel {
  margin-top: 20px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
}

.kline-details-panel h3 {
  color: #ffffff !important;
  margin-bottom: 16px;
}

.table-container {
  overflow-x: auto;
}

.kline-table {
  width: 100%;
  border-collapse: collapse;
}

.kline-table th,
.kline-table td {
  padding: 12px 16px;
  text-align: right;
  border-bottom: 1px solid var(--color-border);
  color: #ffffff !important;
}

.kline-table th {
  background: var(--color-bg-tertiary);
  font-weight: 600;
}

.kline-table tr:hover {
  background: rgba(233, 69, 96, 0.1);
}

.kline-table tr.selected {
  background: rgba(233, 69, 96, 0.2);
}

.kline-table td.high {
  color: var(--color-success) !important;
}

.kline-table td.low {
  color: var(--color-danger) !important;
}

.kline-table td.up {
  color: var(--color-success) !important;
}

.kline-table td.down {
  color: var(--color-danger) !important;
}
```

---

## 驗收標準

### API 測試
- [ ] 富途牛牛客戶端可連接
- [ ] `/api/v1/futu/status` 返回 connected: true
- [ ] `/api/v1/futu/kline` 返回正確的 K 線數據
- [ ] `/api/v1/futu/quote` 返回正確的報價數據

### 前端優化
- [ ] Y 軸顯示價格標籤
- [ ] X 軸顯示時間標籤
- [ ] 展示 K 線詳細數據表格
- [ ] 表格支持點擊選擇
- [ ] 滑鼠懸停顯示詳細信息
- [ ] 價格漲跌用顏色區分（綠漲紅跌）

---

## 參考

- **富途牛牛 API 文檔**: https://futapi.github.io/
- **RealtimeMonitor.vue**: `/Users/alita/.openclaw/workspace/codes/TradeMasterView/src/views/RealtimeMonitor.vue`
- **K 線 API**: `/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/api/futu_kline.py`

---

## Deliverable

1. **API 測試報告**
   - 連接狀態
   - 測試結果
   - 問題記錄

2. **前端優化更新**
   - 更新 RealtimeMonitor.vue
   - 添加 Y 軸/X 軸標籤
   - 添加詳細數據表格
   - 截圖展示效果
