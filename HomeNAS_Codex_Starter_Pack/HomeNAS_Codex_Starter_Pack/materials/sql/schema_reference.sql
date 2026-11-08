-- Reference schema only. Production schema must use versioned migrations.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metric_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  value REAL,
  unit TEXT NOT NULL,
  source TEXT NOT NULL,
  quality TEXT NOT NULL DEFAULT 'valid',
  labels_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_metric_samples_name_ts
  ON metric_samples(metric_name, ts_utc);

CREATE TABLE IF NOT EXISTS metric_aggregates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bucket_start_utc TEXT NOT NULL,
  bucket_seconds INTEGER NOT NULL,
  metric_name TEXT NOT NULL,
  value_avg REAL,
  value_min REAL,
  value_max REAL,
  value_last REAL,
  sample_count INTEGER NOT NULL DEFAULT 0,
  unit TEXT NOT NULL,
  source TEXT NOT NULL,
  quality TEXT NOT NULL DEFAULT 'valid',
  labels_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_metric_aggregates_name_bucket
  ON metric_aggregates(metric_name, bucket_seconds, bucket_start_utc);

CREATE TABLE IF NOT EXISTS energy_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  domain TEXT NOT NULL,
  delta_joules REAL,
  power_watts REAL,
  elapsed_seconds REAL,
  quality TEXT NOT NULL DEFAULT 'valid'
);
CREATE INDEX IF NOT EXISTS idx_energy_domain_ts
  ON energy_records(domain, ts_utc);

CREATE TABLE IF NOT EXISTS service_registry (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  category TEXT,
  deployment TEXT,
  discovery_source TEXT NOT NULL,
  identity_confirmed INTEGER NOT NULL DEFAULT 0,
  manifest_json TEXT,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_status (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service_id TEXT NOT NULL,
  ts_utc TEXT NOT NULL,
  status TEXT NOT NULL,
  health_status TEXT,
  cpu_percent REAL,
  memory_bytes INTEGER,
  uptime_seconds INTEGER,
  details_json TEXT,
  FOREIGN KEY(service_id) REFERENCES service_registry(id)
);
CREATE INDEX IF NOT EXISTS idx_service_status_service_ts
  ON service_status(service_id, ts_utc);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  message TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  first_seen_utc TEXT NOT NULL,
  last_seen_utc TEXT NOT NULL,
  recovered_at_utc TEXT,
  acknowledged_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS alert_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_id INTEGER NOT NULL,
  ts_utc TEXT NOT NULL,
  event_type TEXT NOT NULL,
  details_json TEXT,
  FOREIGN KEY(alert_id) REFERENCES alerts(id)
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'admin',
  created_at_utc TEXT NOT NULL,
  last_login_utc TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  revoked_at_utc TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  user_id INTEGER,
  action TEXT NOT NULL,
  target TEXT,
  result TEXT NOT NULL,
  details_json TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);
