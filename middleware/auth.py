#!/usr/bin/env python3
"""
Authentication Middleware
API Key 認證
"""

import sqlite3
import hashlib
import secrets
from datetime import datetime
from functools import wraps
from flask import request, jsonify

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/trademaster.db'


def init_auth_db():
    """初始化認證數據庫"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id TEXT UNIQUE NOT NULL,
            key_hash TEXT NOT NULL,
            name TEXT,
            permissions TEXT,
            rate_limit INTEGER DEFAULT 100,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used_at DATETIME
        )
    ''')
    
    conn.commit()
    conn.close()


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
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO api_keys (key_id, key_hash, name, permissions)
        VALUES (?, ?, ?, ?)
    ''', (key_id, key_hash, name, permissions))
    
    conn.commit()
    conn.close()
    
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
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM api_keys 
        WHERE key_id = ? AND key_hash = ? AND is_active = 1
    ''', (key_id, key_hash))
    
    row = cursor.fetchone()
    
    if row:
        # 更新最後使用時間
        cursor.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
            (datetime.now().isoformat(), key_id)
        )
        conn.commit()
    
    conn.close()
    
    return dict(row) if row else None


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


# 初始化
init_auth_db()


if __name__ == "__main__":
    # 測試創建 key
    result = create_api_key("Test Key", "read,write")
    print("新 API Key:", result)
