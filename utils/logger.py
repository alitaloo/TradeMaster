#!/usr/bin/env python3
"""
Logger Utility
結構化日誌
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

# 日誌配置
LOG_DIR = Path('/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/logs')
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class StructuredLogger:
    """結構化日誌器"""
    
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 控制台 handler
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        
        # 文件 handler
        log_file = LOG_DIR / f"{name}.log"
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        
        if not self.logger.handlers:
            self.logger.addHandler(console)
            self.logger.addHandler(file_handler)
    
    def info(self, message, **kwargs):
        self.logger.info(self._format(message, **kwargs))
    
    def warning(self, message, **kwargs):
        self.logger.warning(self._format(message, **kwargs))
    
    def error(self, message, **kwargs):
        self.logger.error(self._format(message, **kwargs))
    
    def debug(self, message, **kwargs):
        self.logger.debug(self._format(message, **kwargs))
    
    def _format(self, message, **kwargs):
        if kwargs:
            return f"{message} | {json.dumps(kwargs)}"
        return message


class APILogger:
    """API 請求日誌"""
    
    def __init__(self):
        self.logger = StructuredLogger('api')
    
    def log_request(self, method, path, status, duration_ms, user=None):
        self.logger.info(
            f"{method} {path}",
            status=status,
            duration_ms=duration_ms,
            user=user,
            timestamp=datetime.now().isoformat()
        )
    
    def log_error(self, method, path, error):
        self.logger.error(
            f"{method} {path}",
            error=str(error),
            timestamp=datetime.now().isoformat()
        )


class TradeLogger:
    """交易日誌"""
    
    def __init__(self):
        self.logger = StructuredLogger('trade')
    
    def log_signal(self, symbol, signal_type, price, quantity):
        self.logger.info(
            f"Signal: {signal_type} {symbol}",
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            quantity=quantity,
            timestamp=datetime.now().isoformat()
        )
    
    def log_order(self, order_id, symbol, direction, status):
        self.logger.info(
            f"Order: {direction} {symbol}",
            order_id=order_id,
            symbol=symbol,
            direction=direction,
            status=status,
            timestamp=datetime.now().isoformat()
        )
    
    def log_risk_block(self, symbol, reason):
        self.logger.warning(
            f"Risk Block: {symbol}",
            symbol=symbol,
            reason=reason,
            timestamp=datetime.now().isoformat()
        )


# 全局日誌實例
api_logger = APILogger()
trade_logger = TradeLogger()


def get_logger(name):
    """獲取日誌器"""
    return StructuredLogger(name)


if __name__ == "__main__":
    # 測試
    logger = get_logger('test')
    logger.info("Test message", foo="bar")
    
    api_logger.log_request('GET', '/api/v1/positions', 200, 15)
    
    trade_logger.log_signal('AAPL', 'BUY', 185.0, 100)
