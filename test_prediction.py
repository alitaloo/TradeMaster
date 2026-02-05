#!/usr/bin/env python3
"""
測試預測引擎
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from modules.prediction import PredictionEngine, ProbabilityCalculator, FactorAnalyzer
from data import DataEngine


def test_factor_analyzer():
    """測試因素分析器"""
    print("\n=== 測試因素分析器 ===")
    
    analyzer = FactorAnalyzer()
    
    # 使用真實數據測試
    data_engine = DataEngine()
    df = data_engine.get_daily_data("AAPL", period="3mo")
    
    if df is None:
        print("❌ 無法獲取數據")
        return False
    
    factors = analyzer.analyze(df)
    
    print(f"✅ 技術分數: {factors['technical_score']:.3f}")
    print(f"✅ 動量: {factors['momentum']}")
    print(f"✅ 支撐阻力: {factors['support_resistance']:.3f}")
    
    return True


def test_probability_calculator():
    """測試概率計算器"""
    print("\n=== 測試概率計算器 ===")
    
    calculator = ProbabilityCalculator()
    
    # 測試上漲預測
    factors = {
        "technical_score": 0.72,
        "momentum": "POSITIVE",
        "support_resistance": 0.65
    }
    
    result = calculator.calculate(factors, "UP", 10, 5)
    
    print(f"✅ 符號: {result.symbol}")
    print(f"✅ 方向: {result.direction}")
    print(f"✅ 概率: {result.probability:.3f}")
    print(f"✅ 置信度: {result.confidence}")
    print(f"✅ 因素: {result.factors}")
    
    return True


def test_prediction_engine():
    """測試預測引擎"""
    print("\n=== 測試預測引擎 ===")
    
    data_engine = DataEngine()
    engine = PredictionEngine(data_engine=data_engine)
    
    # 測試指令格式
    result = engine.predict_from_command("AAPL/📈/10/5")
    
    if result.get("success"):
        data = result["data"]
        print(f"✅ 預測成功!")
        print(f"   符號: {data['symbol']}")
        print(f"   方向: {data['direction']}")
        print(f"   概率: {data['probability']:.1%}")
        print(f"   置信度: {data['confidence']}")
    else:
        print(f"❌ 預測失敗: {result.get('error')}")
        return False
    
    return True


def main():
    print("=" * 50)
    print("TradeMaster v2.0 - 預測模組測試")
    print("=" * 50)
    
    tests_passed = 0
    tests_total = 3
    
    if test_factor_analyzer():
        tests_passed += 1
    
    if test_probability_calculator():
        tests_passed += 1
    
    if test_prediction_engine():
        tests_passed += 1
    
    print("\n" + "=" * 50)
    print(f"測試結果: {tests_passed}/{tests_total} 通過")
    print("=" * 50)
    
    return 0 if tests_passed == tests_total else 1


if __name__ == "__main__":
    sys.exit(main())
