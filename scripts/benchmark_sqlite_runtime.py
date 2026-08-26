from __future__ import annotations

"""Deterministic PRE-M8 C11 SQLite runtime benchmark (synthetic data only)."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
import gc
import json
import math
from pathlib import Path
import shutil
import statistics
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from dashboard_repository import DashboardRepository
from dashboard_service import DashboardService
from repository_factory import RepositoryFactory
from services.dashboard_response_cache import DashboardResponseCache
from storage.connection import backup_database
from storage.schema import apply_schema_migrations
from storage.sqlite_workbook_store import SQLiteWorkbookStore


@dataclass(frozen=True)
class Dimensions:
    creators: int
    accounts: int
    videos: int
    creator_snapshots: int
    video_snapshots: int
    campaigns: int
    campaign_creators: int
    products: int
    insights: int


SCALES = {
    "medium": Dimensions(2500, 3000, 5000, 5000, 25000, 100, 2500, 20, 2500),
    "large": Dimensions(10000, 15000, 20000, 20000, 100000, 400, 10000, 80, 10000),
}


def _insert_many(connection, table: str, columns: tuple[str, ...], rows) -> None:
    connection.executemany(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES "
        f"({','.join('?' for _ in columns)})",
        rows,
    )


def create_fixture(database_path: Path, dimensions: Dimensions) -> SQLiteWorkbookStore:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteWorkbookStore.initialize_empty(database_path, reference="c11-benchmark")
    with store.factory.write_transaction() as connection:
        _insert_many(connection, "creators", (
            "creator_id", "name", "platform", "profile_url", "country", "language",
            "content_category", "followers", "insight_level", "status", "created_at",
            "updated_at", "archived_at", "agency_id",
        ), (
            (
                f"creator_{index:05d}", f"Creator {index}",
                ("TikTok", "YouTube", "Instagram")[index % 3],
                f"https://creator.test/{index}",
                ("Brazil", "United States", "Japan", "Germany")[index % 4],
                ("Portuguese", "English", "Japanese")[index % 3],
                ("Gaming", "Lifestyle", "Comedy")[index % 3],
                10_000 + index, "normal", "discovered",
                f"2026-01-{(index % 28) + 1:02d}T00:00:00Z",
                "2026-08-01T00:00:00Z",
                "2026-07-01T00:00:00Z" if index % 20 == 0 else None,
                f"agency_{index % 10:02d}",
            )
            for index in range(dimensions.creators)
        ))
        extra_accounts = dimensions.accounts - dimensions.creators
        account_rows = []
        for index in range(dimensions.creators):
            count = 2 if index < extra_accounts else 1
            for position in range(count):
                platform = ("TikTok", "YouTube", "Instagram")[(index + position) % 3]
                account_rows.append((
                    f"account_{index:05d}_{position}", f"legacy_{index}_{position}",
                    f"creator_{index:05d}", platform, f"creator{index}_{position}",
                    f"https://account.test/{index}/{position}", 10_000 + index + position,
                    f"public{index}@example.test" if index % 10 == 0 else None,
                    "2026-07-31", "2026-08-01T00:00:00Z", "benchmark", "success",
                    f"platform_{index}_{position}", "confirmed", None, None,
                    "2026-01-01T00:00:00Z", "2026-08-01T00:00:00Z",
                ))
        _insert_many(connection, "creator_accounts", (
            "account_uid", "account_id", "creator_id", "platform", "username",
            "profile_url", "followers", "account_email", "latest_post_date",
            "last_scrape_time", "data_source", "scrape_status", "platform_account_id",
            "attribution_status", "note", "source_task_id", "created_at", "updated_at",
        ), account_rows)
        _insert_many(connection, "creator_tags", ("creator_id", "position", "tag"), (
            (f"creator_{index:05d}", 0, f"group-{index % 10}")
            for index in range(dimensions.creators)
        ))
        _insert_many(connection, "insights", (
            "creator_id", "average_views", "median_views", "stability", "risks", "recommendation",
        ), (
            (f"creator_{index:05d}", None if index % 17 == 0 else 5000 + index,
             None if index % 19 == 0 else 4500 + index, 0.8, "[]", "fit")
            for index in range(dimensions.insights)
        ))
        _insert_many(connection, "videos", (
            "creator_id", "video_url", "views", "likes", "comments", "captured_at",
        ), (
            (f"creator_{index % dimensions.creators:05d}", f"https://video.test/{index}",
             1000 + index, 100 + index % 500, 10 + index % 50, "2026-07-01T00:00:00Z")
            for index in range(dimensions.videos)
        ))
        _insert_many(connection, "creator_snapshots", (
            "snapshot_id", "creator_id", "platform", "account_uid", "followers",
            "average_views", "median_views", "video_count", "creator_score",
            "insight_level", "captured_at", "source",
        ), (
            (
                f"snapshot_{index:06d}", f"creator_{index % dimensions.creators:05d}",
                ("TikTok", "YouTube", "Instagram")[index % 3],
                f"account_{index % dimensions.creators:05d}_0", 10_000 + index,
                5000 + index, 4500 + index, 10, 80.0, "normal",
                f"2026-{(index % 7) + 1:02d}-{(index % 28) + 1:02d}T00:00:00Z", "benchmark",
            )
            for index in range(dimensions.creator_snapshots)
        ))
        _insert_many(connection, "video_snapshots", (
            "video_snapshot_id", "snapshot_id", "creator_id", "video_id", "video_url",
            "platform", "views", "likes", "comments", "captured_at",
        ), (
            (
                f"video_snapshot_{index:07d}",
                f"snapshot_{index % dimensions.creator_snapshots:06d}",
                f"creator_{index % dimensions.creators:05d}", f"video_{index % dimensions.videos}",
                f"https://video.test/{index % dimensions.videos}",
                ("TikTok", "YouTube", "Instagram")[index % 3], 1000 + index,
                100 + index % 500, 10 + index % 50,
                f"2026-{(index % 7) + 1:02d}-{(index % 28) + 1:02d}T00:00:00Z",
            )
            for index in range(dimensions.video_snapshots)
        ))
        _insert_many(connection, "agencies", (
            "agency_id", "name", "country", "created_at", "updated_at",
        ), ((f"agency_{index:02d}", f"Agency {index}", "Brazil", "2026-01-01", "2026-08-01") for index in range(10)))
        _insert_many(connection, "agency_contacts", (
            "contact_id", "name", "agency_id", "email", "created_at", "updated_at",
        ), ((f"contact_{index:02d}", f"Contact {index}", f"agency_{index:02d}", f"agency{index}@example.test", "2026-01-01", "2026-08-01") for index in range(10)))
        _insert_many(connection, "products", (
            "product_id", "name", "company_name", "created_at", "updated_at",
        ), ((f"product_{index:03d}", f"Product {index}", "Company", "2026-01-01", "2026-08-01") for index in range(dimensions.products)))
        _insert_many(connection, "campaigns", (
            "campaign_id", "product_id", "name", "country", "platform", "start_date",
            "end_date", "owner", "status", "budget", "created_at", "updated_at",
        ), ((f"campaign_{index:04d}", f"product_{index % dimensions.products:03d}", f"Campaign {index}", "Brazil", "TikTok", "2026-01-01", "2026-12-31", "owner", "running", 5000.0, "2026-01-01", "2026-08-01") for index in range(dimensions.campaigns)))
        _insert_many(connection, "campaign_platforms", ("campaign_id", "position", "platform"), (
            (f"campaign_{index:04d}", position, platform)
            for index in range(dimensions.campaigns)
            for position, platform in enumerate(("TikTok", "YouTube"))
        ))
        _insert_many(connection, "campaign_creators", (
            "id", "campaign_id", "creator_id", "account_id", "stage", "owner",
            "creator_quote", "cost", "publish_date", "views", "likes", "comments",
            "roi", "performance_note", "created_at", "updated_at",
        ), (
            (
                f"relation_{index:06d}", f"campaign_{index % dimensions.campaigns:04d}",
                f"creator_{index % dimensions.creators:05d}", f"account_{index % dimensions.creators:05d}_0",
                "completed" if index % 2 == 0 else "executing", "owner",
                None if index % 11 == 0 else 500.0, None if index % 13 == 0 else 450.0,
                "2026-08-15", 10_000 + index, 1000, 100, 1.5, None,
                "2026-01-01", "2026-08-01",
            )
            for index in range(dimensions.campaign_creators)
        ))
        _insert_many(connection, "campaign_creator_accounts", (
            "campaign_creator_id", "position", "account_uid",
        ), ((f"relation_{index:06d}", 0, f"account_{index % dimensions.creators:05d}_0") for index in range(dimensions.campaign_creators)))
        _insert_many(connection, "campaign_creator_planned_dates", (
            "campaign_creator_id", "position", "planned_date",
        ), ((f"relation_{index:06d}", position, date_value) for index in range(dimensions.campaign_creators) for position, date_value in enumerate(("2026-08-15", "2026-08-22"))))
        _insert_many(connection, "cooperations", (
            "cooperation_id", "creator_id", "campaign", "platform", "price", "created_at",
        ), ((f"coop_{index:05d}", f"creator_{index % dimensions.creators:05d}", "Legacy", "TikTok", 100.0, "2026-01-01") for index in range(min(dimensions.creators, 2000))))
        _insert_many(connection, "follow_up_logs", (
            "follow_up_id", "object_type", "object_id", "content", "created_at",
        ), ((f"follow_{index:05d}", "creator", f"creator_{index % dimensions.creators:05d}", "Follow up", "2026-01-01") for index in range(min(dimensions.creators, 2000))))
        _insert_many(connection, "analysis_data", (
            "creator_id", "task_id", "account_uid", "analysis_json", "source",
        ), ((f"creator_{index:05d}", f"task_{index:05d}", f"account_{index:05d}_0", "{}", "benchmark") for index in range(dimensions.creators)))
        connection.execute("INSERT OR REPLACE INTO storage_metadata(key,value) VALUES ('business_revision','0')")
    return store


def stats(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3),
        "max_ms": round(max(ordered), 3),
    }


def measure(operation, *, samples: int, warmup: int = 1) -> dict[str, float]:
    for _ in range(warmup):
        operation()
    values = []
    for _ in range(samples):
        gc.collect()
        started = time.perf_counter()
        operation()
        values.append((time.perf_counter() - started) * 1000)
    return stats(values)


def dashboard_payload(factory: RepositoryFactory) -> dict:
    service = DashboardService(factory.dashboard(factory.creator(), factory.campaign_creator(), factory.campaign()))
    return {
        "overview": service.getOverview(),
        "creator_health": service.getCreatorHealth(),
        "health_summary": service.getHealthSummary(),
        "cooperation_performance": service.getCooperationPerformance(),
        "action_items": service.getActionItems(),
        "platform_distribution": service.getPlatformDistribution(),
        "creator_status_distribution": service.getCreatorStatusDistribution(),
        "creator_growth_trend": service.getCreatorGrowthTrend(),
    }


def run_benchmark(store: SQLiteWorkbookStore, dimensions: Dimensions, *, samples: int) -> dict:
    factory = RepositoryFactory(store)
    creator = factory.creator()
    campaign = factory.campaign()
    campaign_creator = factory.campaign_creator()
    library_snapshot = creator.getCreatorLibrarySnapshot()
    cache = DashboardResponseCache(lambda: date(2026, 8, 26))
    results = {
        "creator_library_initial": measure(lambda: creator.getCreatorLibrarySnapshot(), samples=samples),
        "creator_library_pagination": measure(lambda: creator.getCreatorsPageFromSnapshot(library_snapshot, page=2, page_size=24), samples=samples),
        "creator_library_country": measure(lambda: creator.getCreatorsPageFromSnapshot(library_snapshot, filters={"country": "Brazil"}), samples=samples),
        "creator_library_platform": measure(lambda: creator.getCreatorsPageFromSnapshot(library_snapshot, filters={"platform": "TikTok"}), samples=samples),
        "creator_library_followers": measure(lambda: creator.getCreatorsPageFromSnapshot(library_snapshot, filters={"followers_min": "11000", "followers_max": "12500"}), samples=samples),
        "creator_library_combined": measure(lambda: creator.getCreatorsPageFromSnapshot(library_snapshot, include_archived=True, filters={"country": "Brazil", "platform": "TikTok", "status": "discovered"}), samples=samples),
        "creator_detail": measure(lambda: creator.getCreatorDetail("creator_00000"), samples=samples),
        "campaign_list": measure(lambda: campaign.getCampaigns(), samples=samples),
        "campaign_detail": measure(lambda: campaign.getCampaign("campaign_0000"), samples=samples),
        "campaign_members": measure(lambda: campaign_creator.getCampaignCreators(campaign_id="campaign_0000"), samples=samples),
        "creator_snapshot_history": measure(lambda: creator.getCreatorSnapshots("creator_00000"), samples=samples),
        "dashboard_cold": measure(lambda: dashboard_payload(RepositoryFactory(store)), samples=samples),
    }
    cache.get_response(store, lambda: dashboard_payload(RepositoryFactory(store)))
    results["dashboard_warm"] = measure(
        lambda: cache.get_response(store, lambda: dashboard_payload(RepositoryFactory(store))),
        samples=samples,
        warmup=0,
    )
    write_samples = max(3, min(samples, 5))
    creator_update_index = 0

    def creator_update():
        nonlocal creator_update_index
        creator_update_index += 1
        creator.updateCreator(
            "creator_00000",
            {"country": "Brazil" if creator_update_index % 2 else "Portugal"},
        )

    account_update_index = 0

    def account_update():
        nonlocal account_update_index
        account_update_index += 1
        creator.updateCreator(
            "creator_00000",
            {"followers": 10000 + (account_update_index % 2)},
        )

    campaign_update_index = 0

    def campaign_update():
        nonlocal campaign_update_index
        campaign_update_index += 1
        campaign.updateCampaign(
            "campaign_0000", {"note": f"benchmark-{campaign_update_index}"}
        )

    membership_update_index = 0

    def membership_update():
        nonlocal membership_update_index
        membership_update_index += 1
        campaign_creator.updateCampaignCreator(
            "relation_000000",
            {"performance_note": f"benchmark-{membership_update_index}"},
        )

    snapshot_index = dimensions.creator_snapshots

    def snapshot_append():
        nonlocal snapshot_index
        snapshot_index += 1
        creator.createSnapshot({
            "task_id": f"task_20260826T120000Z_{snapshot_index:08x}"[-35:],
            "account_uid": "account_00000_0",
            "imported_at": "2026-08-26T12:00:00Z",
            "source": "benchmark",
            "creator": {"platform": "TikTok", "followers": "10000"},
            "video_analysis": {"average_views": 5000, "median_views": 4500},
            "creator_insight": {"level": "normal", "creator_score": 80},
            "videos": [],
        }, "creator_00000")

    results["creator_update"] = measure(creator_update, samples=write_samples, warmup=0)
    results["account_update"] = measure(account_update, samples=write_samples, warmup=0)
    results["campaign_update"] = measure(campaign_update, samples=write_samples, warmup=0)
    results["campaign_membership_update"] = measure(membership_update, samples=write_samples, warmup=0)
    results["snapshot_append"] = measure(snapshot_append, samples=write_samples, warmup=0)

    def video_snapshot_latest():
        with store.factory.read_connection() as connection:
            return connection.execute(
                "SELECT * FROM video_snapshots WHERE video_id=? "
                "ORDER BY captured_at DESC LIMIT 1",
                ("video_0",),
            ).fetchone()

    def video_snapshot_history():
        with store.factory.read_connection() as connection:
            return connection.execute(
                "SELECT * FROM video_snapshots WHERE video_id=? "
                "ORDER BY captured_at DESC",
                ("video_0",),
            ).fetchall()

    results["video_snapshot_latest"] = measure(video_snapshot_latest, samples=samples)
    results["video_snapshot_history"] = measure(video_snapshot_history, samples=samples)
    with store.factory.read_connection() as connection:
        point_queries = {
            "creator_lookup": "SELECT * FROM creators WHERE creator_id='creator_00000'",
            "account_ownership": "SELECT * FROM creator_accounts WHERE creator_id='creator_00000'",
            "creator_snapshot_latest": "SELECT * FROM creator_snapshots WHERE creator_id='creator_00000' ORDER BY captured_at DESC LIMIT 1",
            "video_snapshot_latest": "SELECT * FROM video_snapshots WHERE video_id='video_0' ORDER BY captured_at DESC LIMIT 1",
            "campaign_membership": "SELECT * FROM campaign_creators WHERE campaign_id='campaign_0000'",
        }
        plans = {
            name: [str(row[3]) for row in connection.execute(f"EXPLAIN QUERY PLAN {query}")]
            for name, query in point_queries.items()
        }
    backup_path = store.database_path.with_name(f"{store.database_path.stem}.benchmark-backup.db")
    results["backup"] = measure(lambda: backup_database(store.database_path, backup_path), samples=max(2, min(samples, 3)), warmup=0)
    export_path = store.database_path.with_name(f"{store.database_path.stem}.benchmark-export.xlsx")
    export_started = time.perf_counter()
    store.export_workbook(export_path)
    export_ms = (time.perf_counter() - export_started) * 1000

    query_counts: dict[str, int] = {}

    def count_queries(name: str, operation) -> None:
        statements: list[str] = []
        original_connect = store.factory.connect

        def traced_connect():
            connection = original_connect()
            connection.set_trace_callback(statements.append)
            return connection

        store.factory.connect = traced_connect
        try:
            operation()
        finally:
            store.factory.connect = original_connect
        query_counts[name] = sum(
            1 for statement in statements if statement.lstrip().upper().startswith("SELECT")
        )

    count_queries("creator_library", lambda: RepositoryFactory(store).creator().getCreatorsPage(page=1, page_size=24))
    count_queries("creator_detail", lambda: RepositoryFactory(store).creator().getCreatorDetail("creator_00000"))
    count_queries("campaign_detail", lambda: RepositoryFactory(store).campaign().getCampaign("campaign_0000"))
    count_queries("dashboard", lambda: dashboard_payload(RepositoryFactory(store)))
    with ThreadPoolExecutor(max_workers=6) as executor:
        started = time.perf_counter()
        futures = [executor.submit(creator.getCreatorDetail, f"creator_{index:05d}") for index in range(20)]
        futures += [executor.submit(campaign.getCampaign, f"campaign_{index % dimensions.campaigns:04d}") for index in range(10)]
        for future in futures:
            future.result()
        concurrent_ms = (time.perf_counter() - started) * 1000
    with store.factory.read_connection() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return {
        "dimensions": asdict(dimensions),
        "operations": results,
        "query_plans": plans,
        "query_counts": query_counts,
        "database_size_bytes": store.database_path.stat().st_size,
        "wal_size_bytes": store.database_path.with_name(store.database_path.name + "-wal").stat().st_size if store.database_path.with_name(store.database_path.name + "-wal").exists() else 0,
        "concurrent_workload_ms": round(concurrent_ms, 3),
        "excel_export_ms": round(export_ms, 3),
        "excel_export_size_bytes": export_path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", choices=tuple(SCALES), required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = ROOT / ".pre_m8_batch3_benchmark" / args.scale
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    logs = root / "logs"
    logs.mkdir()
    import app_logging
    import local_storage_lock

    app_logging.get_logs_dir = lambda: logs
    local_storage_lock.get_shared_storage_lock_path = (
        lambda: root / "locks" / "shared_storage.lock"
    )
    started = time.perf_counter()
    store = create_fixture(root / "kolconnect.db", SCALES[args.scale])
    fixture_seconds = time.perf_counter() - started
    result = run_benchmark(store, SCALES[args.scale], samples=max(3, args.samples))
    result["scale"] = args.scale
    result["fixture_seconds"] = round(fixture_seconds, 3)
    output = args.output or root / "results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
