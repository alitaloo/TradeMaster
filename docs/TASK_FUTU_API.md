# TradeMaster 富途牛牛 API 對接任務

**任務目標：** 整合富途牛牛 Open API 提供穩定的 5 分鐘 K 線數據

**參考文檔：** https://futapi.github.io/

---

## 任務清單

### 1. 安裝富途牛牛 API
```bash
pip install futu
```

### 2. 創建 `api/futu_kline.py`

**功能需求：**

```python
#!/usr/bin/env python3
"""
富途牛牛 K 線數據 API
支持港股、美股、A 股的實時和歷史數據
"""

from flask import Blueprint, jsonify, request
import futu as ft
from datetime import datetime
import json

futu_bp = Blueprint('futu_kline', __name__)

class FutuClient:
    """富途牛牛客戶端封裝"""
    
    def __init__(self, host='127.0.0.1', port=11111):
        self.host = host
        self.port = port
        self.quote_ctx = None
        self.trade_ctx = None
    
    def connect(self):
        """連接富途牛牛"""
        self.quote_ctx = ft.OpenQuoteContext(host=self.host, port=self.port)
        # 登入（如果需要）
        return self.quote_ctx is not None
    
    def close(self):
        """關閉連接"""
        if self.quote_ctx:
            self.quote_ctx.close()
    
    def get_kline(self, symbol, interval='5m', limit=100        獲取):
        """
 K 線數據
        
        Args:
            symbol: 股票代號 (如 'US.AAPL', 'HK.00700')
            interval: 時間區間 ('1m', '5m', '15m', '30m', '1h', '1d', '1w', '1M')
            limit: 返回數據數量
        
        Returns:
            dict: K 線數據
        """
        # 轉換時間區間格式
        kl_type_map = {
            '1m': ft.KLType.MIN1,
            '5m': ft.KLType.MIN5,
            '15m': ft.KLType.MIN15,
            '30m': ft.KLType.MIN30,
            '1h': ft.KLType.HOUR1,
            '1d': ft.KLType.DAY,
            '1w': ft.KLType.WEEK,
            '1M': ft.KLType.MONTH
        }
        
        kl_type = kl_type_map.get(interval, ft.KLType.MIN5)
        
        # 請求 K 線
        ret, data = self.quote_ctx.request_history_kline(
            symbol,
            start='2020-01-01',
            end=datetime.now().strftime('%Y-%m-%d'),
            kl_type=kl_type,
            fields=['time', 'open', 'close', 'high', 'low', 'volume']
        )
        
        if ret == ft.RetType.OK:
            return {
                'status': 'ok',
                'symbol': symbol,
                'interval': interval,
                'data': data.to_dict('records')[-limit:]
            }
        else:
            return {
                'status': 'error',
                'symbol': symbol,
                'error': data
            }
    
    def get_realtime_quote(self, symbols):
        """
        獲取實時報價
        
        Args:
            symbols: 股票代號列表
        
        Returns:
            dict: 實時報價
        """
        ret, data = self.quote_ctx.get_market_snapshot(symbols)
        
        if ret == ft.RetType.OK:
            return {
                'status': 'ok',
                'data': data.to_dict('records')
            }
        else:
            return {
                'status': 'error',
                'error': data
            }


# 全局客戶端實例
futu_client = None

def get_client():
    """獲取富途牛牛客戶端"""
    global futu_client
    if futu_client is None:
        futu_client = FutuClient()
        futu_client.connect()
    return futu_client


@futu_bp.route('/api/v1/futu/kline', methods=['GET'])
def get_kline():
    """獲取 K 線數據"""
    symbol = request.args.get('symbol', 'US.AAPL')
    interval = request.args.get('interval', '5m')
    limit = int(request.args.get('limit', 100))
    
    client = get_client()
    result = client.get_kline(symbol, interval, limit)
    
    return jsonify(result)


@futu_bp.route('/api/v1/futu/quote', methods=['GET'])
def get_quote():
    """獲取實時報價"""
    symbols = request.args.get('symbols', 'US.AAPL,US.MSFT').split(',')
    symbols = [s.strip() for s in symbols if s.strip()]
    
    client = get_client()
    result = client.get_realtime_quote(symbols)
    
    return jsonify(result)


@futu_bp.route('/api/v1/futu/connect', methods=['POST'])
def connect():
    """連接富途牛牛"""
    client = get_client()
    if client.connect():
        return jsonify({'status': 'ok', 'message': 'Connected to Futu'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to connect'}), 500


@futu_bp.route('/api/v1/futu/disconnect', methods=['POST'])
def disconnect():
    """斷開連接"""
    global futu_client
    if futu_client:
        futu_client.close()
        futu_client = None
    return jsonify({'status': 'ok', 'message': 'Disconnected'})


@futu_bp.route('/api/v1/futu/status', methods=['GET'])
def status():
    """檢查連接狀態"""
    global futu_client
    connected = futu_client is not None
    return jsonify({
        'status': 'ok',
        'connected': connected,
        'timestamp': datetime.now().isoformat()
    })
```

