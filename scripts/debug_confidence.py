#!/usr/bin/env python3
"""
信心度 Debug 工具 - 拆解每個股票的信心度計算過程

Usage:
    python3 scripts/debug_confidence.py          # 所有持倉
    python3 scripts/debug_confidence.py US.TSLA  # 單一股票
    python3 scripts/debug_confidence.py TSLA     # 不帶前綴也行
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
    os.environ.pop(k, None)

from config.database import get_db_cursor
import requests

API = 'http://127.0.0.1:8080/api/v1'

def api_get(path):
    try:
        r = requests.get(f'{API}{path}', timeout=10)
        return r.json()
    except:
        return {}

def get_market_data():
    r = api_get('/market')
    markets = {m['type']: m['value'] for m in r.get('markets', [])}
    return {
        'vix': markets.get('VIX'),
        'market_drop': markets.get('MARKET_DROP', 0),
        'spy': markets.get('SPY'),
        'qqq': markets.get('QQQ'),
    }

def get_news_data(symbol):
    sym = symbol.replace('US.', '')
    r = api_get(f'/news/analysis?symbol={sym}')
    return r if r else {}

def get_tf_signals(symbol):
    sym = symbol.replace('US.', '')
    r = api_get(f'/signals?symbol={sym}&limit=3')
    signals = r.get('signals', [])
    if not signals:
        return None
    # 簡單取最新的
    latest = signals[0]
    return {
        'consensus': latest.get('action'),
        '1h': latest.get('action'),
        '1d': latest.get('action'),
    }

def get_agent_scores(symbol):
    with get_db_cursor() as c:
        c.execute("""
            SELECT agent_id, score_type, score, reasoning, updated_at
            FROM agent_scores
            WHERE symbol = %s
            AND updated_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
            ORDER BY agent_id
        """, (symbol,))
        rows = c.fetchall()
    result = {}
    for r in rows:
        if r['score_type'] == 'news_risk':
            result['news_risk'] = float(r['score'])
            result['news_risk_reason'] = r['reasoning'] or ''
            result['news_risk_at'] = str(r['updated_at'])
        elif r['score_type'] == 'strategy_signal':
            result['strategy_signal'] = float(r['score'])
            result['strategy_reason'] = r['reasoning'] or ''
            result['strategy_at'] = str(r['updated_at'])
    return result

def get_position(symbol):
    with get_db_cursor() as c:
        c.execute("SELECT * FROM paper_positions WHERE symbol = %s AND quantity != 0", (symbol,))
        r = c.fetchone()
    if not r:
        return None
    pnl = float(r['unrealized_pnl'] or 0)
    cost = float(r['average_cost'] or 0) * int(r['quantity'])
    return_pct = (pnl / cost * 100) if cost != 0 else 0
    return {
        'symbol': symbol,
        'quantity': r['quantity'],
        'average_cost': float(r['average_cost'] or 0),
        'current_price': float(r['current_price'] or 0),
        'unrealized_pnl': pnl,
        'return_pct': return_pct,
    }

def debug_confidence(symbol):
    if not symbol.startswith('US.'):
        symbol = f'US.{symbol}'

    print(f"\n{'='*60}")
    print(f"  {symbol} 信心度拆解")
    print(f"{'='*60}")

    pos = get_position(symbol)
    if not pos:
        print(f"  ⚠️ 無持倉資料（使用虛擬持倉）")
        pos = {'symbol': symbol, 'quantity': 100, 'return_pct': 0}

    market = get_market_data()
    news = get_news_data(symbol)
    agent = get_agent_scores(symbol)

    # ======= 模擬計算（跟 calculate_confidence 邏輯一致）=======
    confidence = 0.50
    steps = [("基礎分", 0.50, 0.50)]

    # 1. 持倉報酬率
    return_pct = pos.get('return_pct', 0) or 0
    if return_pct > 15:
        delta = +0.18; tag = f"持倉報酬 +{return_pct:.1f}% (強正)"
    elif return_pct > 8:
        delta = +0.12; tag = f"持倉報酬 +{return_pct:.1f}% (正)"
    elif return_pct > 0:
        delta = +0.06; tag = f"持倉報酬 +{return_pct:.1f}% (微正)"
    elif return_pct > -5:
        delta = -0.08; tag = f"持倉報酬 {return_pct:.1f}% (微負)"
    else:
        delta = -0.16; tag = f"持倉報酬 {return_pct:.1f}% (負)"
    confidence += delta
    steps.append((tag, delta, confidence))

    # 2. 新聞權重
    news_weight = news.get('total_weight', 0) or 0
    news_degraded = news.get('degraded', False)
    if news_degraded or news_weight is None:
        delta = 0; tag = "新聞: API降級"
    elif news_weight == 0:
        delta = +0.08; tag = "新聞: 安靜"
    elif news_weight < 3:
        delta = +0.04; tag = f"新聞: 輕量(weight={news_weight})"
    elif news_weight > 7:
        delta = -0.16; tag = f"新聞: 密集(weight={news_weight})"
    else:
        delta = 0; tag = f"新聞: 一般(weight={news_weight})"
    confidence += delta
    steps.append((tag, delta, confidence))

    # 3. 情緒
    bd = news.get('breakdown', {})
    pos_n = bd.get('positive', 0)
    neg_n = bd.get('negative', 0)
    if pos_n > neg_n:
        delta = +0.06; tag = f"情緒: 正面 (+{pos_n}/-{neg_n})"
    elif neg_n > pos_n:
        delta = -0.06; tag = f"情緒: 負面 (+{pos_n}/-{neg_n})"
    else:
        delta = 0; tag = f"情緒: 中性 (+{pos_n}/-{neg_n})"
    confidence += delta
    steps.append((tag, delta, confidence))

    # 4. VIX
    vix = market.get('vix')
    if vix is not None:
        if vix < 15:
            delta = +0.12; tag = f"VIX={vix:.1f} (平靜)"
        elif vix < 20:
            delta = +0.06; tag = f"VIX={vix:.1f} (穩定)"
        elif vix > 30:
            delta = -0.14; tag = f"VIX={vix:.1f} (恐慌)"
        elif vix > 25:
            delta = -0.08; tag = f"VIX={vix:.1f} (升高)"
        else:
            delta = 0; tag = f"VIX={vix:.1f} (正常)"
        confidence += delta
        steps.append((tag, delta, confidence))

    # 5. 市場漲跌
    md = market.get('market_drop', 0) or 0
    if md > 1:
        delta = +0.05; tag = f"大盤: 強勢(+{md:.2f}%)"
    elif md < -2:
        delta = -0.10; tag = f"大盤: 大跌({md:.2f}%)"
    else:
        delta = 0; tag = f"大盤: 一般({md:.2f}%)"
    confidence += delta
    steps.append((tag, delta, confidence))

    # 6. Agent 評分
    news_risk = agent.get('news_risk', 0)
    if news_risk != 0:
        delta = -(news_risk * 0.1)
        tag = f"Agent新聞風險: {news_risk:+.3f} → {delta:+.3f}"
        confidence += delta
        steps.append((tag, delta, confidence))

    strategy_signal = agent.get('strategy_signal', 0)
    if strategy_signal != 0:
        delta = strategy_signal * 0.1
        tag = f"Agent技術評分: {strategy_signal:+.3f} → {delta:+.3f}"
        confidence += delta
        steps.append((tag, delta, confidence))

    # 收斂
    confidence = max(0.0, min(1.0, round(confidence, 2)))

    # ======= 輸出 =======
    print(f"\n  持倉: {pos.get('quantity',0)}股 @ ${pos.get('average_cost',0):.2f} | 現價=${pos.get('current_price',0):.2f} | 報酬率={return_pct:+.1f}%")
    print(f"  市場: SPY={market.get('spy','N/A')} | VIX={market.get('vix','N/A')} | 大盤={market.get('market_drop',0):+.2f}%")
    print()
    print(f"  {'步驟':<30} {'調整':>8}  {'累計':>6}")
    print(f"  {'-'*50}")
    for name, delta, cum in steps:
        sign = f"{delta:+.2f}" if delta != 0 else "  --  "
        print(f"  {name:<30} {sign:>8}  {cum:.2f}")
    print(f"  {'-'*50}")
    print(f"  最終信心度: {confidence:.2f}", end="")

    if confidence >= 0.75:
        print("  → 🟢 HIGH (強)")
    elif confidence >= 0.60:
        print("  → 🟡 MEDIUM (可執行)")
    else:
        print("  → 🔴 LOW (HOLD，不執行)")

    # Agent 詳情
    if agent:
        print(f"\n  📊 Agent 評分詳情:")
        if 'news_risk' in agent:
            print(f"    新聞風險:  {agent['news_risk']:+.3f}  ({agent.get('news_risk_at','')[:16]})")
            reason = agent.get('news_risk_reason','')[:80]
            if reason:
                print(f"    ↳ {reason}")
        if 'strategy_signal' in agent:
            print(f"    技術評分:  {agent['strategy_signal']:+.3f}  ({agent.get('strategy_at','')[:16]})")
            reason = agent.get('strategy_reason','')[:80]
            if reason:
                print(f"    ↳ {reason}")
    else:
        print(f"\n  ⚠️ Agent 評分: 無資料（超過1小時未更新）")

    print()
    return confidence


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]

    if args:
        for sym in args:
            debug_confidence(sym.upper())
    else:
        # 所有持倉
        with get_db_cursor() as c:
            c.execute("SELECT symbol FROM paper_positions WHERE quantity > 0 ORDER BY symbol")
            symbols = [r['symbol'] for r in c.fetchall()]

        if not symbols:
            print("⚠️ 目前無持倉")
            return

        print(f"\n{'='*60}")
        print(f"  全部持倉信心度快覽")
        print(f"{'='*60}")

        for sym in symbols:
            conf = debug_confidence(sym)


if __name__ == '__main__':
    main()
