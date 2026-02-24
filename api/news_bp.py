#!/usr/bin/env python3
"""
News API Blueprint
新聞管理接口
"""

from flask import Blueprint, jsonify, request
import sqlite3
from datetime import datetime

news_bp = Blueprint('news', __name__, url_prefix='/api/v1/news')

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/trademaster.db'


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_news_db():
    """初始化 news 表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol VARCHAR,
            title VARCHAR,
            content TEXT,
            weight INTEGER DEFAULT 0,
            sentiment VARCHAR DEFAULT 'neutral',
            source VARCHAR,
            url VARCHAR,
            news_type VARCHAR DEFAULT 'general',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()


# 初始化
# init_news_db()


@news_bp.route('', methods=['GET'])
def get_news():
    """獲取新聞列表"""
    symbol = request.args.get('symbol')
    limit = int(request.args.get('limit', 50))
    sentiment = request.args.get('sentiment')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM news WHERE 1=1"
    params = []
    
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.upper())
    
    if sentiment:
        query += " AND sentiment = ?"
        params.append(sentiment)
    
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    news = [row._asdict() for row in rows]
    
    return jsonify({
        "status": "ok",
        "count": len(news),
        "news": news
    })


@news_bp.route('/<int:news_id>', methods=['GET'])
def get_news_by_id(news_id):
    """獲取單條新聞"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM news WHERE id = ?", (news_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({"status": "error", "message": "News not found"}), 404
    
    return jsonify({
        "status": "ok",
        "news": row._asdict()
    })


@news_bp.route('', methods=['POST'])
def create_news():
    """創建新聞"""
    data = request.json
    
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO news (symbol, title, content, weight, sentiment, source, url, news_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('symbol', '').upper(),
        data.get('title', ''),
        data.get('content', ''),
        data.get('weight', 0),
        data.get('sentiment', 'neutral'),
        data.get('source', ''),
        data.get('url', ''),
        data.get('news_type', 'general')
    ))
    
    news_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "message": "News created",
        "news_id": news_id
    }), 201


@news_bp.route('/<int:news_id>', methods=['PUT'])
def update_news(news_id):
    """更新新聞"""
    data = request.json
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    for field in ['symbol', 'title', 'content', 'weight', 'sentiment', 'source', 'url', 'news_type']:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    
    if not updates:
        return jsonify({"status": "error", "message": "No fields to update"}), 400
    
    updates.append("created_at = ?")
    params.append(datetime.now().isoformat())
    params.append(news_id)
    
    cursor.execute(
        f"UPDATE news SET {', '.join(updates)} WHERE id = ?",
        params
    )
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if affected == 0:
        return jsonify({"status": "error", "message": "News not found"}), 404
    
    return jsonify({
        "status": "ok",
        "message": "News updated"
    })


@news_bp.route('/<int:news_id>', methods=['DELETE'])
def delete_news(news_id):
    """刪除新聞"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM news WHERE id = ?", (news_id,))
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if affected == 0:
        return jsonify({"status": "error", "message": "News not found"}), 404
    
    return jsonify({
        "status": "ok",
        "message": "News deleted"
    })


@news_bp.route('/analyze', methods=['POST'])
def analyze_news():
    """分析新聞權重"""
    data = request.json
    
    title = data.get('title', '')
    content = data.get('content', '')
    news_type = data.get('news_type', 'general')
    
    # 簡單的權重計算邏輯
    weight = 0
    sentiment = 'neutral'
    
    # 財報相關 +2
    if any(kw in title.lower() or kw in content.lower() for kw in ['earnings', 'revenue', 'profit', '財報', '營收', '獲利']):
        weight += 2
    
    # 政策相關 +3
    if any(kw in title.lower() or kw in content.lower() for kw in ['policy', 'fed', 'rate', '利率', '政策', '制裁']):
        weight += 3
    
    # 高管變動 +2
    if any(kw in title.lower() or kw in content.lower() for kw in ['ceo', 'cfo', 'executive', '執行長', '高管']):
        weight += 2
    
    # 產品發布 +1
    if any(kw in title.lower() or kw in content.lower() for kw in ['launch', 'product', '發布', '產品']):
        weight += 1
    
    # 訴訟 +3
    if any(kw in title.lower() or kw in content.lower() for kw in ['lawsuit', 'sue', ' lawsuit', '訴訟']):
        weight += 3
    
    # 收購 +2
    if any(kw in title.lower() or kw in content.lower() for kw in ['acquisition', 'merge', '收購', '併購']):
        weight += 2
    
    # 情感判斷
    positive_kw = ['gain', 'rise', 'surge', 'growth', '漲', '增加', '成長', '利好']
    negative_kw = ['fall', 'drop', 'loss', '跌', '減少', '虧損', '利空']
    
    if any(kw in title.lower() or kw in content.lower() for kw in positive_kw):
        sentiment = 'positive'
    elif any(kw in title.lower() or kw in content.lower() for kw in negative_kw):
        sentiment = 'negative'
    
    # 限制權重範圍
    weight = min(10, max(0, weight))
    
    return jsonify({
        "status": "ok",
        "analysis": {
            "weight": weight,
            "sentiment": sentiment,
            "news_type": news_type
        }
    })


@news_bp.route('/weight/<symbol>', methods=['GET'])
def get_news_weight(symbol):
    """獲取股票新聞權重"""
    hours = int(request.args.get('hours', 24))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 獲取一段時間內的新聞權重總和
    cursor.execute(f'''
        SELECT 
            SUM(weight) as total_weight,
            COUNT(*) as news_count,
            sentiment
        FROM news 
        WHERE symbol = ? 
        AND created_at >= datetime('now', '-{hours} hours')
        GROUP BY sentiment
    ''', (symbol.upper(),))
    
    rows = cursor.fetchall()
    
    # 計算總權重
    total_weight = 0
    positive_count = 0
    negative_count = 0
    neutral_count = 0
    
    for row in rows:
        w = row['total_weight'] or 0
        total_weight += w
        if row['sentiment'] == 'positive':
            positive_count = row['news_count'] or 0
        elif row['sentiment'] == 'negative':
            negative_count = row['news_count'] or 0
        else:
            neutral_count = row['news_count'] or 0
    
    conn.close()
    
    return jsonify({
        "status": "ok",
        "symbol": symbol.upper(),
        "total_weight": total_weight,
        "news_count": positive_count + negative_count + neutral_count,
        "breakdown": {
            "positive": positive_count,
            "negative": negative_count,
            "neutral": neutral_count
        },
        "hours": hours
    })
