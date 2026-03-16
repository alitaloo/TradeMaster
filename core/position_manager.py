#!/usr/bin/env python3
"""
Position Manager - 持倉管理模組
持倉的完整管理邏輯
已從 SQLite 遷移至 MySQL (2026-03-06)
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# 導入 MySQL 配置
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config.database import get_db_cursor, get_db_connection


class PositionManager:
    """持倉管理器"""

    def __init__(self):
        pass

    def load_positions(self):
        """從數據庫加載持倉"""
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM positions ORDER BY updated_at DESC")
            rows = cursor.fetchall()
        return rows

    def get_position(self, symbol):
        """獲取單個持倉"""
        with get_db_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM positions WHERE symbol = %s", (symbol.upper(),))
            row = cursor.fetchone()
        return row

    def create_position(self, symbol, entry_price=None, entry_quantity=None, total_capital=None):
        """創建持倉記錄"""
        with get_db_cursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO positions (symbol, status, entry_price, entry_quantity,
                                      current_quantity, average_cost, total_capital)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''',
                (
                    symbol.upper(),
                    'WATCHING',
                    entry_price,
                    entry_quantity,
                    entry_quantity or 0,
                    entry_price,
                    total_capital
                )
            )
            return cursor.lastrowid

    def update_position(self, symbol, **kwargs):
        """更新持倉"""
        if not kwargs:
            return False

        allowed_fields = {
            'status', 'entry_price', 'entry_quantity', 'entry_total',
            'exit_price', 'exit_quantity', 'exit_total',
            'current_quantity', 'current_value', 'average_cost',
            'unrealized_pnl', 'return_pct', 'total_capital'
        }

        updates = []
        params = []
        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = %s")
                params.append(value)

        if not updates:
            return False

        updates.append("updated_at = %s")
        params.append(datetime.now().isoformat())
        params.append(symbol.upper())

        with get_db_cursor() as cursor:
            cursor.execute(
                f"UPDATE positions SET {', '.join(updates)} WHERE symbol = %s",
                params
            )
            return cursor.rowcount > 0

    def calculate_pnl(self, symbol, current_price):
        """計算持倉盈虧"""
        position = self.get_position(symbol)
        if not position:
            return None

        entry_price = position.get('entry_price') or position.get('average_cost') or 0
        quantity = position.get('current_quantity') or position.get('entry_quantity') or 0

        if entry_price <= 0 or quantity <= 0:
            return 0

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
            return_pct = pos.get('return_pct', 0) or 0
            unrealized_pnl = pos.get('unrealized_pnl', 0) or 0

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

        return alerts

    def log_position_change(self, symbol, change_type, old_data, new_data):
        """記錄持倉變更"""
        print(f"[Position Change] {symbol}: {change_type}")
        print(f"  Old: {old_data}")
        print(f"  New: {new_data}")


def get_position_manager():
    """獲取持倉管理器實例"""
    return PositionManager()


if __name__ == "__main__":
    pm = PositionManager()

    # 創建測試持倉
    pm.create_position('AAPL', entry_price=180, entry_quantity=100, total_capital=50000)

    # 計算盈虧
    pnl = pm.calculate_pnl('AAPL', 185)
    print("盈虧計算:", pnl)

    # 檢查報警
    alerts = pm.check_position_alerts()
    print("報警:", alerts)
