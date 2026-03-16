#!/usr/bin/env python3
"""
System Config Model - 系統配置
"""
from datetime import datetime
from config.database import get_db_cursor


class SystemConfig:
    """系統配置"""
    
    TABLE_NAME = 'system_config'
    
    @classmethod
    def get(cls, key, default=None):
        """取得配置"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT config_value FROM {cls.TABLE_NAME} WHERE config_key = %s", (key,))
            row = cursor.fetchone()
            return row['config_value'] if row else default
    
    @classmethod
    def set(cls, key, value, description=None):
        """設定配置"""
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO {cls.TABLE_NAME} (config_key, config_value, description)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE config_value = %s, description = COALESCE(%s, description)
            """, (key, value, description, value, description))
    
    @classmethod
    def is_paper_trading(cls):
        """是否啟用模擬交易"""
        return cls.get('paper_trading_enabled', 'false') == 'true'
    
    @classmethod
    def get_trading_mode(cls):
        """取得交易模式 (0=真實, 1=模擬)"""
        return int(cls.get('paper_trading_mode', '1'))
    
    @classmethod
    def get_initial_balance(cls):
        """取得初始資金"""
        return float(cls.get('paper_initial_balance', '1000000'))
    
    @classmethod
    def get_bool(cls, key, default=False):
        value = cls.get(key, 'true' if default else 'false')
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

    @classmethod
    def get_int(cls, key, default=0):
        value = cls.get(key, default)
        return int(value) if value not in (None, '') else int(default)

    @classmethod
    def get_float(cls, key, default=0.0):
        value = cls.get(key, default)
        return float(value) if value not in (None, '') else float(default)

    @classmethod
    def get_all(cls):
        """取得所有配置"""
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {cls.TABLE_NAME}")
            return {row['config_key']: row['config_value'] for row in cursor.fetchall()}
