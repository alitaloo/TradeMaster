#!/usr/bin/env python3
"""
Position Manager - 持倉管理模組
持倉的完整管理邏輯
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/trademaster.db'


class PositionManager:
    """持倉管理器"""
    
    def __init__(self):
        pass
    
    def load_positions(self):
        """從數據庫加載持倉"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM positions ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_position(self, symbol):
        """獲取單個持倉"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM positions WHERE symbol = ?", (symbol.upper(),))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def create_position(self, symbol, entry_price=None, entry_quantity=None, total_capital=None):
        """創建持倉記錄"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO positions (symbol, status, entry_price, entry_quantity, 
                              current_quantity, average_cost, total_capital)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            symbol.upper(),
            'WATCHING',
            entry_price,
            entry_quantity,
            entry_quantity or 0,
            entry_price,
            total_capital
        ))
        
        position_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return position_id
    
    def update_position(self, symbol, **kwargs):
        """更新持倉"""
        if not kwargs:
            return False
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        for key, value in kwargs.items():
            if key in ['status', 'entry_price', 'entry_quantity', 'entry_total',
                      'exit_price', 'exit_quantity', 'exit_total',
                      'current_quantity', 'current_value', 'average_cost',
                      'unrealized_pnl', 'return_pct', 'total_capital']:
                updates.append(f"{key} = ?")
                params.append(value)
        
        if not updates:
            return False
        
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(symbol.upper())
        
        cursor.execute(
            f"UPDATE positions SET {', '.join(updates)} WHERE symbol = ?",
            params
        )
        
        conn.commit()
        affected = cursor.rowcount > 0
        conn.close()
        
        return affected
    
    def calculate_pnl(self, symbol, current_price):
        """計算持倉盈虧"""
        position = self.get_position(symbol)
        if not position:
            return None
        
        entry_price = position.get('entry_price') or position.get('average_cost') or 0
        quantity = position.get('current_quantity') or position.get('entry_quantity') or 0
        
        if entry_price <= 0 or quantity <= 0:
            return 0
        
        # 計算
        cost = entry_price * quantity
        current_value = current_price * quantity
        unrealized_pnl = current_value - cost
        return_pct = (unrealized_pnl / cost * 100) if cost > 0 else 0
        
        return {
            'symbol': symbol,
            'entry_price': entry_price,
            'current_price': current_price,
            'quantity': quantity,
            'cost': cost,
            'current_value': current_value,
            'unrealized_pnl': unrealized_pnl,
            'return_pct': return_pct
        }
    
    def sync_positions(self, market_prices=None):
        """同步持倉（更新當前價格和盈虧）"""
        positions = self.load_positions()
        results = []
        
        for pos in positions:
            symbol = pos['symbol']
            current_price = market_prices.get(symbol) if market_prices else pos.get('entry_price')
            
            if current_price:
                pnl = self.calculate_pnl(symbol, current_price)
                if pnl:
                    self.update_position(
                        symbol,
                        current_value=pnl['current_value'],
                        unrealized_pnl=pnl['unrealized_pnl'],
                        return_pct=pnl['return_pct']
                    )
                    results.append(pnl)
        
        return results
    
    def check_position_alerts(self):
        """檢查持倉報警"""
        positions = self.load_positions()
        alerts = []
        
        for pos in positions:
            symbol = pos['symbol']
            return_pct = pos.get('return_pct', 0)
            unrealized_pnl = pos.get('unrealized_pnl', 0)
            
            # 止損報警 (-5%)
            if return_pct <= -5:
                alerts.append({
                    'type': 'stop_loss',
                    'symbol': symbol,
                    'message': f'{symbol} 虧損達 {-return_pct:.1f}%，觸發止損'
                })
            
            # 止盈報警 (+10%)
            if return_pct >= 10:
                alerts.append({
                    'type': 'take_profit',
                    'symbol': symbol,
                    'message': f'{symbol} 獲利達 {return_pct:.1f}%，考慮止盈'
                })
            
            # 大幅波動報警 (日波動 > 5%)
            # 需要結合 K 線數據，這裡暫略
        
        return alerts
    
    def log_position_change(self, symbol, change_type, old_data, new_data):
        """記錄持倉變更"""
        # 可以擴展為持倉歷史表
        print(f"[Position Change] {symbol}: {change_type}")
        print(f"  Old: {old_data}")
        print(f"  New: {new_data}")


def get_position_manager():
    """獲取持倉管理器實例"""
    return PositionManager()


if __name__ == "__main__":
    # 測試
    pm = PositionManager()
    
    # 創建測試持倉
    pm.create_position('AAPL', entry_price=180, entry_quantity=100, total_capital=50000)
    
    # 計算盈虧
    pnl = pm.calculate_pnl('AAPL', 185)
    print("盈虧計算:", pnl)
    
    # 檢查報警
    alerts = pm.check_position_alerts()
    print("報警:", alerts)
