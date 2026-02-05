# Gateway Version Sync Tool

自動確保 Gateway 版本與 OpenClaw 一致

## 使用方法

### 方法 1：手動執行（Windows）
```batch
# 在啟動 OpenClaw 前執行
gateway_sync.bat
```

### 方法 2：添加到 npm 生命週期鉤子

在你的 `package.json` 中添加：
```json
{
  "scripts": {
    "preupdate": "node gateway_sync.js",
    "postinstall": "node gateway_sync.js",
    "sync": "node gateway_sync.js"
  }
}
```

### 方法 3：定時任務（Windows）
```batch
# 建立排程，每小時檢查一次
schtasks /create /tn "TradeMaster Gateway Sync" /tr "gateway_sync.bat" /sc hourly
```

## 檔案結構

```
tools/
├── gateway_sync.js    # Node.js 版本檢查腳本
├── gateway_sync.bat   # Windows Batch 執行檔
└── package.json      # npm 腳本配置
```

## 功能

1. 檢查當前安裝的 OpenClaw 版本
2. 比對配置文件中的版本
3. 如果不一致，自動執行 `openclaw gateway restart`
4. 輸出結果並退出

## 日誌

成功時輸出 `✅`，失敗時輸出 `❌` 並返回錯誤碼
