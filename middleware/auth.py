#!/usr/bin/env python3
"""
Authentication Middleware
API Key 認證
已從 SQLite 遷移至 MySQL (2026-03-06)
"""

import hashlib
import secrets
import sys
import os
from datetime import datetime
from functools import wraps
from flask import request, jsonify

# 導入 MySQL 配置
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config.database import get_db_cursor, get_db_connection


def init_auth_db():
    """初始化認證數據庫 (MySQL)"""
    # api_keys 表由 migrations/005_api_keys_kline_cache.sql 建立
    # 此函數保留用於向後兼容，實際建表由 migrate_v2.py 處理
    pass


def hash_api_key(key):
    """Hash API Key"""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key():
    """生成新的 API Key"""
    return secrets.token_urlsafe(32)


def create_api_key(name, permissions='read'):
    """創建 API Key"""
    key = generate_api_key()
    key_hash = hash_api_key(key)
    key_id = f"sk_{secrets.token_hex(8)}"

    with get_db_cursor() as cursor:
        cursor.execute(
            '''
            INSERT INTO api_keys (key_id, key_hash, name, permissions)
            VALUES (%s, %s, %s, %s)
            ''',
            (key_id, key_hash, name, permissions)
        )

    # 返回完整 key（只顯示一次）
    return {
        'key_id': key_id,
        'key': f"{key_id}_{key}",
        'name': name,
        'permissions': permissions
    }


def verify_api_key(key):
    """驗證 API Key"""
    if not key:
        return None

    # 解析 key_id_key 格式
    parts = key.split('_')
    if len(parts) < 3:
        return None

    key_id = f"{parts[0]}_{parts[1]}"
    key_part = '_'.join(parts[2:])
    key_hash = hash_api_key(key_part)

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            '''
            SELECT * FROM api_keys
            WHERE key_id = %s AND key_hash = %s AND is_active = 1
            ''',
            (key_id, key_hash)
        )
        row = cursor.fetchone()

        if row:
            # 更新最後使用時間
            cursor.execute(
                "UPDATE api_keys SET last_used_at = %s WHERE key_id = %s",
                (datetime.now().isoformat(), key_id)
            )
            conn.commit()

    return row if row else None


def require_auth(f):
    """認證裝飾器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # 從 Header 獲取 API Key
        auth_header = request.headers.get('Authorization', '')

        if not auth_header:
            return jsonify({'error': 'Missing Authorization header'}), 401

        # 支援 Bearer token 或直接 key
        if auth_header.startswith('Bearer '):
            api_key = auth_header[7:]
        else:
            api_key = auth_header

        # 驗證
        user = verify_api_key(api_key)

        if not user:
            return jsonify({'error': 'Invalid API key'}), 401

        # 傳遞用戶信息
        request.api_user = user
        return f(*args, **kwargs)

    return decorated


def require_permission(permission):
    """權限檢查裝飾器"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'api_user'):
                return jsonify({'error': 'Authentication required'}), 401

            user_perms = request.api_user.get('permissions', '')
            if permission not in user_perms and user_perms != 'admin':
                return jsonify({'error': 'Insufficient permissions'}), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


if __name__ == "__main__":
    # 測試創建 key
    result = create_api_key("Test Key", "read,write")
    print("新 API Key:", result)
