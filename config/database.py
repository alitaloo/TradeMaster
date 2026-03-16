#!/usr/bin/env python3
"""
Database Configuration - 統一資料庫配置
所有模組應從這裡導入資料庫配置
"""

import os
import mysql.connector
from mysql.connector import pooling
from contextlib import contextmanager

# MySQL 配置 (可通過環境變數覆蓋)
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'alita'),
    'password': os.getenv('MYSQL_PASSWORD', 'alitamysql'),
    'database': os.getenv('MYSQL_DATABASE', 'trademaster'),
    'charset': 'utf8mb4'
}

# 創建連接池（pool_size=10）
_connection_pool = None

def get_connection_pool():
    """獲取資料庫連接池（懶惰初始化）"""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = pooling.MySQLConnectionPool(
            pool_name="trademaster_pool",
            pool_size=10,
            pool_reset_session=True,
            **MYSQL_CONFIG
        )
    return _connection_pool

# PyMySQL 格式 (某些模組使用)
PYMYSQL_CONFIG = {
    'host': MYSQL_CONFIG['host'],
    'user': MYSQL_CONFIG['user'],
    'password': MYSQL_CONFIG['password'],
    'database': MYSQL_CONFIG['database'],
    'charset': MYSQL_CONFIG['charset']
}


def get_connection():
    """獲取 MySQL 連接（從連接池）"""
    return get_connection_pool().get_connection()


@contextmanager
def get_db_cursor(dictionary=True):
    """上下文管理器：自動處理連接和游標
    
    Usage:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM stocks")
            rows = cursor.fetchall()
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=dictionary)
        yield cursor
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


@contextmanager
def get_db_connection():
    """上下文管理器：自動處理連接（從連接池）
    
    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # ... do stuff
            conn.commit()
    """
    conn = None
    try:
        conn = get_connection()
        yield conn
    finally:
        if conn:
            conn.close()


# 向後兼容別名
DB_CONFIG = MYSQL_CONFIG
