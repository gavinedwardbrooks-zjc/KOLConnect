from __future__ import annotations

"""Versioned SQLite schema matching the current workbook business contract."""

from datetime import datetime, timezone

from storage.errors import SQLiteSchemaUnsupportedError


CURRENT_SCHEMA_VERSION = 3


SCHEMA_V1_SQL = r"""
CREATE TABLE storage_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE creators (
    creator_id TEXT PRIMARY KEY,
    name TEXT,
    platform TEXT,
    profile_url TEXT,
    country TEXT,
    language TEXT,
    content_category TEXT,
    followers INTEGER,
    insight_level TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT,
    email TEXT,
    whatsapp TEXT,
    cooperation_stage TEXT,
    recent_product TEXT,
    quote REAL,
    owner TEXT,
    last_contact_time TEXT,
    next_follow_up_time TEXT,
    note TEXT,
    agency_id TEXT,
    current_contact_id TEXT,
    source_contact_id TEXT,
    bio TEXT,
    archived_at TEXT
);

CREATE TABLE creator_tags (
    creator_id TEXT NOT NULL REFERENCES creators(creator_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (creator_id, position),
    UNIQUE (creator_id, tag)
);

CREATE TABLE creator_accounts (
    account_uid TEXT PRIMARY KEY,
    account_id TEXT,
    creator_id TEXT NOT NULL REFERENCES creators(creator_id) ON DELETE RESTRICT,
    platform TEXT,
    username TEXT,
    profile_url TEXT,
    followers INTEGER,
    account_email TEXT,
    latest_post_date TEXT,
    last_scrape_time TEXT,
    data_source TEXT,
    scrape_status TEXT,
    platform_account_id TEXT,
    attribution_status TEXT,
    note TEXT,
    source_task_id TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE videos (
    creator_id TEXT NOT NULL REFERENCES creators(creator_id) ON DELETE RESTRICT,
    video_url TEXT NOT NULL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    captured_at TEXT,
    PRIMARY KEY (creator_id, video_url)
);

CREATE TABLE insights (
    creator_id TEXT PRIMARY KEY REFERENCES creators(creator_id) ON DELETE RESTRICT,
    average_views REAL,
    median_views REAL,
    stability REAL,
    risks TEXT,
    recommendation TEXT
);

CREATE TABLE creator_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    creator_id TEXT NOT NULL REFERENCES creators(creator_id) ON DELETE RESTRICT,
    platform TEXT,
    account_uid TEXT REFERENCES creator_accounts(account_uid) ON DELETE RESTRICT,
    followers INTEGER,
    average_views REAL,
    median_views REAL,
    video_count INTEGER,
    creator_score REAL,
    insight_level TEXT,
    captured_at TEXT,
    source TEXT
);

CREATE TABLE video_snapshots (
    video_snapshot_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES creator_snapshots(snapshot_id) ON DELETE RESTRICT,
    creator_id TEXT NOT NULL REFERENCES creators(creator_id) ON DELETE RESTRICT,
    video_id TEXT,
    video_url TEXT,
    platform TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    captured_at TEXT
);

CREATE TABLE cooperations (
    cooperation_id TEXT PRIMARY KEY,
    creator_id TEXT NOT NULL REFERENCES creators(creator_id) ON DELETE RESTRICT,
    campaign TEXT,
    platform TEXT,
    contact_date TEXT,
    price REAL,
    published_count INTEGER,
    total_views INTEGER,
    average_views REAL,
    roi REAL,
    result TEXT,
    note TEXT,
    created_at TEXT
);

CREATE TABLE agencies (
    agency_id TEXT PRIMARY KEY,
    name TEXT,
    country TEXT,
    website TEXT,
    public_email TEXT,
    whatsapp TEXT,
    cooperation_stage TEXT,
    tags TEXT,
    last_contact_time TEXT,
    next_follow_up_time TEXT,
    owner TEXT,
    note TEXT,
    resource_files TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE agency_contacts (
    contact_id TEXT PRIMARY KEY,
    name TEXT,
    agency_id TEXT REFERENCES agencies(agency_id) ON DELETE RESTRICT,
    position TEXT,
    email TEXT,
    whatsapp TEXT,
    language TEXT,
    status TEXT,
    last_contact_time TEXT,
    next_follow_up_time TEXT,
    owner TEXT,
    note TEXT,
    external_record_id TEXT,
    source TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE follow_up_logs (
    follow_up_id TEXT PRIMARY KEY,
    object_type TEXT,
    object_id TEXT,
    contact_method TEXT,
    content TEXT,
    stage_before TEXT,
    stage_after TEXT,
    contacted_at TEXT,
    next_follow_up_time TEXT,
    owner TEXT,
    created_at TEXT
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    name TEXT,
    company_name TEXT,
    note TEXT,
    created_at TEXT,
    updated_at TEXT,
    archived_at TEXT
);

CREATE TABLE campaigns (
    campaign_id TEXT PRIMARY KEY,
    product_id TEXT REFERENCES products(product_id) ON DELETE RESTRICT,
    name TEXT,
    country TEXT,
    platform TEXT,
    start_date TEXT,
    end_date TEXT,
    owner TEXT,
    status TEXT,
    budget REAL,
    goal TEXT,
    note TEXT,
    created_at TEXT,
    updated_at TEXT,
    archived_at TEXT
);

CREATE TABLE campaign_platforms (
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    platform TEXT NOT NULL,
    PRIMARY KEY (campaign_id, position),
    UNIQUE (campaign_id, platform)
);

CREATE TABLE campaign_creators (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE RESTRICT,
    creator_id TEXT NOT NULL REFERENCES creators(creator_id) ON DELETE RESTRICT,
    account_id TEXT,
    stage TEXT,
    owner TEXT,
    quote_currency TEXT,
    quote_unit_amount REAL,
    quote_quantity INTEGER,
    quote_unit TEXT,
    creator_quote REAL,
    cost REAL,
    cost_currency TEXT,
    publish_date TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    roi REAL,
    performance_note TEXT,
    created_at TEXT,
    updated_at TEXT,
    archived_at TEXT
);

CREATE TABLE campaign_creator_accounts (
    campaign_creator_id TEXT NOT NULL REFERENCES campaign_creators(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    account_uid TEXT NOT NULL REFERENCES creator_accounts(account_uid) ON DELETE RESTRICT,
    PRIMARY KEY (campaign_creator_id, position),
    UNIQUE (campaign_creator_id, account_uid)
);

CREATE TABLE campaign_creator_planned_dates (
    campaign_creator_id TEXT NOT NULL REFERENCES campaign_creators(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    planned_date TEXT NOT NULL,
    PRIMARY KEY (campaign_creator_id, position),
    UNIQUE (campaign_creator_id, planned_date)
);

CREATE TABLE campaign_creator_publish_links (
    campaign_creator_id TEXT NOT NULL REFERENCES campaign_creators(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    publish_link TEXT NOT NULL,
    PRIMARY KEY (campaign_creator_id, position),
    UNIQUE (campaign_creator_id, publish_link)
);

CREATE TABLE analysis_data (
    creator_id TEXT PRIMARY KEY REFERENCES creators(creator_id) ON DELETE RESTRICT,
    task_id TEXT,
    account_uid TEXT REFERENCES creator_accounts(account_uid) ON DELETE RESTRICT,
    status_updated_at TEXT,
    analysis_json TEXT,
    source TEXT
);

CREATE INDEX idx_creators_archive_status ON creators(archived_at, status);
CREATE INDEX idx_creators_created_at ON creators(created_at);
CREATE INDEX idx_creator_accounts_creator ON creator_accounts(creator_id);
CREATE INDEX idx_creator_accounts_platform ON creator_accounts(platform);
CREATE INDEX idx_videos_creator_captured ON videos(creator_id, captured_at DESC);
CREATE INDEX idx_creator_snapshots_creator_time ON creator_snapshots(creator_id, captured_at DESC);
CREATE INDEX idx_creator_snapshots_account_time ON creator_snapshots(account_uid, captured_at DESC);
CREATE INDEX idx_video_snapshots_video_time ON video_snapshots(video_id, captured_at DESC);
CREATE INDEX idx_video_snapshots_creator_time ON video_snapshots(creator_id, captured_at DESC);
CREATE INDEX idx_campaigns_status_archive ON campaigns(status, archived_at);
CREATE INDEX idx_campaigns_created_at ON campaigns(created_at);
CREATE INDEX idx_campaign_creators_campaign ON campaign_creators(campaign_id);
CREATE INDEX idx_campaign_creators_creator ON campaign_creators(creator_id);
CREATE INDEX idx_campaign_creators_stage_archive ON campaign_creators(stage, archived_at);
CREATE INDEX idx_follow_up_object ON follow_up_logs(object_type, object_id, created_at DESC);
"""

