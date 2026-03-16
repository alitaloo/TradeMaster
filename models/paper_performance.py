#!/usr/bin/env python3
"""
Paper Performance Model - 回測對比
"""
from datetime import datetime, date, timezone, timedelta
from config.database import get_db_cursor

_TZ_TAIPEI = timezone(timedelta(hours=8))


class PaperPerformance:
    """回測對比"""
    
    TABLE_NAME = 'paper_performance'
    
    def __init__(self, id=None, date=None, backtest_return=0, 
                 simulation_return=0, diff=0, note=None, created_at=None):
        from datetime import date as _date
        self.id = id
        self.date = date if isinstance(date, _date) else (datetime.strptime(date, '%Y-%m-%d').date() if date else date)
        self.backtest_return = backtest_return
        self.simulation_return = simulation_return
        self.diff = diff
        self.note = note
        self.created_at = created_at or datetime.now(_TZ_TAIPEI)
    
    def save(self):
        """儲存記錄"""
        with get_db_cursor() as cursor:
            if self.id:
                cursor.execute(f"""
                    UPDATE {self.TABLE_NAME}
                    SET backtest_return=%s, simulation_return=%s, diff=%s, note=%s
                    WHERE id=%s
                """, (self.backtest_return, self.simulation_return, 
                      self.diff, self.note, self.id))
            else:
                cursor.execute(f"""
                    INSERT INTO {self.TABLE_NAME}
                    (date, backtest_return, simulation_return, diff, note)
                    VALUES (%s, %s, %s, %s, %s)
                """, (self.date, self.backtest_return, self.simulation_return,
                      self.diff, self.note))
                self.id = cursor.lastrowid
        return self.id
    
    @classmethod
    def find_by_date(cls, target_date):
        """透過日期查詢"""
        if isinstance(target_date, datetime):
            target_date = target_date.date()
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} WHERE date = %s", (target_date,))
            row = cursor.fetchone()
            return cls(**row) if row else None
    
    @classmethod
    def find_latest(cls, limit=30):
        """查詢最新記錄"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME} ORDER BY date DESC LIMIT %s", (limit,))
            return [cls(**row) for row in cursor.fetchall()]
    
    @classmethod
    def calculate_diff(cls, backtest_return, simulation_return):
        """計算差異"""
        return simulation_return - backtest_return
    
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
            'date': self.date.isoformat() if self.date else None,
            'backtest_return': float(self.backtest_return) if self.backtest_return else 0,
            'simulation_return': float(self.simulation_return) if self.simulation_return else 0,
            'diff': float(self.diff) if self.diff else 0,
            'note': self.note,
            'created_at': self._iso_taipei(self.created_at),
        }
