#!/usr/bin/env python3
"""
Fox Analysis v2 × 新聞風控 實測腳本
測試目的：驗證 check_news_risk 在多檔標的上是否正確攔截信號
"""

import sys
import os
import json
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import requests

API_BASE = 'http://localhost:8080/api/v1'

# 風控參數 (與 fox_analysis_v2.py 一致)
RISK_PARAMS = {
    'NEWS_WEIGHT_THRESHOLD': 5,
    'MIN_CONFIDENCE': 0.6,
    'HIGH_CONFIDENCE': 0.8,
}

# ==================== 測試標的 ====================
# TSLA: 真實持倉 + paper持倉
# NFLX: paper持倉 (盈利+27%)
# COIN: paper持倉 (盈利+15%)
# NVDA: 只有WATCHLIST (無持倉)
TEST_STOCKS = [
    {
        'symbol': 'US.TSLA',
        'symbol_clean': 'TSLA',
        'category': '真實持倉',
        'quantity': 198,
        'avg_price': 439.52,
        'current_price': 439.52,
        'return_pct': 0.0,
    },
    {
        'symbol': 'US.NFLX',
        'symbol_clean': 'NFLX',
        'category': 'Paper持倉',
        'quantity': 2580,
        'avg_price': 77.63,
        'current_price': 98.63,
        'return_pct': 27.05,
    },
    {
        'symbol': 'US.COIN',
        'symbol_clean': 'COIN',
        'category': 'Paper持倉',
        'quantity': 578,
        'avg_price': 171.48,
        'current_price': 198.41,
        'return_pct': 15.70,
    },
    {
        'symbol': 'US.NVDA',
        'symbol_clean': 'NVDA',
        'category': 'Watchlist-Only',
        'quantity': 0,
        'avg_price': 0,
        'current_price': 130.0,  # 估算
        'return_pct': 0.0,
    },
]


def check_news_risk(news_weight: int):
    """Fox Analysis v2 的 check_news_risk 函數"""
    threshold = RISK_PARAMS['NEWS_WEIGHT_THRESHOLD']
    if news_weight > threshold:
        return False, f"新聞權重={news_weight} > {threshold} (新聞異常)"
    return True, "新聞風險檢查通過"


def calculate_confidence_base(stock: dict, news_data: dict, market_data: dict = None) -> dict:
    """計算信心度 - 逐步展示新聞因子的影響"""
    confidence = 0.5  # 基礎
    breakdown = {'base': 0.5}

    # 1. 持倉回報率因素
    return_pct = stock.get('return_pct', 0)
    if return_pct > 10:
        adj = 0.2
    elif return_pct > 5:
        adj = 0.1
    elif return_pct > 0:
        adj = 0.05
    elif return_pct > -5:
        adj = -0.1
    else:
        adj = -0.2
    confidence += adj
    breakdown['return_pct_adj'] = adj

    # 2. 新聞因素 (Before - 記錄 confidence_before_news)
    confidence_before_news = round(confidence, 2)

    news_weight = news_data.get('total_weight', 0) or 0
    news_adj = 0
    if news_weight == 0:
        news_adj = 0.1  # 無新聞 = 穩定
    elif news_weight < 3:
        news_adj = 0.05
    elif news_weight > 7:
        news_adj = -0.2

    b = news_data.get('breakdown', {})
    positive = b.get('positive', 0)
    negative = b.get('negative', 0)
    sentiment_adj = 0
    if positive > negative:
        sentiment_adj = 0.1
    elif negative > positive:
        sentiment_adj = -0.1

    confidence += news_adj + sentiment_adj
    breakdown['news_weight_adj'] = news_adj
    breakdown['sentiment_adj'] = sentiment_adj
    confidence_after_news = round(confidence, 2)

    # 3. 市場環境 (略，VIX API 可能不可用)
    confidence = max(0.1, min(0.95, confidence))
    confidence_final = round(confidence, 2)

    return {
        'confidence_before_news': confidence_before_news,
        'confidence_after_news': confidence_after_news,
        'confidence_final': confidence_final,
        'breakdown': breakdown,
    }


