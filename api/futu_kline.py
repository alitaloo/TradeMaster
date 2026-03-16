#!/usr/bin/env python3
"""
富途牛牛 K 線數據 API
支持港股、美股、A 股的實時和歷史數據
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timezone, timedelta
import json

_TZ_TAIPEI = timezone(timedelta(hours=8))

# 嘗試導入 futu 庫，如果不可用則使用 Mock
try:
    import futu as ft
    # 檢查必要的屬性是否存在
    if hasattr(ft, 'OpenQuoteContext') and hasattr(ft, 'KLType') and hasattr(ft, 'RetType'):
        FUTU_AVAILABLE = True
    else:
        FUTU_AVAILABLE = False
        raise ImportError("Futu library attributes not found")
except ImportError:
    FUTU_AVAILABLE = False
    # Mock 類用於測試
    class MockFutu:
        class KLType:
            MIN1 = '1m'
            MIN5 = '5m'
            MIN15 = '15m'
            MIN30 = '30m'
            HOUR1 = '1h'
            DAY = '1d'
            WEEK = '1w'
            MONTH = '1M'
        
        class RetType:
            OK = 'OK'
        
        class OpenQuoteContext:
            def __init__(self, host='127.0.0.1', port=11111):
                self.host = host
                self.port = port
            
            def request_history_kline(self, symbol, start, end, kl_type, fields):
                return (False, "Futu library not connected - using mock data")
            
            def get_market_snapshot(self, symbols):
                return (False, "Futu library not connected - using mock data")
            
            def close(self):
                pass
    
    ft = MockFutu()

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
        if not FUTU_AVAILABLE:
            print("⚠️  Futu library not installed, using mock mode")
            return False
        
        self.quote_ctx = ft.OpenQuoteContext(host=self.host, port=self.port)
        return self.quote_ctx is not None
    
    def close(self):
        """關閉連接"""
        if self.quote_ctx:
            self.quote_ctx.close()
    
    def get_kline(self, symbol, interval='5m', limit=100):
        """
        獲取 K 線數據
        
        Args:
            symbol: 股票代號 (如 'US.AAPL', 'HK.00700')
            interval: 時間區間 ('1m', '5m', '15m', '30m', '1h', '1d', '1w', '1M')
            limit: 返回數據數量
        
        Returns:
            dict: K 線數據
        """
        if not FUTU_AVAILABLE or not self.quote_ctx:
            return self._mock_kline_data(symbol, interval, limit)
        
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
                'error': str(data)
            }
    
    def get_realtime_quote(self, symbols):
        """
        獲取實時報價
        
        Args:
            symbols: 股票代號列表
        
        Returns:
            dict: 實時報價
        """
        if not FUTU_AVAILABLE or not self.quote_ctx:
            return self._mock_quote_data(symbols)
        
        ret, data = self.quote_ctx.get_market_snapshot(symbols)
        
        if ret == ft.RetType.OK:
            return {
                'status': 'ok',
                'data': data.to_dict('records')
            }
        else:
            return {
                'status': 'error',
                'error': str(data)
            }
    
    def _mock_kline_data(self, symbol, interval, limit):
        """生成 Mock K 線數據"""
        import random
        from datetime import timedelta
        
        base_price = 100.0
        if symbol.startswith('HK.'):
            base_price = 300.0
        elif symbol.startswith('SH.') or symbol.startswith('SZ.'):
            base_price = 50.0
        
        data = []
        interval_minutes = 5 if interval == '5m' else 1
        base_time = datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
        
        for i in range(limit):
            price_change = random.uniform(-2, 2)
            open_price = base_price + random.uniform(-5, 5)
            close_price = open_price + price_change
            high_price = max(open_price, close_price) + random.uniform(0, 1)
            low_price = min(open_price, close_price) - random.uniform(0, 1)
            volume = int(random.uniform(1000000, 10000000))
            
            data.append({
                'time': (base_time.replace(tzinfo=_TZ_TAIPEI) + timedelta(minutes=i * interval_minutes)).strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                'open': round(open_price, 2),
                'close': round(close_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'volume': volume
            })
        
        return {
            'status': 'mock',
            'symbol': symbol,
            'interval': interval,
            'data': data,
            'note': 'Mock data - Futu library not connected'
        }
    
    def _mock_quote_data(self, symbols):
        """生成 Mock 報價數據"""
        import random
        data = []
        for symbol in symbols:
            price = 100.0
            if symbol.startswith('HK.'):
                price = 300.0
            elif symbol.startswith('SH.') or symbol.startswith('SZ.'):
                price = 50.0
            
            change = random.uniform(-5, 5)
            data.append({
                'code': symbol,
                'last_price': round(price + change, 2),
                'change_percent': round(change / price * 100, 2),
                'volume': int(random.uniform(1000000, 10000000)),
                'turnover': round(random.uniform(1000000, 10000000), 2)
            })
        
        return {
            'status': 'mock',
            'data': data,
            'note': 'Mock data - Futu library not connected'
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
    connected = futu_client is not None and futu_client.quote_ctx is not None
    return jsonify({
        'status': 'ok',
        'connected': connected,
        'futu_available': FUTU_AVAILABLE,
        'timestamp': datetime.now(_TZ_TAIPEI).isoformat()
    })
