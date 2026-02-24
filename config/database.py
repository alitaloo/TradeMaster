#!/usr/bin/env python3
"""
Database Configuration - 統一資料庫配置
所有模組應從這裡導入資料庫配置
"""

import os
import mysql.connector
from contextlib import contextmanager

# MySQL 配置 (可通過環境變數覆蓋)
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'alita'),
    'password': os.getenv('MYSQL_PASSWORD', 'alitamysql'),
    'database': os.getenv('MYSQL_DATABASE', 'trademaster'),
    'charset': 'utf8mb4'
}

# PyMySQL 格式 (某些模組使用)
PYMYSQL_CONFIG = {
    'host': MYSQL_CONFIG['host'],
    'user': MYSQL_CONFIG['user'],
    'password': MYSQL_CONFIG['password'],
    'database': MYSQL_CONFIG['database'],
    'charset': MYSQL_CONFIG['charset']
}


def get_connection():
    """獲取 MySQL 連接"""
    return mysql.connector.connect(**MYSQL_CONFIG)


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
        conn = mysql.connector.connect(**MYSQL_CONFIG)
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
    """上下文管理器：自動處理連接
    
    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # ... do stuff
            conn.commit()
    """
    conn = None
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        yield conn
    finally:
        if conn:
            conn.close()


# 向後兼容別名
DB_CONFIG = MYSQL_CONFIG
