# Stage 3 Dry-Run Action Layer

## Goal

把 Stage 2.5 已持久化的 `lifecycle_exit_candidates(active)` 接到一層 **安全的 action layer**，但本輪仍然 **只做 dry-run proposal，不送 broker / Futu order**。

## Scope in this round

- feature flag / action gate
- candidate -> proposal idempotency
- pre-action freshness check
- dry-run proposal 持久化
- audit trail
- CLI / JSON output

## Out of scope in this round

- 真正送出 exit order
- 改寫 lifecycle closure / reconciliation 主流程
- 自動把 proposal 變成 `exit_pending`

## Config

- `risk.exit_action_enabled` (default false)
- `risk.exit_action_mode` = `off | dry_run | live`
  - 本輪實作 `off` / `dry_run`
  - `live` 只保留旗標，不會送單
- `risk.exit_action_freshness_seconds` (default 120)

## Data model

### `lifecycle_exit_action_proposals`

每個 `candidate_id + proposal_mode` 最多一筆 proposal，作為 Stage 3 的最小安全 idempotency 鎖。

核心欄位：
- `candidate_id`
- `lifecycle_id`
- `symbol`
- `action_type` (`exit_market`)
- `action_side` (`sell` for long / `buy` for short)
- `proposal_mode` (`dry_run` / `live`)
- `status` (`proposed` / `blocked` / `stale` / `cancelled` / `executed`)
- `freshness_checked_at`
- `candidate_last_detected_at`
- `snapshot_time`
- `snapshot_age_seconds`
- `action_reason`
- `block_reason`
- `audit_payload`

## Freshness / safety checks

在 proposal 生成前，會重查：

1. candidate 仍為 `active`
2. lifecycle 仍為 open / eligible
   - `signal_created`
   - `order_submitted`
   - `partially_filled`
   - `filled_open`
   - `exit_pending`
3. 最新 `broker_positions_snapshot` 存在
4. `candidate.last_detected_at` 未過舊
5. `snapshot_time` 未過舊

若失敗：
- lifecycle 條件不符 → `blocked`
- snapshot / candidate freshness 不符 → `stale`
- 僅在全部通過時 → `proposed`

## Gate behavior

- gate 關閉時（`enabled=false` 或 `mode=off`）
  - 不生成 proposal row
  - 回傳 `gate_skipped_count`
  - 明確標記 `ready=false`

- gate 開啟且 `mode=dry_run`
  - 只產生 / 更新 dry-run proposal
  - 絕不送單

## CLI

### 生成 dry-run proposals

```bash
python scripts/lifecycle_exit_action.py --json
```

### 只看已持久化 proposals

```bash
python scripts/lifecycle_exit_action.py --list-proposals --json
```

### 篩選狀態

```bash
python scripts/lifecycle_exit_action.py --list-proposals --statuses proposed blocked stale --json
```

## Mainline integration

`execution.futu_sync_service.FutuSyncService.run_risk_monitor()` 現在會：

1. 跑 `LifecycleRiskMonitor.scan()`
2. 再跑 `ExitActionService.generate_proposals()`
3. 將結果掛在 `risk_report['action_layer']`

因此 execution / lifecycle 主線已有 Stage 3 dry-run handoff，但仍維持 no-broker boundary。
