#!/usr/bin/env python3
"""
Metrics Utility
API 監控指標
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Lock

class Metrics:
    """簡單內存指標收集器"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)
        self.gauges = {}
    
    def increment(self, name, value=1):
        """計數器遞增"""
        self.counters[name] += value
    
    def gauge(self, name, value):
        """設置瞬時值"""
        self.gauges[name] = {
            'value': value,
            'timestamp': datetime.now().isoformat()
        }
    
    def timing(self, name, duration_ms):
        """記錄耗時"""
        self.timers[name].append(duration_ms)
    
    def get_stats(self):
        """獲取統計"""
        stats = {
            'counters': dict(self.counters),
            'gauges': self.gauges,
            'timers': {}
        }
        
        # 計算耗時統計
        for name, values in self.timers.items():
            if values:
                stats['timers'][name] = {
                    'count': len(values),
                    'avg': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values)
                }
        
        return stats
    
    def reset(self):
        """重置"""
        self.counters.clear()
        self.timers.clear()
        self.gauges.clear()


# 全局指標實例
metrics = Metrics()


def track_request(f):
    """請求追蹤裝飾器"""
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = f(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            
            # 記錄指標
            metrics.increment('requests.total')
            metrics.increment(f'requests.{f.__name__}.success')
            metrics.timing(f'requests.{f.__name__}.duration', duration_ms)
            
            return result
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            
            metrics.increment('requests.total')
            metrics.increment(f'requests.{f.__name__}.error')
            metrics.timing(f'requests.{f.__name__}.duration', duration_ms)
            
            raise
    
    return wrapper


# Flask 請求追蹤
def init_metrics_middleware(app):
    """初始化 Flask 中間件"""
    
    @app.before_request
    def before():
        request.start_time = time.time()
    
    @app.after_request
    def after(response):
        if hasattr(request, 'start_time'):
            duration_ms = (time.time() - request.start_time) * 1000
            
            # 記錄指標
            metrics.increment('http.requests')
            metrics.increment(f'http.{response.status_code}')
            metrics.timing('http.response_time', duration_ms)
        
        return response
    
    @app.route('/api/v1/metrics')
    def get_metrics():
        return metrics.get_stats()


if __name__ == "__main__":
    # 測試
    metrics.increment('test')
    metrics.gauge('memory', 1024)
    metrics.timing('test', 15.5)
    
    print(metrics.get_stats())
