#!/usr/bin/env python3
"""
Paper Order Model - 模擬訂單
"""
from datetime import datetime
from config.database import get_db_cursor


class PaperOrder:
    """模擬訂單"""
    
    TABLE_NAME = 'paper_orders'
    
    def __init__(self, id=None, symbol=None, order_type=None, quantity=None, 
                 price=None, status='pending', source_signal_id=None, 
                 futu_order_id=None, filled_quantity=0, filled_price=None,
                 filled_at=None, created_at=None, updated_at=None):
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
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
    
    def save(self):
        """儲存訂單"""
        with get_db_cursor() as cursor:
            if self.id:
                cursor.execute(f"""
                    UPDATE {self.TABLE_NAME}
                    SET symbol=%s, order_type=%s, quantity=%s, price=%s,
                        status=%s, source_signal_id=%s, futu_order_id=%s,
                        filled_quantity=%s, filled_price=%s, filled_at=%s
                    WHERE id=%s
                """, (self.symbol, self.order_type, self.quantity, self.price,
                      self.status, self.source_signal_id, self.futu_order_id,
                      self.filled_quantity, self.filled_price, self.filled_at, self.id))
            else:
                cursor.execute(f"""
                    INSERT INTO {self.TABLE_NAME}
                    (symbol, order_type, quantity, price, status, source_signal_id,
                     futu_order_id, filled_quantity, filled_price, filled_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (self.symbol, self.order_type, self.quantity, self.price,
                      self.status, self.source_signal_id, self.futu_order_id,
                      self.filled_quantity, self.filled_price, self.filled_at))
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
        """查詢所有 pending 訂單"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE status = 'pending'")
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
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
