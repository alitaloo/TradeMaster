#!/usr/bin/env python3
"""
News API Blueprint
新聞管理接口
已從 SQLite 遷移至 MySQL (2026-03-06)
"""

import sys
import os
from flask import Blueprint, jsonify, request
from datetime import datetime, timezone, timedelta

# 導入 MySQL 配置
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config.database import get_db_cursor, get_db_connection

news_bp = Blueprint('news', __name__, url_prefix='/api/v1/news')


@news_bp.route('', methods=['GET'])
def get_news():
    """獲取新聞列表"""
    symbol = request.args.get('symbol')
    limit = int(request.args.get('limit', 50))
    sentiment = request.args.get('sentiment')

    conditions = ["1=1"]
    params = []

    if symbol:
        conditions.append("symbol = %s")
        params.append(symbol.upper())

    if sentiment:
        conditions.append("sentiment = %s")
        params.append(sentiment)

    query = f"SELECT * FROM news WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        news = cursor.fetchall()

    # 確保 datetime 字段可序列化，並標記為 +08:00
    _tz_taipei = timezone(timedelta(hours=8))
    for item in news:
        for k, v in item.items():
            if isinstance(v, datetime):
                if v.tzinfo is None:
                    v = v.replace(tzinfo=_tz_taipei)
                item[k] = v.isoformat()

    return jsonify({
        "status": "ok",
        "count": len(news),
        "news": news
    })


@news_bp.route('/<int:news_id>', methods=['GET'])
def get_news_by_id(news_id):
    """獲取單條新聞"""
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM news WHERE id = %s", (news_id,))
        row = cursor.fetchone()

    if not row:
        return jsonify({"status": "error", "message": "News not found"}), 404

    _tz_taipei = timezone(timedelta(hours=8))
    for k, v in row.items():
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=_tz_taipei)
            row[k] = v.isoformat()

    return jsonify({
        "status": "ok",
        "news": row
    })


@news_bp.route('', methods=['POST'])
def create_news():
    """創建新聞"""
    data = request.json

    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    with get_db_cursor() as cursor:
        cursor.execute(
            '''
            INSERT INTO news (symbol, title, content, weight, sentiment, source, url, news_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                weight = VALUES(weight),
                sentiment = VALUES(sentiment)
            ''',
            (
                data.get('symbol', '').upper(),
                data.get('title', ''),
                data.get('content', ''),
                data.get('weight', 0),
                data.get('sentiment', 'neutral'),
                data.get('source', ''),
                data.get('url', ''),
                data.get('news_type', 'general')
            )
        )
        news_id = cursor.lastrowid

    return jsonify({
        "status": "ok",
        "message": "News created",
        "news_id": news_id
    }), 201


@news_bp.route('/<int:news_id>', methods=['PUT'])
def update_news(news_id):
    """更新新聞"""
    data = request.json

    updates = []
    params = []

    for field in ['symbol', 'title', 'content', 'weight', 'sentiment', 'source', 'url', 'news_type']:
        if field in data:
            updates.append(f"{field} = %s")
            params.append(data[field])

    if not updates:
        return jsonify({"status": "error", "message": "No fields to update"}), 400

    updates.append("created_at = %s")
    params.append(datetime.now(timezone(timedelta(hours=8))).isoformat())
    params.append(news_id)

    with get_db_cursor() as cursor:
        cursor.execute(
            f"UPDATE news SET {', '.join(updates)} WHERE id = %s",
            params
        )
        affected = cursor.rowcount

    if affected == 0:
        return jsonify({"status": "error", "message": "News not found"}), 404

    return jsonify({
        "status": "ok",
        "message": "News updated"
    })


@news_bp.route('/<int:news_id>', methods=['DELETE'])
def delete_news(news_id):
    """刪除新聞"""
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM news WHERE id = %s", (news_id,))
        affected = cursor.rowcount

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

    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    title = data.get('title', '')
    content = data.get('content', '')
    news_type = data.get('news_type', 'general')

    weight = 0
    sentiment = 'neutral'

    # 財報相關 +2
    if any(kw in title.lower() or kw in content.lower()
           for kw in ['earnings', 'revenue', 'profit', '財報', '營收', '獲利']):
        weight += 2

    # 政策相關 +3
    if any(kw in title.lower() or kw in content.lower()
           for kw in ['policy', 'fed', 'rate', '利率', '政策', '制裁']):
        weight += 3

    # 高管變動 +2
    if any(kw in title.lower() or kw in content.lower()
           for kw in ['ceo', 'cfo', 'executive', '執行長', '高管']):
        weight += 2

    # 產品發布 +1
    if any(kw in title.lower() or kw in content.lower()
           for kw in ['launch', 'product', '發布', '產品']):
        weight += 1

    # 訴訟 +3
    if any(kw in title.lower() or kw in content.lower()
           for kw in ['lawsuit', 'sue', '訴訟']):
        weight += 3

    # 收購 +2
    if any(kw in title.lower() or kw in content.lower()
           for kw in ['acquisition', 'merge', '收購', '併購']):
        weight += 2

    # 情感判斷
    positive_kw = ['gain', 'rise', 'surge', 'growth', '漲', '增加', '成長', '利好']
    negative_kw = ['fall', 'drop', 'loss', '跌', '減少', '虧損', '利空']

    if any(kw in title.lower() or kw in content.lower() for kw in positive_kw):
        sentiment = 'positive'
    elif any(kw in title.lower() or kw in content.lower() for kw in negative_kw):
        sentiment = 'negative'

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

    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            '''
            SELECT
                SUM(weight) AS total_weight,
                COUNT(*) AS news_count,
                sentiment
            FROM news
            WHERE symbol = %s
              AND created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
            GROUP BY sentiment
            ''',
            (symbol.upper(), hours)
        )
        rows = cursor.fetchall()

    total_weight = 0
    positive_count = 0
    negative_count = 0
    neutral_count = 0

    for row in rows:
        w = int(row['total_weight'] or 0)
        total_weight += w
        if row['sentiment'] == 'positive':
            positive_count = row['news_count'] or 0
        elif row['sentiment'] == 'negative':
            negative_count = row['news_count'] or 0
        else:
            neutral_count = row['news_count'] or 0

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
