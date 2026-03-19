#!/usr/bin/env python3
"""
debug_confidence.py - 信心度分解診斷工具

Usage:
    python3 scripts/debug_confidence.py           # 分析所有持倉
    python3 scripts/debug_confidence.py US.TSLA   # 分析指定股票
    python3 scripts/debug_confidence.py TSLA      # 自動補 US. 前綴
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
    os.environ.pop(k, None)

import requests
from config.database import get_db_cursor

API = 'http://127.0.0.1:8080/api/v1'

def api_get(path):
    try:
        r = requests.get(f'{API}{path}', timeout=10)
        return r.json()
    except:
        return {}

def get_market_data():
    d = api_get('/market')
    markets = {m['type']: m['value'] for m in d.get('markets', [])}
    return {
        'vix': markets.get('VIX'),
        'spy': markets.get('SPY'),
        'qqq': markets.get('QQQ'),
        'market_drop': markets.get('MARKET_DROP', 0),
    }

def get_news_data(symbol):
    code = symbol.replace('US.', '')
    d = api_get(f'/news?symbol={code}&limit=20')
    news = d.get('news', [])
    pos = sum(1 for n in news if n.get('sentiment') == 'positive')
    neg = sum(1 for n in news if n.get('sentiment') == 'negative')
    total_w = sum(n.get('weight', 0) for n in news)
    return {
        'total_weight': total_w,
        'breakdown': {'positive': pos, 'negative': neg},
        'count': len(news),
    }

def get_agent_scores(symbol):
    with get_db_cursor() as c:
        c.execute("""
            SELECT score_type, score, reasoning, updated_at
            FROM agent_scores
            WHERE symbol = %s AND updated_at > NOW() - INTERVAL 1 HOUR
            ORDER BY updated_at DESC
        """, (symbol,))
        rows = c.fetchall()
    result = {}
    for r in rows:
        result[r['score_type']] = {
            'score': float(r['score']),
            'reasoning': r['reasoning'],
            'updated_at': str(r['updated_at']),
        }
    return result

def debug_confidence(symbol, position=None):
    if not symbol.startswith('US.'):
        symbol = f'US.{symbol}'

    print(f"\n{'='*60}")
    print(f"  📊 信心度分解：{symbol}")
    print(f"{'='*60}")

    # 持倉數據
    if position is None:
        with get_db_cursor() as c:
            c.execute("SELECT * FROM paper_positions WHERE symbol = %s", (symbol,))
            position = c.fetchone()
    
    if not position:
        position = {'symbol': symbol, 'return_pct': 0}

    return_pct = float(position.get('return_pct') or position.get('unrealized_pnl_pct') or 0)

    market = get_market_data()
    news = get_news_data(symbol)
    agent = get_agent_scores(symbol)

    confidence = 0.50
    steps = []

    # --- 基礎分 ---
    steps.append(('基礎分', 0.50, 0.50, '固定起點'))

    # --- 持倉回報 ---
    if return_pct > 15:
        delta = +0.18; label = '強勢獲利'
    elif return_pct > 8:
        delta = +0.12; label = '獲利中'
    elif return_pct > 0:
        delta = +0.06; label = '小幅獲利'
    elif return_pct > -5:
        delta = -0.08; label = '小幅虧損'
    else:
        delta = -0.16; label = '虧損'
    confidence += delta
    steps.append(('持倉回報', delta, confidence, f'{return_pct:+.2f}% → {label}'))

    # --- 新聞 ---
    total_w = news.get('total_weight', 0) or 0
    pos_n = news.get('breakdown', {}).get('positive', 0)
    neg_n = news.get('breakdown', {}).get('negative', 0)
    
    if total_w == 0:
        delta = +0.08; label = '無重大新聞'
    elif total_w < 3:
        delta = +0.04; label = '新聞量輕'
    elif total_w > 7:
        delta = -0.16; label = '新聞量大'
    else:
        delta = 0; label = '新聞量中等'
    confidence += delta
    steps.append(('新聞量', delta, confidence, f'weight={total_w} → {label}'))

    if pos_n > neg_n:
        delta = +0.06; label = '正面情緒'
    elif neg_n > pos_n:
        delta = -0.06; label = '負面情緒'
    else:
        delta = 0; label = '中性'
    confidence += delta
    steps.append(('新聞情緒', delta, confidence, f'正={pos_n} 負={neg_n} → {label}'))

    # --- VIX ---
    vix = market.get('vix')
    if vix is not None:
        if vix < 15:
            delta = +0.12; label = '市場平靜'
        elif vix < 20:
            delta = +0.06; label = '市場穩定'
        elif vix > 30:
            delta = -0.14; label = '市場恐慌'
        elif vix > 25:
            delta = -0.08; label = '波動升高'
        else:
            delta = 0; label = '正常'
        confidence += delta
        steps.append(('VIX', delta, confidence, f'VIX={vix:.1f} → {label}'))

    # --- 大盤 ---
    market_drop = market.get('market_drop', 0) or 0
    if market_drop > 1:
        delta = +0.05; label = '大盤強勢'
    elif market_drop < -2:
        delta = -0.10; label = '大盤大跌'
    else:
        delta = 0; label = '大盤平穩'
    confidence += delta
    steps.append(('大盤', delta, confidence, f'MARKET_DROP={market_drop:+.2f}% → {label}'))

    # --- Agent 評分 ---
    if agent:
        news_risk_d = agent.get('news_risk', {})
        news_risk = news_risk_d.get('score', 0)
        delta = -(news_risk * 0.1)
        confidence += delta
        updated = news_risk_d.get('updated_at', 'N/A')
        steps.append(('Agent:新聞風險', delta, confidence,
                       f'news_risk={news_risk:+.3f} × -10% | 更新:{updated[-8:] if updated != "N/A" else "N/A"}'))

        strat_d = agent.get('strategy_signal', {})
        strat = strat_d.get('score', 0)
        delta = strat * 0.1
        confidence += delta
        updated = strat_d.get('updated_at', 'N/A')
        steps.append(('Agent:技術信號', delta, confidence,
                       f'strategy_signal={strat:+.3f} × 10% | 更新:{updated[-8:] if updated != "N/A" else "N/A"}'))
    else:
        steps.append(('Agent評分', 0, confidence, '⚠️ 無資料（超過1小時或未執行）'))

    # --- 輸出 ---
    print(f"\n  {'項目':<14} {'調整':>7}  {'累計':>7}  說明")
    print(f"  {'-'*55}")
    for name, delta, cum, desc in steps:
        delta_str = f'{delta:+.2f}' if delta != 0 else '  0.00'
        print(f"  {name:<14} {delta_str:>7}  {cum:>7.4f}  {desc}")

    # 最終判斷
    conf_final = round(min(max(confidence, 0.0), 1.0), 4)
    print(f"\n  {'─'*55}")
    if conf_final >= 0.80:
        tier = 'HIGH'; emoji = '🟢'
    elif conf_final >= 0.60:
        tier = 'MEDIUM'; emoji = '🟡'
    else:
        tier = 'LOW'; emoji = '🔴'

    if conf_final >= 0.60:
        verdict = '✅ 允許 BUY/SELL'
    else:
        verdict = '❌ 降級為 HOLD（未達 0.60 門檻）'

    print(f"\n  最終信心度：{conf_final:.4f}  [{tier}] {emoji}")
    print(f"  結論：{verdict}\n")

    return conf_final


def main():
    if len(sys.argv) > 1:
        symbol = sys.argv[1]
        debug_confidence(symbol)
    else:
        # 分析所有持倉
        with get_db_cursor() as c:
            c.execute("SELECT symbol, unrealized_pnl_pct as return_pct FROM paper_positions WHERE quantity > 0 ORDER BY symbol")
            positions = c.fetchall()
        
        if not positions:
            print("目前無持倉")
            return
        
        print(f"\n分析 {len(positions)} 個持倉...")
        results = []
        for pos in positions:
            conf = debug_confidence(pos['symbol'], pos)
            results.append((pos['symbol'], conf))
        
        print(f"\n{'='*60}")
        print(f"  匯總")
        print(f"{'='*60}")
        print(f"  {'股票':<12} {'信心度':>8}  {'門檻':>6}  結論")
        print(f"  {'-'*45}")
        for sym, conf in sorted(results, key=lambda x: -x[1]):
            verdict = '✅ 可交易' if conf >= 0.60 else '❌ HOLD'
            print(f"  {sym:<12} {conf:>8.4f}  {'0.60':>6}  {verdict}")


if __name__ == '__main__':
    main()
