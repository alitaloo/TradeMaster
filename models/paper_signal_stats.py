#!/usr/bin/env python3
"""
Paper Signal Stats Model - 信號命中率統計
"""
from datetime import datetime, date
from config.database import get_db_cursor


class PaperSignalStats:
    """信號命中率統計"""
    
    TABLE_NAME = 'paper_signal_stats'
    
    def __init__(self, id=None, date=None, symbol=None, signal_type=None,
                 signal_count=0, filled_count=0, hit_rate=0, created_at=None):
        from datetime import date as _date
        self.id = id
        self.date = date if isinstance(date, _date) else (datetime.strptime(date, '%Y-%m-%d').date() if date else date)
        self.symbol = symbol
        self.signal_type = signal_type
        self.signal_count = signal_count
        self.filled_count = filled_count
        self.hit_rate = hit_rate
        self.created_at = created_at or datetime.now()
    
    def save(self):
        """儲存統計"""
        with get_db_cursor() as cursor:
            if self.id:
                cursor.execute(f"""
                    UPDATE {self.TABLE_NAME}
                    SET signal_count=%s, filled_count=%s, hit_rate=%s
                    WHERE id=%s
                """, (self.signal_count, self.filled_count, self.hit_rate, self.id))
            else:
                cursor.execute(f"""
                    INSERT INTO {self.TABLE_NAME}
                    (date, symbol, signal_type, signal_count, filled_count, hit_rate)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (self.date, self.symbol, self.signal_type, 
                      self.signal_count, self.filled_count, self.hit_rate))
                self.id = cursor.lastrowid
        return self.id
    
    @classmethod
    def find_by_date_symbol(cls, target_date, symbol):
        """透過日期與股票查詢"""
        if isinstance(target_date, datetime):
            target_date = target_date.date()
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE date = %s AND symbol = %s", 
                          (target_date, symbol))
            row = cursor.fetchone()
            return cls(**row) if row else None
    
    @classmethod
    def find_by_date(cls, target_date):
        """透過日期查詢"""
        if isinstance(target_date, datetime):
            target_date = target_date.date()
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE date = %s", (target_date,))
            return [cls(**row) for row in cursor.fetchall()]
    
    @classmethod
    def find_by_symbol(cls, symbol, limit=30):
        """透過股票查詢"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE symbol = %s ORDER BY date DESC LIMIT %s",
                          (symbol, limit))
            return [cls(**row) for row in cursor.fetchall()]
    
    @classmethod
    def calculate_hit_rate(cls, signal_count, filled_count):
        """計算命中率"""
        if signal_count == 0:
            return 0
        return (filled_count / signal_count) * 100
    
    def to_dict(self):
        """轉換為字典"""
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'symbol': self.symbol,
            'signal_type': self.signal_type,
            'signal_count': self.signal_count,
            'filled_count': self.filled_count,
            'hit_rate': float(self.hit_rate) if self.hit_rate else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
