#!/usr/bin/env python3
"""
Backtests API - 回測結果端點
"""

import os
import glob
import csv
from datetime import datetime
from flask import Blueprint, jsonify, request

backtests_bp = Blueprint('backtests', __name__, url_prefix='/api/v1/backtests')

# 回測結果目錄
BACKTEST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'backtest_results')


def load_backtest_results():
    """加載所有回測結果"""
    results = []
    csv_files = glob.glob(os.path.join(BACKTEST_DIR, '*.csv'))
    
    for file_path in csv_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row['file'] = os.path.basename(file_path)
                    # 轉換數值類型
                    for key in ['return', 'sharpe', 'max_dd', 'total_trades']:
                        if key in row:
                            try:
                                row[key] = float(row[key])
                            except:
                                pass
                    results.append(row)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    return results


def parse_md_report(file_path):
    """解析 MD 格式的回測報告"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 簡單解析
            return {
                "file": os.path.basename(file_path),
                "content": content[:1000],  # 截取前1000字符
                "parsed": True
            }
    except Exception as e:
        return {"file": os.path.basename(file_path), "error": str(e)}


@backtests_bp.route('', methods=['GET'])
def get_backtests():
    """獲取所有回測結果"""
    results = load_backtest_results()
    
    # 可選過濾
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    
    if strategy:
        results = [r for r in results if strategy.lower() in r.get('strategy', '').lower()]
    if symbol:
        results = [r for r in results if r.get('symbol', '').upper() == symbol.upper()]
    
    return jsonify({
        "status": "ok",
        "count": len(results),
        "backtests": results
    })


@backtests_bp.route('/strategy/<strategy_name>', methods=['GET'])
def get_backtests_by_strategy(strategy_name):
    """獲取特定策略的回測結果"""
    results = load_backtest_results()
    strategy_results = [r for r in results if strategy_name.lower() in r.get('strategy', '').lower()]
    
    return jsonify({
        "status": "ok",
        "strategy": strategy_name,
        "count": len(strategy_results),
        "backtests": strategy_results
    })


@backtests_bp.route('/symbol/<symbol>', methods=['GET'])
def get_backtests_by_symbol(symbol):
    """獲取特定股票的回測結果"""
    results = load_backtest_results()
    symbol_results = [r for r in results if r.get('symbol', '').upper() == symbol.upper()]
    
    return jsonify({
        "status": "ok",
        "symbol": symbol.upper(),
        "count": len(symbol_results),
        "backtests": symbol_results
    })


@backtests_bp.route('/top', methods=['GET'])
def get_top_backtests():
    """獲取表現最好的回測結果"""
    results = load_backtest_results()
    
    # 按報酬排序
    top_by_return = sorted(results, key=lambda x: x.get('return', 0), reverse=True)[:5]
    # 按夏普排序
    top_by_sharpe = sorted(results, key=lambda x: x.get('sharpe', 0), reverse=True)[:5]
    
    return jsonify({
        "status": "ok",
        "top_by_return": top_by_return,
        "top_by_sharpe": top_by_sharpe
    })


@backtests_bp.route('/statistics', methods=['GET'])
def get_backtests_statistics():
    """獲取回測統計"""
    results = load_backtest_results()
    
    if not results:
        return jsonify({
            "status": "ok",
            "total_backtests": 0,
            "avg_return": 0,
            "avg_sharpe": 0,
            "strategies": [],
            "symbols": []
        })
    
    strategies = list(set(r.get('strategy') for r in results))
    symbols = list(set(r.get('symbol') for r in results))
    
    returns = [r.get('return', 0) for r in results]
    sharpes = [r.get('sharpe', 0) for r in results]
    
    return jsonify({
        "status": "ok",
        "total_backtests": len(results),
        "avg_return": sum(returns) / len(returns) if returns else 0,
        "avg_sharpe": sum(sharpes) / len(sharpes) if sharpes else 0,
        "strategies": sorted(strategies),
        "symbols": sorted(symbols)
    })
