from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS activity_forms (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    parameter_schema_json TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS budget_accounts (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    default_source_sheet TEXT
);

CREATE TABLE IF NOT EXISTS account_rules (
    id TEXT PRIMARY KEY,
    form_code TEXT NOT NULL REFERENCES activity_forms(code) ON DELETE CASCADE,
    rule_name TEXT NOT NULL,
    condition_json TEXT NOT NULL DEFAULT '{}',
    account_code TEXT NOT NULL REFERENCES budget_accounts(code),
    recommended_reason TEXT NOT NULL,
    default_selected INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS account_detail_templates (
    id TEXT PRIMARY KEY,
    account_code TEXT NOT NULL REFERENCES budget_accounts(code) ON DELETE CASCADE,
    item_name TEXT NOT NULL,
    default_unit TEXT NOT NULL,
    reference_key TEXT NOT NULL DEFAULT 'manual',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cost_references (
    id TEXT PRIMARY KEY,
    source_sheet TEXT NOT NULL,
    category TEXT NOT NULL,
    label TEXT,
    region TEXT,
    region_key TEXT,
    origin TEXT,
    origin_key TEXT,
    destination TEXT,
    destination_key TEXT,
    unit TEXT,
    rate_primary REAL,
    rate_secondary REAL,
    rate_tertiary REAL,
    rate_quaternary REAL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cost_reference_category_region
ON cost_references (category, region_key);

CREATE INDEX IF NOT EXISTS idx_cost_reference_category_route
ON cost_references (category, origin_key, destination_key);

CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    fiscal_year INTEGER NOT NULL,
    budget_ceiling REAL NOT NULL,
    default_province TEXT,
    origin_city TEXT DEFAULT 'JAKARTA',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sub_components (
    id TEXT PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(activity_id, code),
    UNIQUE(activity_id, sequence)
);

CREATE TABLE IF NOT EXISTS activity_form_selections (
    id TEXT PRIMARY KEY,
    sub_component_id TEXT NOT NULL REFERENCES sub_components(id) ON DELETE CASCADE,
    form_code TEXT NOT NULL REFERENCES activity_forms(code),
    attributes_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS budget_account_selections (
    id TEXT PRIMARY KEY,
    sub_component_id TEXT NOT NULL REFERENCES sub_components(id) ON DELETE CASCADE,
    form_selection_id TEXT REFERENCES activity_form_selections(id) ON DELETE SET NULL,
    account_code TEXT NOT NULL REFERENCES budget_accounts(code),
    recommendation_reason TEXT,
    source_rule_id TEXT REFERENCES account_rules(id) ON DELETE SET NULL,
    is_recommended INTEGER NOT NULL DEFAULT 1,
    is_selected INTEGER NOT NULL DEFAULT 1,
    is_manual INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_account_selection_unique
ON budget_account_selections (sub_component_id, account_code, is_manual);

CREATE TABLE IF NOT EXISTS budget_lines (
    id TEXT PRIMARY KEY,
    account_selection_id TEXT NOT NULL REFERENCES budget_account_selections(id) ON DELETE CASCADE,
    template_id TEXT REFERENCES account_detail_templates(id) ON DELETE SET NULL,
    item_name TEXT NOT NULL,
    specification TEXT,
    volume REAL NOT NULL DEFAULT 0,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL DEFAULT 0,
    suggested_unit_price REAL,
    amount REAL NOT NULL DEFAULT 0,
    suggestion_note TEXT,
    pricing_context_json TEXT NOT NULL DEFAULT '{}',
    is_manual INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def db_cursor() -> sqlite3.Connection:
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def bootstrap_schema() -> None:
    with db_cursor() as connection:
        connection.executescript(SCHEMA_SQL)

