#!/usr/bin/env python3
"""
Paper Order Model - 模擬訂單
"""
from datetime import datetime, timezone, timedelta
from config.database import get_db_cursor

_TZ_TAIPEI = timezone(timedelta(hours=8))


class PaperOrder:
    """模擬訂單"""
    
    TABLE_NAME = 'paper_orders'
    
    def __init__(self, id=None, symbol=None, order_type=None, quantity=None, 
                 price=None, status='pending', source_signal_id=None, 
                 futu_order_id=None, filled_quantity=0, filled_price=None,
                 filled_at=None, stop_loss=None, take_profit=None,
                 source_type=None, created_at=None, updated_at=None):
        self.id = id
        self.symbol = symbol
        self.order_type = order_type
        self.quantity = quantity
        self.price = price
        self.status = status
        self.source_signal_id = source_signal_id
        self.futu_order_id = futu_order_id
        self.filled_quantity = filled_quantity
        self.filled_price = filled_price
        self.filled_at = filled_at
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.source_type = source_type
        self.created_at = created_at or datetime.now(_TZ_TAIPEI)
        self.updated_at = updated_at or datetime.now(_TZ_TAIPEI)
    
    def save(self):
        """儲存訂單"""
        with get_db_cursor() as cursor:
            if self.id:
                cursor.execute(f"""
                    UPDATE {self.TABLE_NAME}
                    SET symbol=%s, order_type=%s, quantity=%s, price=%s,
                        status=%s, source_signal_id=%s, futu_order_id=%s,
                        filled_quantity=%s, filled_price=%s, filled_at=%s,
                        stop_loss=%s, take_profit=%s, source_type=%s
                    WHERE id=%s
                """, (self.symbol, self.order_type, self.quantity, self.price,
                      self.status, self.source_signal_id, self.futu_order_id,
                      self.filled_quantity, self.filled_price, self.filled_at,
                      self.stop_loss, self.take_profit, self.source_type, self.id))
            else:
                cursor.execute(f"""
                    INSERT INTO {self.TABLE_NAME}
                    (symbol, order_type, quantity, price, status, source_signal_id,
                     futu_order_id, filled_quantity, filled_price, filled_at,
                     stop_loss, take_profit, source_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (self.symbol, self.order_type, self.quantity, self.price,
                      self.status, self.source_signal_id, self.futu_order_id,
                      self.filled_quantity, self.filled_price, self.filled_at,
                      self.stop_loss, self.take_profit, self.source_type))
                self.id = cursor.lastrowid
        return self.id
    
    @classmethod
    def find_by_id(cls, order_id):
        """透過 ID 查詢"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE id = %s", (order_id,))
            row = cursor.fetchone()
            return cls(**row) if row else None
    
    @classmethod
    def find_pending(cls):
        """查詢所有待輪詢訂單（pending / partial / expired，expired 也查因為富途可能已成交但本地標錯）"""
        with get_db_cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {cls.TABLE_NAME} WHERE status IN ('pending', 'partial', 'expired') AND futu_order_id IS NOT NULL ORDER BY created_at ASC"
            )
            return [cls(**row) for row in cursor.fetchall()]
    
    @classmethod
    def find_by_symbol(cls, symbol):
        """查詢某股票的所有訂單"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE symbol = %s ORDER BY created_at DESC", (symbol,))
            return [cls(**row) for row in cursor.fetchall()]
    
    @classmethod
    def find_all(cls, limit=100):
        """查詢所有訂單"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} ORDER BY created_at DESC LIMIT %s", (limit,))
            return [cls(**row) for row in cursor.fetchall()]
    
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
        return {
            'id': self.id,
            'symbol': self.symbol,
            'order_type': self.order_type,
            'quantity': self.quantity,
            'price': float(self.price) if self.price else None,
            'status': self.status,
            'source_signal_id': self.source_signal_id,
            'futu_order_id': self.futu_order_id,
            'filled_quantity': self.filled_quantity,
            'filled_price': float(self.filled_price) if self.filled_price else None,
            'filled_at': self._iso_taipei(self.filled_at),
            'stop_loss': float(self.stop_loss) if self.stop_loss else None,
            'take_profit': float(self.take_profit) if self.take_profit else None,
            'source_type': self.source_type,
            'created_at': self._iso_taipei(self.created_at),
            'updated_at': self._iso_taipei(self.updated_at),
        }