def get_news_weight_from_api(symbol_query: str):
    """從 API 獲取新聞權重"""
    import subprocess
    try:
        result = subprocess.run(
            ['curl', '-s', f'{API_BASE}/news/weight/{symbol_query}'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception as e:
        print(f"  API 錯誤: {e}")
    return {'total_weight': 0, 'news_count': 0, 'breakdown': {'positive': 0, 'negative': 0, 'neutral': 0}}


def simulate_fox_analysis_current_behavior(stock: dict, news_data_with_prefix: dict):
    """模擬 Fox Analysis v2 的【現有行為】(使用 US.SYMBOL - 有 Bug)"""
    # 現有 fox_analysis_v2.py 使用 US.TSLA → API 返回 0
    news_weight = news_data_with_prefix.get('total_weight', 0)
    news_ok, news_reason = check_news_risk(news_weight)
    confidence_info = calculate_confidence_base(stock, news_data_with_prefix)

    # 決定信號 (簡化版：信心度>0.8=BUY, 信心度>0.6=HOLD, 否則=SELL)
    confidence = confidence_info['confidence_final']
    if not news_ok:
        signal = 'HOLD'
        signal_reason = f'新聞風險: {news_reason}'
    elif confidence >= RISK_PARAMS['HIGH_CONFIDENCE']:
        signal = 'BUY'
        signal_reason = f'高信心度 ({confidence})'
    elif confidence >= RISK_PARAMS['MIN_CONFIDENCE']:
        signal = 'HOLD'
        signal_reason = f'中等信心度 ({confidence})'
    else:
        signal = 'SELL'
        signal_reason = f'低信心度 ({confidence})'

    return {
        'news_weight': news_weight,
        'news_ok': news_ok,
        'news_reason': news_reason,
        'confidence_before_news': confidence_info['confidence_before_news'],
        'confidence_after_news': confidence_info['confidence_after_news'],
        'confidence_final': confidence,
        'signal': signal,
        'signal_reason': signal_reason,
    }


def simulate_fox_analysis_fixed_behavior(stock: dict, news_data_clean: dict):
    """模擬 Fox Analysis v2 的【修復後行為】(使用 TSLA - 正確)"""
    news_weight = news_data_clean.get('total_weight', 0)
    news_ok, news_reason = check_news_risk(news_weight)
    confidence_info = calculate_confidence_base(stock, news_data_clean)

    confidence = confidence_info['confidence_final']
    if not news_ok:
        signal = 'HOLD'
        signal_reason = f'新聞風險阻擋: {news_reason}'
    elif confidence >= RISK_PARAMS['HIGH_CONFIDENCE']:
        signal = 'BUY'
        signal_reason = f'高信心度 ({confidence})'
    elif confidence >= RISK_PARAMS['MIN_CONFIDENCE']:
        signal = 'HOLD'
        signal_reason = f'中等信心度 ({confidence})'
    else:
        signal = 'SELL'
        signal_reason = f'低信心度 ({confidence})'

    return {
        'news_weight': news_weight,
        'news_ok': news_ok,
        'news_reason': news_reason,
        'confidence_before_news': confidence_info['confidence_before_news'],
        'confidence_after_news': confidence_info['confidence_after_news'],
        'confidence_final': confidence,
        'signal': signal,
        'signal_reason': signal_reason,
        'breakdown_detail': confidence_info['breakdown'],
    }


def main():
    print("=" * 70)
    print("🦊 Fox Analysis v2 × 新聞風控 實測")
    print(f"   時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   新聞權重閾值: {RISK_PARAMS['NEWS_WEIGHT_THRESHOLD']}")
    print("=" * 70)

    results = []

    for stock in TEST_STOCKS:
        symbol = stock['symbol']
        symbol_clean = stock['symbol_clean']
        print(f"\n{'='*60}")
        print(f"📊 標的: {symbol} [{stock['category']}]")
        print(f"   持倉: {stock['quantity']} 股 @ ${stock['avg_price']} | 回報: {stock['return_pct']}%")

        # 獲取新聞 - 兩種方式
        news_with_prefix = get_news_weight_from_api(symbol)       # US.TSLA (有Bug)
        news_clean = get_news_weight_from_api(symbol_clean)        # TSLA (正確)

        print(f"\n   📰 新聞數據:")
        print(f"      [現有行為] US.{symbol_clean} → weight={news_with_prefix['total_weight']}, count={news_with_prefix.get('news_count',0)}")
        print(f"      [正確行為] {symbol_clean}    → weight={news_clean['total_weight']}, count={news_clean.get('news_count',0)}")
        bd = news_clean.get('breakdown', {})
        print(f"      breakdown: +{bd.get('positive',0)} / -{bd.get('negative',0)} / ={bd.get('neutral',0)}")

        # 模擬現有行為 (Bug - 看不到新聞)
        current = simulate_fox_analysis_current_behavior(stock, news_with_prefix)
        # 模擬修復後行為 (正確)
        fixed = simulate_fox_analysis_fixed_behavior(stock, news_clean)

        print(f"\n   🔴 【現有行為 - 有Bug】(用 US.{symbol_clean} 查詢):")
        print(f"      news_weight={current['news_weight']} | news_ok={current['news_ok']}")
        print(f"      confidence_before_news={current['confidence_before_news']} | after={current['confidence_after_news']} | final={current['confidence_final']}")
        print(f"      → Signal: {current['signal']} | {current['signal_reason']}")

        print(f"\n   🟢 【修復後行為】(用 {symbol_clean} 查詢):")
        print(f"      news_weight={fixed['news_weight']} | news_ok={fixed['news_ok']}")
        print(f"      confidence_before_news={fixed['confidence_before_news']} | after={fixed['confidence_after_news']} | final={fixed['confidence_final']}")
        print(f"      → Signal: {fixed['signal']} | {fixed['signal_reason']}")
        print(f"      breakdown_detail: {fixed['breakdown_detail']}")

        # 驗證關鍵邏輯
        if fixed['news_weight'] > RISK_PARAMS['NEWS_WEIGHT_THRESHOLD']:
            if fixed['signal'] == 'HOLD':
                print(f"\n   ✅ 驗證通過: 高news_weight({fixed['news_weight']}>5) → news_ok=False → 信號被擋成HOLD")
            else:
                print(f"\n   ❌ 驗證失敗: 高news_weight({fixed['news_weight']}>5) 但信號是 {fixed['signal']}!")

        results.append({
            'symbol': symbol,
            'symbol_clean': symbol_clean,
            'category': stock['category'],
            'quantity': stock['quantity'],
            'return_pct': stock['return_pct'],
            'news_count_24h': news_clean.get('news_count', 0),
            'news_weight': fixed['news_weight'],
            'news_breakdown': news_clean.get('breakdown', {}),
            'news_ok': fixed['news_ok'],
            'confidence_before_news': fixed['confidence_before_news'],
            'confidence_after_news': fixed['confidence_after_news'],
            'confidence_final': fixed['confidence_final'],
            'signal_current_buggy': current['signal'],
            'signal_fixed': fixed['signal'],
            'signal_reason': fixed['signal_reason'],
            'bug_impact': current['signal'] != fixed['signal'],
        })

    # 總結
    print(f"\n{'='*70}")
    print("📋 總結")
    print(f"{'='*70}")
    for r in results:
        bug_flag = " ⚠️ BUG影響" if r['bug_impact'] else ""
        print(f"  {r['symbol']:<10} [{r['category']:<10}] news_weight={r['news_weight']:>3} | news_ok={str(r['news_ok']):<5} | "
              f"signal_current={r['signal_current_buggy']:<4} | signal_fixed={r['signal_fixed']:<4}{bug_flag}")

    return results


if __name__ == '__main__':
    results = main()
