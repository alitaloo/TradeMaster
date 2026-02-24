#!/usr/bin/env python3
"""
 Signals API - 交易信號端點
"""

import os
import json
import glob
from datetime import datetime
from flask import Blueprint, jsonify, request

signals_bp = Blueprint('signals', __name__, url_prefix='/api/v1/signals')

# 信號文件目錄
SIGNALS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'signals')


def load_latest_signals():
    """加載最新信號"""
    # 查找最新的信號文件
    signal_files = glob.glob(os.path.join(SIGNALS_DIR, 'signals_*.json'))
    if not signal_files:
        return [], None
    
    latest_file = max(signal_files, key=os.path.getctime)
    file_mtime = os.path.getmtime(latest_file)
    data_timestamp = datetime.fromtimestamp(file_mtime).isoformat()
    
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('signals', data if isinstance(data, list) else []), data_timestamp
    except Exception as e:
        print(f"Error loading signals: {e}")
        return [], None


def load_all_signals(limit=100):
    """加載所有信號文件"""
    all_signals = []
    data_timestamp = None
    
    signal_files = sorted(
        glob.glob(os.path.join(SIGNALS_DIR, 'signals_*.json')),
        key=os.path.getctime,
        reverse=True
    )[:limit]
    
    for file_path in signal_files:
        try:
            # 使用第一個文件的時間作為 data_timestamp
            if data_timestamp is None:
                file_mtime = os.path.getmtime(file_path)
                data_timestamp = datetime.fromtimestamp(file_mtime).isoformat()
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                signals = data.get('signals', data if isinstance(data, list) else [])
                for signal in signals:
                    signal['file'] = os.path.basename(file_path)
                all_signals.extend(signals)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    return all_signals, data_timestamp


@signals_bp.route('', methods=['GET'])
def get_signals():
    """獲取所有信號"""
    limit = request.args.get('limit', type=int, default=100)
    signals, data_timestamp = load_all_signals(limit)
    return jsonify({
        "status": "ok",
        "count": len(signals),
        "data_timestamp": data_timestamp,
        "signals": signals
    })


@signals_bp.route('/latest', methods=['GET'])
def get_latest_signals():
    """獲取最新信號"""
    limit = request.args.get('limit', type=int, default=10)
    signals, data_timestamp = load_latest_signals()
    signals = signals[:limit] if signals else []
    return jsonify({
        "status": "ok",
        "count": len(signals),
        "data_timestamp": data_timestamp,
        "signals": signals
    })


@signals_bp.route('/<symbol>', methods=['GET'])
def get_signal_by_symbol(symbol):
    """獲取特定股票的信號"""
    all_signals, data_timestamp = load_all_signals(200)
    symbol_signals = [s for s in all_signals if s.get('symbol', '').upper() == symbol.upper()]
    
    return jsonify({
        "status": "ok",
        "symbol": symbol.upper(),
        "count": len(symbol_signals),
        "data_timestamp": data_timestamp,
        "signals": symbol_signals
    })


@signals_bp.route('/summary', methods=['GET'])
def get_signals_summary():
    """獲取信號摘要"""
    latest, data_timestamp = load_latest_signals()
    
    long_signals = [s for s in latest if s.get('type') == 'LONG']
    short_signals = [s for s in latest if s.get('type') == 'SHORT']
    
    return jsonify({
        "status": "ok",
        "total": len(latest),
        "data_timestamp": data_timestamp,
        "long_count": len(long_signals),
        "short_count": len(short_signals),
        "long_symbols": [s['symbol'] for s in long_signals],
        "short_symbols": [s['symbol'] for s in short_signals]
    })
