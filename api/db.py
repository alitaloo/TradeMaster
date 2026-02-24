#!/usr/bin/env python3
"""
Database connection helper - MySQL (MariaDB)
"""

import pymysql
from contextlib import contextmanager

# MySQL config
DB_CONFIG = {
    'host': 'localhost',
    'user': 'alita',
    'password': 'alitamysql',
    'database': 'trademaster',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

@contextmanager
def get_db_connection():
    """Get MySQL database connection"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

def get_connection():
    """Get MySQL connection (non-context manager)"""
    return pymysql.connect(**DB_CONFIG)
