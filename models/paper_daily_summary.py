#!/usr/bin/env python3
"""
Paper Daily Summary Model - 每日結算
"""
from datetime import datetime, date, timezone, timedelta
from config.database import get_db_cursor

_TZ_TAIPEI = timezone(timedelta(hours=8))


class PaperDailySummary:
    """每日結算"""
    
    TABLE_NAME = 'paper_daily_summary'
    UPSERT_FIELDS = (
        'total_value', 'cash', 'market_value', 'unrealized_pnl',
        'realized_pnl', 'daily_pnl', 'trade_count', 'buy_count', 'sell_count'
    )
    
    def __init__(self, id=None, date=None, total_value=0, cash=0, 
                 market_value=0, unrealized_pnl=0, realized_pnl=0,
                 daily_pnl=0, trade_count=0, buy_count=0, sell_count=0,
                 created_at=None):
        from datetime import date as _date
        self.id = id
        self.date = date if isinstance(date, _date) else (datetime.strptime(date, '%Y-%m-%d').date() if date else date)
        self.total_value = total_value
        self.cash = cash
        self.market_value = market_value
        self.unrealized_pnl = unrealized_pnl
        self.realized_pnl = realized_pnl
        self.daily_pnl = daily_pnl
        self.trade_count = trade_count
        self.buy_count = buy_count
        self.sell_count = sell_count
        self.created_at = created_at or datetime.now(_TZ_TAIPEI)
    
    def _upsert_values(self):
        """回傳 upsert 欄位值"""
        return (
            self.total_value,
            self.cash,
            self.market_value,
            self.unrealized_pnl,
            self.realized_pnl,
            self.daily_pnl,
            self.trade_count,
            self.buy_count,
            self.sell_count,
        )

    def save(self):
        """儲存每日結算；若同日期已存在則更新既有資料"""
        with get_db_cursor() as cursor:
            if self.id:
                cursor.execute(f"""
                    UPDATE {self.TABLE_NAME}
                    SET total_value=%s, cash=%s, market_value=%s,
                        unrealized_pnl=%s, realized_pnl=%s, daily_pnl=%s,
                        trade_count=%s, buy_count=%s, sell_count=%s
                    WHERE id=%s
                """, self._upsert_values() + (self.id,))
                return self.id

            if not self.date:
                raise ValueError('PaperDailySummary.save() requires date when id is not set')

            update_clause = ', '.join(f"{field}=VALUES({field})" for field in self.UPSERT_FIELDS)
            cursor.execute(f"""
                INSERT INTO {self.TABLE_NAME}
                (date, total_value, cash, market_value, unrealized_pnl,
                 realized_pnl, daily_pnl, trade_count, buy_count, sell_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    {update_clause},
                    id=LAST_INSERT_ID(id)
            """, (self.date,) + self._upsert_values())
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
            'total_value': float(self.total_value) if self.total_value else 0,
            'cash': float(self.cash) if self.cash else 0,
            'market_value': float(self.market_value) if self.market_value else 0,
            'unrealized_pnl': float(self.unrealized_pnl) if self.unrealized_pnl else 0,
            'realized_pnl': float(self.realized_pnl) if self.realized_pnl else 0,
            'daily_pnl': float(self.daily_pnl) if self.daily_pnl else 0,
            'trade_count': self.trade_count,
            'buy_count': self.buy_count,
            'sell_count': self.sell_count,
            'created_at': self._iso_taipei(self.created_at),
        }
