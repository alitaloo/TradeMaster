#!/usr/bin/env python3
"""
Paper Position Model - 模擬持倉
"""
from datetime import datetime, timezone, timedelta
from config.database import get_db_cursor

_TZ_TAIPEI = timezone(timedelta(hours=8))


class PaperPosition:
    """模擬持倉"""
    
    TABLE_NAME = 'paper_positions'
    
    def __init__(self, id=None, symbol=None, quantity=0, average_cost=0,
                 current_price=0, market_value=0, unrealized_pnl=0,
                 unrealized_pnl_pct=0, realized_pnl=0, updated_at=None):
        self.id = id
        self.symbol = symbol
        self.quantity = quantity
        self.average_cost = average_cost
        self.current_price = current_price
        self.market_value = market_value
        self.unrealized_pnl = unrealized_pnl
        self.unrealized_pnl_pct = unrealized_pnl_pct
        self.realized_pnl = realized_pnl
        self.updated_at = updated_at or datetime.now(_TZ_TAIPEI)
    
    def save(self):
        """儲存持倉"""
        with get_db_cursor() as cursor:
            if self.id:
                cursor.execute(f"""
                    UPDATE {self.TABLE_NAME}
                    SET quantity=%s, average_cost=%s, current_price=%s,
                        market_value=%s, unrealized_pnl=%s,
                        unrealized_pnl_pct=%s, realized_pnl=%s
                    WHERE id=%s
                """, (self.quantity, self.average_cost, self.current_price,
                      self.market_value, self.unrealized_pnl,
                      self.unrealized_pnl_pct, self.realized_pnl, self.id))
            else:
                cursor.execute(f"""
                    INSERT INTO {self.TABLE_NAME}
                    (symbol, quantity, average_cost, current_price,
                     market_value, unrealized_pnl, unrealized_pnl_pct, realized_pnl)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (self.symbol, self.quantity, self.average_cost, self.current_price,
                      self.market_value, self.unrealized_pnl, 
                      self.unrealized_pnl_pct, self.realized_pnl))
                self.id = cursor.lastrowid
        return self.id
    
    @classmethod
    def find_by_symbol(cls, symbol):
        """透過股票代碼查詢持倉"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE symbol = %s", (symbol,))
            row = cursor.fetchone()
            return cls(**row) if row else None
    
    @classmethod
    def find_all(cls):
        """查詢所有持倉（含多頭和空頭）"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE quantity != 0")
            return [cls(**row) for row in cursor.fetchall()]
    
    @classmethod
    def delete_by_symbol(cls, symbol):
        """刪除持倉"""
        with get_db_cursor() as cursor:
            cursor.execute(f"DELETE FROM {cls.TABLE_NAME} WHERE symbol = %s", (symbol,))
    
    def calculate_pnl(self, current_price):
        """計算未實現損益（支援多頭和空頭）"""
        current_price = float(current_price)
        self.current_price = current_price
        if self.quantity != 0 and self.average_cost > 0:
            self.market_value = self.quantity * current_price  # 空頭時為負值
            if self.quantity > 0:
                # 多頭：漲了賺、跌了虧
                self.unrealized_pnl = (current_price - float(self.average_cost)) * self.quantity
            else:
                # 空頭：跌了賺、漲了虧（賣空價 - 現價）
                self.unrealized_pnl = (float(self.average_cost) - current_price) * abs(self.quantity)
            self.unrealized_pnl_pct = (current_price / float(self.average_cost) - 1) * 100
        else:
            self.market_value = 0
            self.unrealized_pnl = 0
            self.unrealized_pnl_pct = 0
        return self.unrealized_pnl
    
    @staticmethod
    def _iso_taipei(dt):
        """Convert datetime to ISO 8601 with +08:00"""
        if dt is None:
            return None
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_TZ_TAIPEI)
            return dt.isoformat()
        return str(dt)

    def to_dict(self):
        """轉換為字典"""
        average_cost = float(self.average_cost) if self.average_cost else 0
        quantity = float(self.quantity) if self.quantity else 0
        position_cost = average_cost * quantity
        unrealized_pnl = float(self.unrealized_pnl) if self.unrealized_pnl else 0
        unrealized_pnl_pct_position_cost = float(self.unrealized_pnl_pct) if self.unrealized_pnl_pct else 0

        return {
            'id': self.id,
            'symbol': self.symbol,
            'quantity': self.quantity,
            'average_cost': average_cost,
            'current_price': float(self.current_price) if self.current_price else 0,
            'market_value': float(self.market_value) if self.market_value else 0,
            'position_cost': position_cost,
            'unrealized_pnl': unrealized_pnl,
            'unrealized_pnl_pct_position_cost': unrealized_pnl_pct_position_cost,
            # Deprecated alias: historically position-level unrealized_pnl_pct means pnl / position_cost.
            'unrealized_pnl_pct': unrealized_pnl_pct_position_cost,
            'realized_pnl': float(self.realized_pnl) if self.realized_pnl else 0,
            'updated_at': self._iso_taipei(self.updated_at),
        }
