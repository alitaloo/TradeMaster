#!/usr/bin/env python3
"""
Risk Engine - 風控引擎
交易前的風險檢查
使用 MySQL 資料庫
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.database import get_db_cursor, get_db_connection
from config.constants import RISK_CONFIG


class RiskEngine:
    """風控引擎"""
    
    def __init__(self, config=None):
        self.config = config or RISK_CONFIG
    
    def _get_total_assets(self):
        """取得當前總資產（現金 + 持倉市值），用於動態計算風控閾值"""
        try:
            from paper_trading_portfolio import get_paper_total_assets
            assets = get_paper_total_assets()
            total = assets.get('total', 0)
            return total if total > 0 else 1000000  # fallback 到初始資金
        except Exception:
            return 1000000  # fallback
    
    def _get_limit(self, pct_key, fallback=100000):
        """根據總資產百分比動態計算風控上限"""
        pct = self.config.get(pct_key, 0)
        if pct <= 0:
            return fallback
        total_assets = self._get_total_assets()
        return total_assets * pct
    
    def check_single_amount(self, price, quantity):
        """檢查單筆金額"""
        amount = price * quantity
        limit = self._get_limit('max_single_amount_pct')
        if amount > limit:
            return {
                'passed': False,
                'rule': 'max_single_amount',
                'message': f'單筆金額 ${amount:.2f} 超過上限 ${limit:.0f}（總資產的 {self.config.get("max_single_amount_pct", 0)*100:.0f}%）'
            }
        return {'passed': True, 'rule': 'max_single_amount'}
    
    def check_total_position(self):
        """檢查總持倉"""
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT COALESCE(SUM(quantity * current_price), 0) as total_value 
                    FROM paper_positions 
                    WHERE quantity > 0
                """)
                row = cursor.fetchone()
                total_value = row['total_value'] if row else 0
        except Exception as e:
            return {'passed': False, 'rule': 'max_total_position', 'reason': f'風控查詢失敗: {e}'}
        
        limit = self._get_limit('max_total_position_pct')
        if total_value >= limit:
            return {
                'passed': False,
                'rule': 'max_total_position',
                'message': f'總持倉 ${total_value:.2f} 達到上限 ${limit:.0f}（總資產的 {self.config.get("max_total_position_pct", 0)*100:.0f}%）'
            }
        return {'passed': True, 'rule': 'max_total_position'}
    
    def check_stock_position(self, symbol, price, quantity):
        """檢查單股票持倉"""
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT COALESCE(quantity * current_price, 0) as current_value 
                    FROM paper_positions 
                    WHERE symbol = %s AND quantity > 0
                """, (symbol,))
                row = cursor.fetchone()
                current_value = row['current_value'] if row else 0
        except Exception as e:
            return {'passed': False, 'rule': 'max_position_per_stock', 'reason': f'風控查詢失敗: {e}'}
        
        new_value = price * quantity
        total_value = float(current_value) + new_value
        
        limit = self._get_limit('max_position_per_stock_pct')
        if total_value > limit:
            return {
                'passed': False,
                'rule': 'max_position_per_stock',
                'message': f'{symbol} 持倉 ${total_value:.2f} 超過上限 ${limit:.0f}（總資產的 {self.config.get("max_position_per_stock_pct", 0)*100:.0f}%）'
            }
        return {'passed': True, 'rule': 'max_position_per_stock'}
    
    def check_stop_loss(self, signal_data):
        """檢查止損設置"""
        if not signal_data.get('stop_loss'):
            return {
                'passed': True,
                'rule': 'stop_loss',
                'warning': '未設置止損',
                'message': '建議設置止損價格'
            }
        return {'passed': True, 'rule': 'stop_loss'}
    
    def check_confidence(self, confidence):
        """檢查信心度"""
        if confidence < self.config['min_confidence']:
            return {
                'passed': False,
                'rule': 'min_confidence',
                'message': f'信心度 {confidence:.2f} 低於最低要求 {self.config["min_confidence"]}'
            }
        return {'passed': True, 'rule': 'min_confidence'}
    
    def check_leverage(self, total_value, capital):
        """檢查杠桿"""
        if capital <= 0:
            return {'passed': True, 'rule': 'leverage'}
        
        leverage = total_value / capital
        
        if leverage > self.config['max_leverage']:
            return {
                'passed': False,
                'rule': 'max_leverage',
                'message': f'杠桿 {leverage:.2f}x 超過上限 {self.config["max_leverage"]}x'
            }
        return {'passed': True, 'rule': 'leverage', 'leverage': leverage}
    
    def calculate_risk_score(self, signal_data):
        """計算風險評分 (0-100)"""
        score = 0
        
        # 信心度評分 (0-30)
        confidence = signal_data.get('confidence', 0.5)
        score += confidence * 30
        
        # 有止損 (+20)
        if signal_data.get('stop_loss'):
            score += 20
        
        # 有止盈 (+10)
        if signal_data.get('take_profit'):
            score += 10
        
        # 風控評分 (0-20)
        risk_score = signal_data.get('risk_score', 50)
        score += (risk_score / 100) * 20
        
        # 新聞權重 (0-20)
        news_weight = signal_data.get('news_weight', 0)
        score += (news_weight / 100) * 20
        
        return min(100, int(score))
    
    def risk_check(self, signal_data, price, quantity):
        """整合風控檢查"""
        results = []
        
        # 1. 單筆金額檢查
        result = self.check_single_amount(price, quantity)
        results.append(result)
        
        # 2. 總持倉檢查
        result = self.check_total_position()
        results.append(result)
        
        # 3. 單股票持倉檢查
        symbol = signal_data.get('symbol')
        if symbol:
            result = self.check_stock_position(symbol, price, quantity)
            results.append(result)
        
        # 4. 止損檢查
        result = self.check_stop_loss(signal_data)
        results.append(result)
        
        # 5. 信心度檢查
        confidence = signal_data.get('confidence', 0)
        result = self.check_confidence(confidence)
        results.append(result)
        
        # 計算風險評分
        risk_score = self.calculate_risk_score(signal_data)
        
        # 判斷是否通過
        passed = all(r.get('passed', True) for r in results)
        warnings = [r.get('warning') for r in results if r.get('warning')]
        
        return {
            'passed': passed,
            'risk_score': risk_score,
            'checks': results,
            'warnings': warnings,
            'timestamp': datetime.now().isoformat()
        }
    
    def log_risk_event(self, symbol, rule_name, action_taken, metadata=None):
        """記錄風控日誌"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO risk_logs (symbol, rule_name, action_taken, metadata, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                ''', (symbol, rule_name, action_taken, str(metadata or {})))
                conn.commit()
        except Exception as e:
            # 日誌寫入失敗不應阻塞主流程
            print(f"Warning: Failed to log risk event: {e}")


def check_signal_risk(signal_data, price, quantity):
    """便捷函數：檢查信號風險"""
    engine = RiskEngine()
    return engine.risk_check(signal_data, price, quantity)


if __name__ == "__main__":
    # 測試
    engine = RiskEngine()
    
    # 測試信號
    test_signal = {
        'symbol': 'AAPL',
        'confidence': 0.8,
        'stop_loss': 170.0,
        'take_profit': 200.0,
        'risk_score': 75,
        'news_weight': 60
    }
    
    result = engine.risk_check(test_signal, price=185, quantity=50)
    print("風控檢查結果:")
    print(f"  通過: {result['passed']}")
    print(f"  風險評分: {result['risk_score']}")
    print(f"  檢查詳情: {result['checks']}")
