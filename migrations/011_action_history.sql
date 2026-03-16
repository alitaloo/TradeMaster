-- 011_action_history.sql
-- Action 執行記錄持久化（僅限白名單手動 action）

CREATE TABLE IF NOT EXISTS action_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT    NOT NULL,          -- sync_news / refresh_kline / refresh_status
    status      TEXT    NOT NULL,          -- success / failed
    started_at  TEXT    NOT NULL,          -- ISO8601
    finished_at TEXT,                      -- ISO8601
    summary     TEXT,                      -- 成功時的摘要
    error       TEXT,                      -- 失敗時的錯誤訊息
    created_at  TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_action_history_action ON action_history(action);
CREATE INDEX IF NOT EXISTS idx_action_history_created ON action_history(created_at DESC);
