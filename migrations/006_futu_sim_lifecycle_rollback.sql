-- Rollback for futu sim lifecycle schema
-- migrations/006_futu_sim_lifecycle_rollback.sql

DROP TABLE IF EXISTS sync_checkpoints;
DROP TABLE IF EXISTS account_equity_snapshots;
DROP TABLE IF EXISTS broker_positions_snapshot;
DROP TABLE IF EXISTS broker_fills;
DROP TABLE IF EXISTS trade_lifecycles;
DROP TABLE IF EXISTS broker_orders;
DROP TABLE IF EXISTS strategy_signals;