### 3. 更新 `api/__init__.py`

```python
from .futu_kline import futu_bp

__all__ = [..., 'futu_bp']
```

### 4. 更新 `api_server.py`

```python
from api import futu_bp

app.register_blueprint(futu_bp)
```

### 5. 創建任務測試腳本 `scripts/test_futu_api.py`

```python
#!/usr/bin/env python3
"""
測試富途牛牛 API
"""

import sys
sys.path.insert(0, '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2')

from api.futu_kline import FutuClient

def test_kline():
    """測試 K 線獲取"""
    client = FutuClient()
    
    if not client.connect():
        print("❌ 連接失敗，請確保富途牛牛已打開")
        return
    
    print("✅ 連接成功")
    
    # 測試美股
    print("\n📊 測試美股 AAPL...")
    result = client.get_kline('US.AAPL', '5m', 10)
    print(f"狀態: {result['status']}")
    if result['status'] == 'ok':
        print(f"獲取 {len(result['data'])} 根 K 線")
        print(result['data'][-1] if result['data'] else "無數據")
    else:
        print(f"錯誤: {result.get('error')}")
    
    # 測試港股
    print("\n📊 測試港股 00700...")
    result = client.get_kline('HK.00700', '5m', 10)
    print(f"狀態: {result['status']}")
    
    client.close()
    print("\n✅ 測試完成")

if __name__ == '__main__':
    test_kline()
```

---

## API 端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/v1/futu/kline` | GET | 獲取 K 線數據 |
| `/api/v1/futu/quote` | GET | 獲取實時報價 |
| `/api/v1/futu/connect` | POST | 連接富途牛牛 |
| `/api/v1/futu/disconnect` | POST | 斷開連接 |
| `/api/v1/futu/status` | GET | 檢查連接狀態 |

## 使用範例

```bash
# 獲取 AAPL 5 分鐘 K 線
curl "http://localhost:8080/api/v1/futu/kline?symbol=US.AAPL&interval=5m"

# 獲取實時報價
curl "http://localhost:8080/api/v1/futu/quote?symbols=US.AAPL,US.MSFT"

# 檢查連接狀態
curl "http://localhost:8080/api/v1/futu/status"
```

## 注意事項

1. **富途牛牛必須打開**：需要安裝富途牛牛客戶端並登入
2. **API 連接**：默認連接 `127.0.0.1:11111`
3. **股票代號格式**：
   - 美股：`US.AAPL`, `US.MSFT`, `US.NVDA`
   - 港股：`HK.00700`, `HK.03690`
   - A 股：`SH.600519`, `SZ.000001`

---

## Deliverable

1. ✅ 安裝 futu Python 庫
2. ✅ 創建 `api/futu_kline.py`
3. ✅ 更新 `api/__init__.py`
4. ✅ 更新 `api_server.py`
5. ✅ 創建測試腳本 `scripts/test_futu_api.py`
6. ✅ 驗證 API 可正常運行

---

## 參考文檔

- **富途牛牛 API 文檔：** https://futapi.github.io/
- **GitHub：** https://github.com/futapi/futpy
