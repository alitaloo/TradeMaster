# Stage 2.5 Exit Candidate State (detect-only)

## Goal

把 lifecycle risk detect 從「一次性掃描結果」提升為「可持久化、可去重、可供 Stage 3 action layer 接手的狀態」。

## This stage does

- 掃描 open `trade_lifecycles`
- 產生 detect-only exit candidates
- 持久化到 `lifecycle_exit_candidates`
- 針對相同 `lifecycle_id + candidate_type` 做 cooldown / dedupe
- 當條件消失時把 active candidate 標記為 `resolved`
- 透過 `scripts/lifecycle_risk_scan.py --list-active` 查看目前 active 候選

## This stage does NOT do

- 不送出任何 exit order
- 不直接修改 lifecycle 為 closed
- 不把 detect layer 與 future action layer 混在一起

## Table

`lifecycle_exit_candidates`

核心欄位：
- `lifecycle_id`
- `symbol`
- `candidate_type` (`holding_timeout` / `stop_loss` / `take_profit`)
- `status` (`active` / `resolved` / `ignored`)
- `first_detected_at`
- `last_detected_at`
- `resolved_at`
- `threshold_value`
- `current_price`
- `threshold_source`
- `reason`
- `detection_count`
- `metadata`

## Cooldown

- config key: `risk.exit_candidate_cooldown_seconds`
- default: `300`
- 同一 active candidate 在 cooldown 內再次被掃到時：
  - 不新建 row
  - 更新 `last_detected_at`
  - `detection_count += 1`
  - `persist_action = cooldown_refreshed`

## Stage 3 handoff

未來 auto-exit action layer 應從：

- `lifecycle_exit_candidates`
- 篩選 `status = 'active'`
- 依 `last_detected_at ASC`（或未來加入更嚴格優先級）取出
- 再經過 action guard / order submission / reconciliation

也就是：

`risk detect -> lifecycle_exit_candidates(active) -> future action layer -> broker order / lifecycle exit_pending`

目前 `LifecycleRiskMonitor.scan()` 會在回傳值中帶上 `stage3_handoff`，作為明確接點說明。
