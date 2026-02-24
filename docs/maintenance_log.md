
## 2026-02-25: 模拟交易数据清理

### 问题
- `paper_orders` 表存在测试数据 (id=2: TSLA BUY 50股 @ 200.00)
- `paper_positions` 表有对应的无效持仓记录

### 修复操作
1. 删除测试订单: `DELETE FROM paper_orders WHERE id = 2`
2. 删除测试持仓: `DELETE FROM paper_positions WHERE symbol = 'TSLA'` (非 US.TSLA 格式)
3. 清理旧的 daily_summary 数据
4. 更新 2/24 的统计数据

### 修复后状态
- **paper_orders**: 2条有效订单
  - id=3: US.UBER SELL 1425股 @ 70.60 (平仓)
  - id=4: US.TSLA BUY 245股 @ 406.80
- **paper_positions**: 1条持仓
  - US.TSLA: 245股, 成本 $406.80, 市值 $99,666
- **paper_daily_summary**: 已更新 trade_count=2, buy_count=1, sell_count=1

### 说明
UBER SELL 操作是平仓操作，代码逻辑：当 quantity <= 0 时自动删除持仓记录。