SCHEMA_V2_COLUMNS = (
    ("quote_currency", "TEXT"),
    ("quote_unit_amount", "REAL"),
    ("quote_quantity", "INTEGER"),
    ("quote_unit", "TEXT"),
    ("cost_currency", "TEXT"),
)

SCHEMA_V3_PUBLICATION_COLUMNS = (
    ("publication_id", "TEXT"),
    ("actual_account_uid", "TEXT REFERENCES creator_accounts(account_uid) ON DELETE RESTRICT"),
    ("platform", "TEXT"),
    ("published_at", "TEXT"),
    ("observed_at", "TEXT"),
    ("video_id", "TEXT"),
    ("source", "TEXT"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _metadata_exists(connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='storage_metadata'"
    ).fetchone()
    return row is not None


def schema_version(connection) -> int:
    if not _metadata_exists(connection):
        return 0
    row = connection.execute(
        "SELECT value FROM storage_metadata WHERE key='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise SQLiteSchemaUnsupportedError("SQLite schema metadata is invalid.") from exc


def apply_schema_migrations(connection, *, migration_reference: str = "") -> int:
    current = schema_version(connection)
    if current > CURRENT_SCHEMA_VERSION:
        raise SQLiteSchemaUnsupportedError(
            "This data store was created by a newer KOLConnect version."
        )
    if current == CURRENT_SCHEMA_VERSION:
        return current
    if current == 0:
        created_at = utc_now()
        try:
            connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA_V1_SQL)
            connection.executemany(
                "INSERT INTO storage_metadata(key, value) VALUES (?, ?)",
                (
                    ("schema_version", "1"),
                    ("created_at", created_at),
                    ("migration_version", "excel-to-sqlite-v1"),
                    ("migration_reference", migration_reference),
                    ("application_compatibility", "pre-m8-c0-c3"),
                    ("business_revision", "0"),
                ),
            )
            connection.commit()
            current = 1
        except Exception:
            connection.rollback()
            raise
    if current == 1:
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(campaign_creators)")
            }
            for column, data_type in SCHEMA_V2_COLUMNS:
                if column not in existing:
                    connection.execute(
                        f"ALTER TABLE campaign_creators ADD COLUMN {column} {data_type}"
                    )
            connection.execute(
                "UPDATE storage_metadata SET value=? WHERE key='schema_version'", ("2",)
            )
            connection.execute(
                "INSERT OR REPLACE INTO storage_metadata(key, value) VALUES (?, ?)",
                ("application_compatibility", "pre-m8-item-7-multicurrency"),
            )
            connection.commit()
            current = 2
        except Exception:
            connection.rollback()
            raise
    if current == 2:
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(campaign_creator_publish_links)")
            }
            for column, data_type in SCHEMA_V3_PUBLICATION_COLUMNS:
                if column not in existing:
                    connection.execute(
                        f"ALTER TABLE campaign_creator_publish_links ADD COLUMN {column} {data_type}"
                    )
            rows = connection.execute(
                "SELECT campaign_creator_id, position, publish_link FROM campaign_creator_publish_links"
            ).fetchall()
            import hashlib
            for campaign_creator_id, position, publish_link in rows:
                identity = hashlib.sha256(
                    f"{campaign_creator_id}|{publish_link}".encode("utf-8")
                ).hexdigest()[:24]
                connection.execute(
                    "UPDATE campaign_creator_publish_links SET publication_id=?, source='legacy' "
                    "WHERE campaign_creator_id=? AND position=?",
                    (f"publication_legacy_{identity}", campaign_creator_id, position),
                )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_publication_identity "
                "ON campaign_creator_publish_links(publication_id)"
            )
            connection.execute(
                "UPDATE storage_metadata SET value=? WHERE key='schema_version'", ("3",)
            )
            connection.execute(
                "INSERT OR REPLACE INTO storage_metadata(key, value) VALUES (?, ?)",
                ("application_compatibility", "pre-m8-item-12-publications"),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return CURRENT_SCHEMA_VERSION


def validate_schema(connection) -> dict[str, object]:
    version = schema_version(connection)
    if version != CURRENT_SCHEMA_VERSION:
        raise SQLiteSchemaUnsupportedError("SQLite schema version is unsupported.")
    quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
    foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
    if quick_check != "ok" or foreign_keys:
        from storage.errors import SQLiteIntegrityError

        raise SQLiteIntegrityError("SQLite integrity validation failed.")
    table_count = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    return {
        "schema_version": version,
        "quick_check": quick_check,
        "foreign_key_issues": foreign_keys,
        "table_count": table_count,
    }
