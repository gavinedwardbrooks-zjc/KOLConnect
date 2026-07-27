from __future__ import annotations

"""KOL联系助手本地服务。

职责保持简单：
1. 为桌面前端提供状态与设置接口。
2. 启动、停止并读取 scraper.py 抓取任务。
3. 保存本地配置，打开结果文件并触发飞书同步。
"""

import csv
import io
import json
import imaplib
import mail_sync as mail_sync_module
import os
import re
import smtplib
import subprocess
import task_manager
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import scraper as scraper_module
from runtime_paths import (
    get_app_data_dir,
    get_logs_dir,
    get_resource_dir,
    atomic_write_json,
    json_backup_path,
    load_json_with_backup,
    scraper_worker_command,
)


APP_DIR = get_resource_dir()
DATA_DIR = get_app_data_dir()
LOGS_DIR = get_logs_dir()
STATIC_DIR = APP_DIR / "webapp"
STATE_FILE = DATA_DIR / "settings.json"
TASKS_DIR = DATA_DIR / "tasks"
DATA_PROTECTION_FILE = DATA_DIR / "data_protection.json"
RUN_LOG_FILE = LOGS_DIR / "kolconnect.log"
HOST = "127.0.0.1"
PORT = 8765
SENSITIVE_MASK = "********"
TASK_HEARTBEAT_SECONDS = 60
TASK_INTERRUPTION_TIMEOUT_SECONDS = 15 * 60

REVIEW_FIELD_WHATSAPP = "WhatsApp"
REVIEW_FIELD_NOTE = "备注"
REVIEW_FIELD_DATA_STATUS = "数据状态"
REVIEW_FIELD_MODIFIED_AT = "最后修改时间"
REVIEW_CSV_FIELDS = [
    REVIEW_FIELD_WHATSAPP,
    REVIEW_FIELD_NOTE,
    REVIEW_FIELD_DATA_STATUS,
    REVIEW_FIELD_MODIFIED_AT,
]
REVIEW_EDITABLE_FIELDS = {
    scraper_module.FIELD_NAME,
    scraper_module.FIELD_EMAIL,
    scraper_module.FIELD_FOLLOWER_COUNT,
    REVIEW_FIELD_WHATSAPP,
    REVIEW_FIELD_NOTE,
}
REVIEW_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
REVIEW_WHATSAPP_PATTERN = re.compile(r"^[0-9+()\- ]+$")
TASK_PLATFORM_OPTIONS = {"全部", "TikTok", "Instagram", "YouTube"}
AGENCY_CONTACT_FIELD_NAME = "联系人姓名"
AGENCY_CONTACT_FIELD_WHATSAPP = "WhatsApp"
AGENCY_CONTACT_FIELD_AGENCY = "所属 Agency"
PROTECTED_DATA_FIELDS = {
    scraper_module.FIELD_EMAIL,
    scraper_module.FIELD_NAME,
    scraper_module.FIELD_FOLLOWER_COUNT,
    REVIEW_FIELD_WHATSAPP,
    REVIEW_FIELD_NOTE,
}
DATA_PROTECTION_PRIORITY = {
    "人工维护": 50,
    "人工录入": 40,
    "审核修改": 30,
    "系统补全": 20,
    "邮箱补全": 20,
    "人工+系统补充": 20,
    "人工补充": 20,
    "系统抓取": 10,
}

CHROME_USER_DATA = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
KOLCONNECT_CHROME_USER_DATA = DATA_DIR / "ChromeProfile"
AUTOMATION_PROFILE_NAME = "KOLConnect Automation"
AUTOMATION_PROFILE_DIRECTORY = "Default"
CHROME_EXE_CANDIDATES = [
    Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
]

DEFAULT_STATE = {
    "ui": {"language": "zh"},
    "profiles": {"selected": AUTOMATION_PROFILE_NAME},
    "accounts": {"entries": []},
    "feishu": {
        "app_id": "",
        "app_secret": "",
        "app_token": "",
        "creator_table_id": "",
        "account_table_id": "",
        "agency_table_id": "",
        "contact_table_id": "",
    },
    "mail": {
        "accounts": [],
        "template_subject": "",
        "template_body": "",
    },
}

MAIL_PROVIDER_PRESETS = {
    "gmail": {
        "imap_host": "imap.gmail.com",
        "imap_port": "993",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": "587",
    },
    "netease": {
        "imap_host": "imap.163.com",
        "imap_port": "993",
        "smtp_host": "smtp.163.com",
        "smtp_port": "465",
    },
}


def get_mail_provider_preset(provider: str) -> dict[str, str]:
    return MAIL_PROVIDER_PRESETS.get(provider, {})


def normalize_mail_account(raw: dict | None) -> dict:
    raw = raw or {}
    provider = str(raw.get("provider") or "custom").strip().lower() or "custom"
    preset = get_mail_provider_preset(provider)
    return {
        "name": str(raw.get("name") or "").strip(),
        "provider": provider if provider in {"aliyun", "netease", "gmail", "custom"} else "custom",
        "email": str(raw.get("email") or "").strip(),
        "sender_name": str(raw.get("sender_name") or "").strip(),
        "imap_host": str(raw.get("imap_host") or preset.get("imap_host") or "").strip(),
        "imap_port": str(raw.get("imap_port") or preset.get("imap_port") or "").strip(),
        "smtp_host": str(raw.get("smtp_host") or preset.get("smtp_host") or "").strip(),
        "smtp_port": str(raw.get("smtp_port") or preset.get("smtp_port") or "").strip(),
        "username": str(raw.get("username") or "").strip(),
        "password": str(raw.get("password") or ""),
        "enabled": bool(raw.get("enabled")),
    }


def normalize_mail_state(raw_mail: dict | None) -> dict:
    raw_mail = raw_mail or {}
    if isinstance(raw_mail.get("accounts"), list):
        return {
            "accounts": [
                normalize_mail_account(item)
                for item in raw_mail["accounts"]
                if isinstance(item, dict) and str(item.get("name") or item.get("email") or item.get("username") or "").strip()
            ],
            "template_subject": str(raw_mail.get("template_subject") or ""),
            "template_body": str(raw_mail.get("template_body") or ""),
        }
    return clone_default_state()["mail"]


def is_sensitive_mask(value: object) -> bool:
    return str(value or "").strip() == SENSITIVE_MASK


def mail_account_identity(account: dict) -> tuple[str, str, str]:
    """Use stable account values to retain a masked password during saves."""
    return (
        str(account.get("email") or "").strip().lower(),
        str(account.get("username") or "").strip().lower(),
        str(account.get("name") or "").strip().lower(),
    )


def merge_masked_mail_passwords(raw_mail: dict | None, existing_mail: dict | None) -> dict:
    """Replace API mask placeholders with the already saved account password."""
    merged = dict(raw_mail) if isinstance(raw_mail, dict) else {}
    raw_accounts = merged.get("accounts")
    if not isinstance(raw_accounts, list):
        return merged

    existing_accounts = existing_mail.get("accounts") if isinstance(existing_mail, dict) else []
    existing_by_identity = {
        mail_account_identity(account): account
        for account in existing_accounts
        if isinstance(account, dict) and any(mail_account_identity(account))
    }
    merged_accounts = []
    for raw_account in raw_accounts:
        if not isinstance(raw_account, dict):
            continue
        account = dict(raw_account)
        if is_sensitive_mask(account.get("password")):
            saved_account = existing_by_identity.get(mail_account_identity(account))
            account["password"] = str(saved_account.get("password") or "") if saved_account else ""
        merged_accounts.append(account)
    merged["accounts"] = merged_accounts
    return merged


def state_for_client(state: dict) -> dict:
    """Return settings needed by the UI without exposing saved secrets."""
    client_state = json.loads(json.dumps(state))
    feishu = client_state.get("feishu") if isinstance(client_state.get("feishu"), dict) else {}
    if feishu.get("app_secret"):
        feishu["app_secret"] = SENSITIVE_MASK
    if feishu.get("app_token"):
        feishu["app_token"] = SENSITIVE_MASK
    mail = client_state.get("mail") if isinstance(client_state.get("mail"), dict) else {}
    accounts = mail.get("accounts") if isinstance(mail.get("accounts"), list) else []
    for account in accounts:
        if isinstance(account, dict) and account.get("password"):
            account["password"] = SENSITIVE_MASK
    return client_state


def parse_port(value: str, default: int) -> int:
    try:
        port = int(str(value or "").strip())
        return port if port > 0 else default
    except Exception:
        return default


def test_imap_login(account: dict) -> None:
    host = str(account.get("imap_host") or "").strip()
    username = str(account.get("username") or "").strip()
    password = str(account.get("password") or "")
    port = parse_port(account.get("imap_port") or "", 993)
    if not host or not username or not password:
        raise RuntimeError("请完整填写 IMAP Host、IMAP Port、用户名和密码/授权码。")
    client = None
    try:
        if port == 993:
            client = imaplib.IMAP4_SSL(host, port, timeout=10)
        else:
            client = imaplib.IMAP4(host, port, timeout=10)
            if hasattr(client, "starttls"):
                client.starttls()
        client.login(username, password)
    except Exception as exc:
        raise RuntimeError(f"IMAP 登录失败：{exc}") from exc
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def test_smtp_login(account: dict) -> None:
    host = str(account.get("smtp_host") or "").strip()
    username = str(account.get("username") or "").strip()
    password = str(account.get("password") or "")
    port = parse_port(account.get("smtp_port") or "", 587)
    if not host or not username or not password:
        raise RuntimeError("请完整填写 SMTP Host、SMTP Port、用户名和密码/授权码。")
    client = None
    try:
        if port == 465:
            client = smtplib.SMTP_SSL(host, port, timeout=10)
            client.ehlo()
        else:
            client = smtplib.SMTP(host, port, timeout=10)
            client.ehlo()
            if client.has_extn("starttls"):
                client.starttls()
                client.ehlo()
        client.login(username, password)
    except Exception as exc:
        raise RuntimeError(f"SMTP 登录失败：{exc}") from exc
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass

def clone_default_state() -> dict:
    return json.loads(json.dumps(DEFAULT_STATE))


def get_profiles() -> list[str]:
    profiles: list[str] = [AUTOMATION_PROFILE_NAME]
    if not CHROME_USER_DATA.exists():
        return profiles + ["Default"]

    for child in CHROME_USER_DATA.iterdir():
        if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile ")):
            profiles.append(child.name)
    chrome_profiles = sorted({name for name in profiles if name != AUTOMATION_PROFILE_NAME}, key=lambda name: (name != "Default", name))
    return [AUTOMATION_PROFILE_NAME, *chrome_profiles] or [AUTOMATION_PROFILE_NAME, "Default"]


def resolve_chrome_launch_config(profile: str | None) -> tuple[Path, str]:
    selected = (profile or "").strip() or AUTOMATION_PROFILE_NAME
    if selected == AUTOMATION_PROFILE_NAME:
        KOLCONNECT_CHROME_USER_DATA.mkdir(parents=True, exist_ok=True)
        return KOLCONNECT_CHROME_USER_DATA, AUTOMATION_PROFILE_DIRECTORY
    return CHROME_USER_DATA, selected


def normalize_state(raw: dict | None) -> dict:
    """Normalize persisted application state into the current structure."""
    state = clone_default_state()
    raw = raw or {}

    if isinstance(raw.get("ui"), dict):
        state["ui"].update(raw["ui"])
    if state["ui"].get("language") not in {"zh", "en"}:
        state["ui"]["language"] = "zh"

    if isinstance(raw.get("profiles"), dict):
        state["profiles"].update(raw["profiles"])
    if not state["profiles"].get("selected"):
        state["profiles"]["selected"] = AUTOMATION_PROFILE_NAME
    elif state["profiles"]["selected"] == "Default":
        state["profiles"]["selected"] = AUTOMATION_PROFILE_NAME

    if isinstance(raw.get("accounts"), dict) and isinstance(raw["accounts"].get("entries"), list):
        state["accounts"]["entries"] = [
            {
                "profile": str(item.get("profile") or "").strip(),
                "alias": str(item.get("alias") or "").strip(),
                "usage": str(item.get("usage") or "通用").strip() or "通用",
            }
            for item in raw["accounts"]["entries"]
            if isinstance(item, dict) and str(item.get("profile") or "").strip()
        ]

    if isinstance(raw.get("feishu"), dict):
        feishu = raw["feishu"]
        state["feishu"]["app_id"] = str(feishu.get("app_id") or "").strip()
        state["feishu"]["app_secret"] = str(feishu.get("app_secret") or "").strip()
        for key in (
            "app_token",
            "creator_table_id",
            "account_table_id",
            "agency_table_id",
            "contact_table_id",
        ):
            state["feishu"][key] = str(feishu.get(key) or "").strip()

    if isinstance(raw.get("mail"), dict):
        state["mail"] = normalize_mail_state(raw["mail"])

    return state


def load_state() -> dict:
    data, source_path = load_json_with_backup(STATE_FILE)
    if data is None:
        if STATE_FILE.exists() or json_backup_path(STATE_FILE).exists():
            RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with RUN_LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write("设置文件损坏且无法恢复，已使用默认配置。\n")
        return normalize_state(None)
    if source_path == json_backup_path(STATE_FILE):
        RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with RUN_LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write("设置文件损坏，已从 settings.json.bak 恢复。\n")
    return normalize_state(data if isinstance(data, dict) else None)


def save_state(state: dict) -> None:
    atomic_write_json(STATE_FILE, state)


STATE = load_state()


def find_chrome_exe() -> Path | None:
    for candidate in CHROME_EXE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def open_chrome_profile(profile: str) -> None:
    chrome_exe = find_chrome_exe()
    if not chrome_exe:
        raise RuntimeError("未找到 Chrome，请先安装 Google Chrome。")
    user_data_dir, profile_directory = resolve_chrome_launch_config(profile)
    subprocess.Popen(
        [
            str(chrome_exe),
            f"--user-data-dir={user_data_dir}",
            f"--profile-directory={profile_directory}",
        ],
        cwd=str(DATA_DIR),
    )


def get_four_table_feishu_config() -> dict:
    """Return named four-table settings without falling back to a legacy table."""
    return {
        "app_id": STATE["feishu"].get("app_id", ""),
        "app_secret": STATE["feishu"].get("app_secret", ""),
        "app_token": STATE["feishu"].get("app_token", ""),
        "creator_table_id": STATE["feishu"].get("creator_table_id", ""),
        "account_table_id": STATE["feishu"].get("account_table_id", ""),
        "agency_table_id": STATE["feishu"].get("agency_table_id", ""),
        "contact_table_id": STATE["feishu"].get("contact_table_id", ""),
    }


def _feishu_relation_labels(value) -> list[str]:
    """Read relation display text without using it as an identifier."""
    items = value if isinstance(value, list) else [value]
    labels: list[str] = []
    for item in items:
        if isinstance(item, dict):
            label = str(item.get("text") or item.get("name") or "").strip()
        else:
            label = str(item or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def get_agency_contact_options() -> dict:
    """Read contact choices for manual tasks; no records are changed here."""
    config = get_four_table_feishu_config()
    contact_table_id = str(config.get("contact_table_id") or "").strip()
    if not contact_table_id:
        return {"configured": False, "contacts": []}

    required = ("app_id", "app_secret", "app_token", "contact_table_id")
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"Agency联系人表飞书配置不完整：缺少 {', '.join(missing)}。")

    access_token = scraper_module._four_table_access_token(config)
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    contacts: list[dict] = []
    for item in scraper_module._four_table_list_records(contact_table_id, config, headers):
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        record_id = str(item.get("record_id") or "").strip()
        if not record_id:
            continue
        contacts.append(
            {
                "record_id": record_id,
                "name": str(fields.get(AGENCY_CONTACT_FIELD_NAME) or "").strip(),
                "whatsapp": str(fields.get(AGENCY_CONTACT_FIELD_WHATSAPP) or "").strip(),
                "agencies": _feishu_relation_labels(fields.get(AGENCY_CONTACT_FIELD_AGENCY)),
            }
        )
    contacts.sort(key=lambda item: (not bool(item["name"]), item["name"].casefold(), item["record_id"]))
    return {"configured": True, "contacts": contacts}


def _resolve_source_contact(source_contact_record_id: object) -> dict | None:
    """Validate a selected contact by stable Feishu record ID before saving a manual task."""
    record_id = str(source_contact_record_id or "").strip()
    if not record_id:
        return None
    options = get_agency_contact_options()
    if not options["configured"]:
        raise ValueError("未配置 Agency联系人表，无法选择来源联系人。")
    for contact in options["contacts"]:
        if contact["record_id"] == record_id:
            return contact
    raise ValueError("来源联系人不存在或已被删除，请重新选择。")


@dataclass
class ScrapeJob:
    running: bool = False
    process: subprocess.Popen[str] | None = None
    logs: list[str] = field(default_factory=list)
    task_id: str = ""
    results_file: Path | None = None
    pause_requested: bool = False
    stop_requested: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, text: str) -> None:
        with self.lock:
            self.logs.append(text)
            self.logs = self.logs[-1000:]
            with RUN_LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(text)

    def snapshot(self) -> dict:
        with self.lock:
            status = "idle"
            if self.running:
                status = "stopping" if self.stop_requested else "paused" if self.pause_requested else "running"
            return {
                "running": self.running,
                "status": status,
                "pause_requested": self.pause_requested,
                "stop_requested": self.stop_requested,
                "logs": "".join(self.logs),
                "has_results": bool(self.results_file and self.results_file.exists()),
                "task_id": self.task_id,
            }


SCRAPE_JOB = ScrapeJob()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _task_timestamp_is_stale(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return True
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds() > TASK_INTERRUPTION_TIMEOUT_SECONDS


def detect_interrupted_tasks() -> int:
    """Mark stale running tasks left behind by a closed or crashed application."""
    interrupted = 0
    reason = "任务心跳超时，可能由于程序关闭、电脑异常退出或进程异常结束"
    for task in task_manager.list_tasks(TASKS_DIR):
        if str(task.get("status") or "") != "running":
            continue
        heartbeat = task.get("heartbeat_time") or task.get("started_at")
        if not _task_timestamp_is_stale(heartbeat):
            continue
        task_manager.update_task(
            TASKS_DIR,
            str(task["id"]),
            status="interrupted",
            pause_requested=False,
            stop_requested=False,
            interrupted_time=_utc_now(),
            interrupted_reason=reason,
        )
        interrupted += 1
    if interrupted:
        SCRAPE_JOB.append(f"检测到任务异常中断：{interrupted} 个。\n")
    SCRAPE_JOB.append("任务状态检查完成。\n")
    return interrupted


def _task_next_pending_item(task_paths: dict[str, Path]) -> str:
    try:
        links = [line.strip() for line in task_paths["links"].read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return ""
    completed = set(scraper_module.load_progress(str(task_paths["progress"])))
    return next((url for url in links if url not in completed), "")


def _monitor_scrape_task(task_id: str, task_paths: dict[str, Path], stop_event: threading.Event) -> None:
    """Update task liveness and progress without touching scraper output files."""
    last_completed = len(scraper_module.load_progress(str(task_paths["progress"])))
    last_heartbeat = time.monotonic()
    while not stop_event.wait(2):
        if not SCRAPE_JOB.running or SCRAPE_JOB.task_id != task_id:
            return
        try:
            task, _ = task_manager.load_task(TASKS_DIR, task_id)
            changes: dict[str, object] = {}
            completed = len(scraper_module.load_progress(str(task_paths["progress"])))
            if completed > last_completed:
                changes["last_progress_time"] = _utc_now()
                changes["current_item"] = _task_next_pending_item(task_paths)
                last_completed = completed
            if str(task.get("status") or "") in {"running", "stopping"} and time.monotonic() - last_heartbeat >= TASK_HEARTBEAT_SECONDS:
                changes["heartbeat_time"] = _utc_now()
                last_heartbeat = time.monotonic()
                SCRAPE_JOB.append("任务心跳更新。\n")
            if changes:
                task_manager.update_task(TASKS_DIR, task_id, **changes)
        except Exception as exc:
            SCRAPE_JOB.append(f"任务监控更新失败：{exc}\n")


detect_interrupted_tasks()


def build_accounts_payload() -> list[dict]:
    """构造账号管理页面使用的 Chrome Profile 列表。"""
    profile_names = get_profiles()
    by_profile = {item["profile"]: item for item in STATE["accounts"]["entries"]}
    rows: list[dict] = []
    for profile in profile_names:
        saved = by_profile.get(profile, {})
        rows.append(
            {
                "profile": profile,
                "alias": saved.get("alias", ""),
                "usage": saved.get("usage", "通用"),
                "is_default": profile == STATE["profiles"].get("selected"),
            }
        )
    return rows


def start_scrape(payload: dict) -> dict:
    if SCRAPE_JOB.running:
        raise RuntimeError("已有任务正在运行。")

    task_id = str(payload.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError("请选择任务。")
    _task, task_paths = task_manager.load_task(TASKS_DIR, task_id)
    links_file = str(task_paths["links"])
    progress_file = str(task_paths["progress"])
    output_file = str(task_paths["results"])

    profile = (payload.get("profile") or "").strip() or STATE["profiles"].get("selected", AUTOMATION_PROFILE_NAME)
    chrome_user_data_dir, chrome_profile_directory = resolve_chrome_launch_config(profile)

    command = [
        *scraper_worker_command(),
        "--file",
        links_file,
        "--progress-file",
        progress_file,
        "--output",
        output_file,
        "--task-file",
        str(task_paths["metadata"]),
        "--chrome-dir",
        str(chrome_user_data_dir),
        "--chrome-profile",
        chrome_profile_directory,
    ]
    command.append("--no-feishu")
    startup_logs: list[str] = ["同步模式：手动四表同步\n"]

    STATE["profiles"]["selected"] = profile
    save_state(STATE)
    task_manager.update_task(
        TASKS_DIR,
        task_id,
        status="running",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        finished_at="",
        profile=profile,
        feishu_enabled=False,
        last_error="",
        sync_status="not_requested",
        sync_summary={},
        sync_errors=[],
        pause_requested=False,
        stop_requested=False,
        heartbeat_time=_utc_now(),
        last_progress_time="",
        current_item=_task_next_pending_item(task_paths),
        interrupted_time="",
        interrupted_reason="",
    )

    SCRAPE_JOB.logs = startup_logs
    SCRAPE_JOB.running = True
    SCRAPE_JOB.task_id = task_id
    SCRAPE_JOB.results_file = Path(output_file)
    SCRAPE_JOB.pause_requested = False
    SCRAPE_JOB.stop_requested = False
    SCRAPE_JOB.append("任务心跳已启动。\n")

    def worker() -> None:
        return_code: int | None = None
        error_message = ""
        monitor_stop_event = threading.Event()
        monitor_thread: threading.Thread | None = None
        try:
            SCRAPE_JOB.process = subprocess.Popen(
                command,
                cwd=str(DATA_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            monitor_thread = threading.Thread(
                target=_monitor_scrape_task,
                args=(task_id, task_paths, monitor_stop_event),
                daemon=True,
            )
            monitor_thread.start()
            assert SCRAPE_JOB.process.stdout is not None
            for line in SCRAPE_JOB.process.stdout:
                SCRAPE_JOB.append(line)
            return_code = SCRAPE_JOB.process.wait()
        except Exception as exc:
            error_message = str(exc)
            SCRAPE_JOB.append(f"\n启动抓取失败：{exc}\n")
        finally:
            monitor_stop_event.set()
            if monitor_thread:
                monitor_thread.join(timeout=3)
            try:
                completed_count = len(scraper_module.load_progress(str(task_paths["progress"])))
                sync_summary: dict = {}
                sync_errors: list[str] = []
                final_task, _ = task_manager.load_task(TASKS_DIR, task_id)
                stop_requested = bool(final_task.get("stop_requested")) or SCRAPE_JOB.stop_requested
                if stop_requested:
                    status = "stopped"
                    sync_status = "not_started"
                elif return_code == 0:
                    status = "completed"
                    sync_status = "not_requested"
                else:
                    status = "failed"
                    sync_status = "not_started"
                last_error = error_message or ("" if return_code == 0 else f"抓取进程退出码：{return_code}")
                task_manager.update_task(
                    TASKS_DIR,
                    task_id,
                    status=status,
                    finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    completed_count=completed_count,
                    last_error=last_error,
                    sync_status=sync_status,
                    sync_summary=sync_summary,
                    sync_errors=sync_errors,
                    pause_requested=False,
                    stop_requested=False,
                    heartbeat_time=_utc_now(),
                    current_item="",
                    has_system_supplement=True if _task.get("task_type") == "manual" and return_code == 0 else _task.get("has_system_supplement", False),
                )
                SCRAPE_JOB.pause_requested = False
                SCRAPE_JOB.stop_requested = False
                if status == "completed":
                    SCRAPE_JOB.append("任务完成。\n")
            except Exception as task_error:
                SCRAPE_JOB.append(f"\n任务状态保存失败：{task_error}\n")
            SCRAPE_JOB.running = False

    threading.Thread(target=worker, daemon=True).start()
    return {"task_id": task_id}


def _active_scrape_task() -> str:
    if not SCRAPE_JOB.running or not SCRAPE_JOB.task_id:
        raise RuntimeError("当前没有正在运行的抓取任务。")
    return SCRAPE_JOB.task_id


def pause_scrape() -> dict:
    task_id = _active_scrape_task()
    if SCRAPE_JOB.stop_requested:
        raise RuntimeError("任务正在停止，不能暂停。")
    if not SCRAPE_JOB.pause_requested:
        SCRAPE_JOB.pause_requested = True
        task_manager.update_task(TASKS_DIR, task_id, status="paused", pause_requested=True)
        SCRAPE_JOB.append("任务已暂停，等待继续。\n")
    return {"task_id": task_id, "status": "paused"}


def resume_scrape() -> dict:
    task_id = _active_scrape_task()
    if SCRAPE_JOB.stop_requested:
        raise RuntimeError("任务正在停止，不能继续。")
    if SCRAPE_JOB.pause_requested:
        SCRAPE_JOB.pause_requested = False
        task_manager.update_task(TASKS_DIR, task_id, status="running", pause_requested=False)
        SCRAPE_JOB.append("任务恢复运行。\n")
    return {"task_id": task_id, "status": "running"}


def request_stop_scrape() -> dict:
    task_id = _active_scrape_task()
    if not SCRAPE_JOB.stop_requested:
        SCRAPE_JOB.stop_requested = True
        SCRAPE_JOB.pause_requested = False
        task_manager.update_task(
            TASKS_DIR,
            task_id,
            status="stopping",
            pause_requested=False,
            stop_requested=True,
        )
        SCRAPE_JOB.append("收到停止请求，正在保存当前进度。\n")
    return {"task_id": task_id, "status": "stopping"}


def _read_task_csv(path: Path) -> tuple[list[str], list[dict]]:
    if not path.exists():
        raise ValueError(f"未找到任务文件：{path.name}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"任务文件格式无效：{path.name}")
        return list(reader.fieldnames), [dict(row) for row in reader]


def _review_value(row: dict, field: str) -> str:
    if field == REVIEW_FIELD_DATA_STATUS:
        return str(row.get(field) or "待检查")
    return str(row.get(field) or "")


def _account_uid_for_row(row: dict) -> str:
    return scraper_module.build_creator_uid(scraper_module.row_to_result(row))


def _review_record(row: dict) -> dict:
    return {
        "account_uid": _account_uid_for_row(row),
        scraper_module.FIELD_NAME: str(row.get(scraper_module.FIELD_NAME) or ""),
        scraper_module.FIELD_PLATFORM: str(row.get(scraper_module.FIELD_PLATFORM) or ""),
        scraper_module.FIELD_URL: str(row.get(scraper_module.FIELD_URL) or ""),
        scraper_module.FIELD_EMAIL: str(row.get(scraper_module.FIELD_EMAIL) or ""),
        scraper_module.FIELD_EMAIL_SOURCE: str(row.get(scraper_module.FIELD_EMAIL_SOURCE) or ""),
        scraper_module.FIELD_EXTERNAL_LINK: str(row.get(scraper_module.FIELD_EXTERNAL_LINK) or ""),
        scraper_module.FIELD_EXTERNAL_SOURCE: str(row.get(scraper_module.FIELD_EXTERNAL_SOURCE) or ""),
        scraper_module.FIELD_LATEST_DATE: str(row.get(scraper_module.FIELD_LATEST_DATE) or ""),
        scraper_module.FIELD_FOLLOWER_COUNT: str(row.get(scraper_module.FIELD_FOLLOWER_COUNT) or ""),
        scraper_module.FIELD_STATUS: str(row.get(scraper_module.FIELD_STATUS) or ""),
        REVIEW_FIELD_WHATSAPP: _review_value(row, REVIEW_FIELD_WHATSAPP),
        REVIEW_FIELD_NOTE: _review_value(row, REVIEW_FIELD_NOTE),
        REVIEW_FIELD_DATA_STATUS: _review_value(row, REVIEW_FIELD_DATA_STATUS),
        REVIEW_FIELD_MODIFIED_AT: _review_value(row, REVIEW_FIELD_MODIFIED_AT),
    }


def get_task_review_results(task_id: str) -> dict:
    _task, paths = task_manager.load_task(TASKS_DIR, task_id)
    if not paths["results"].exists():
        return {"task_id": task_id, "records": []}
    _fieldnames, rows = _read_task_csv(paths["results"])
    return {"task_id": task_id, "records": [_review_record(row) for row in rows]}


def _task_progress(task_id: str, fallback_total: int = 0) -> dict:
    """Calculate task-local progress from its own input and latest progress rows."""
    try:
        _task, paths = task_manager.load_task(TASKS_DIR, task_id)
    except ValueError:
        return {"total_links": fallback_total, "completed_links": 0, "failed_links": 0, "pending_links": fallback_total, "progress": 0}

    try:
        links = [line.strip() for line in paths["links"].read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        links = []
    total_links = len(links) or fallback_total
    task_urls = set(links)
    latest_status_by_url: dict[str, str] = {}
    if paths["progress"].exists():
        try:
            with paths["progress"].open(encoding="utf-8-sig", newline="", errors="ignore") as handle:
                for row in csv.DictReader(handle):
                    url = str(row.get(scraper_module.FIELD_URL) or "").strip()
                    if url and (not task_urls or url in task_urls):
                        latest_status_by_url[url] = str(row.get(scraper_module.FIELD_STATUS) or "").strip()
        except OSError:
            pass

    completed = sum(1 for status in latest_status_by_url.values() if status == "完成")
    failed = sum(1 for status in latest_status_by_url.values() if status == "失败")
    completed = min(completed, total_links)
    failed = min(failed, max(0, total_links - completed))
    pending = max(0, total_links - completed - failed)
    progress = round(((completed + failed) / total_links) * 100, 1) if total_links else 0
    return {
        "total_links": total_links,
        "completed_links": completed,
        "failed_links": failed,
        "pending_links": pending,
        "progress": progress,
    }


def get_task_list() -> dict:
    items: list[dict] = []
    for task in task_manager.list_tasks(TASKS_DIR):
        task_id = str(task.get("id") or "")
        progress = _task_progress(task_id, int(task.get("valid_count") or 0))
        task_type = str(task.get("task_type") or "scrape")
        item = {
                "id": task_id,
                "name": str(task.get("name") or "未命名任务"),
                "task_type": task_type if task_type in {"manual", "email_recheck"} else "scrape",
                "target_platform": str(task.get("target_platform") or "全部"),
                "status": str(task.get("status") or "created"),
                "heartbeat_time": str(task.get("heartbeat_time") or ""),
                "last_progress_time": str(task.get("last_progress_time") or ""),
                "current_item": str(task.get("current_item") or ""),
                "interrupted_time": str(task.get("interrupted_time") or ""),
                "interrupted_reason": str(task.get("interrupted_reason") or ""),
                "created_at": str(task.get("created_at") or ""),
                "platform_summary": task.get("platform_summary") if isinstance(task.get("platform_summary"), dict) else {},
                "filtered_count": int(task.get("filtered_count") or 0),
                **progress,
            }
        if task_type == "email_recheck":
            item.update(_email_recheck_summary(task_id))
        items.append(item)
    return {"tasks": items}


def rename_task(task_id: str, name: str) -> dict:
    name = str(name or "").strip()
    if not name:
        raise ValueError("任务名称不能为空。")
    if len(name) > 100:
        raise ValueError("任务名称不能超过100个字符。")
    return task_manager.update_task(TASKS_DIR, task_id, name=name)


def delete_local_task(task_id: str) -> dict:
    if SCRAPE_JOB.running and SCRAPE_JOB.task_id == task_id:
        raise RuntimeError("任务正在运行，不能删除。")
    task_manager.delete_task(TASKS_DIR, task_id)
    return {"task_id": task_id, "deleted": True}


def prepare_task_links(raw_links: list[str], target_platform: str) -> dict:
    """Normalize once, then keep only links selected for this local task."""
    target_platform = str(target_platform or "全部").strip() or "全部"
    if target_platform not in TASK_PLATFORM_OPTIONS:
        raise ValueError("目标平台无效。")

    platform_summary = {"TikTok": 0, "Instagram": 0, "YouTube": 0}
    selected_links: list[str] = []
    filtered_links: list[dict] = []
    invalid_links: list[str] = []
    seen_links: set[str] = set()
    seen_invalid: set[str] = set()

    for raw_link in raw_links:
        record = scraper_module.normalize_link_record(raw_link)
        if not record.get("valid"):
            value = str(record.get("input") or "").strip()
            if value and value not in seen_invalid:
                seen_invalid.add(value)
                invalid_links.append(value)
            continue

        normalized_url = str(record.get("normalized_url") or "").strip()
        platform = {
            "tiktok": "TikTok",
            "instagram": "Instagram",
            "youtube": "YouTube",
        }.get(str(record.get("platform") or "").strip().lower(), "")
        if not normalized_url or platform not in platform_summary or normalized_url in seen_links:
            continue
        seen_links.add(normalized_url)
        platform_summary[platform] += 1
        if target_platform == "全部" or platform == target_platform:
            selected_links.append(normalized_url)
        else:
            filtered_links.append(
                {
                    "url": normalized_url,
                    "platform": platform,
                    "reason": "非目标平台",
                }
            )

    return {
        "target_platform": target_platform,
        "platform_summary": platform_summary,
        "normalized_links": selected_links,
        "filtered_links": filtered_links,
        "invalid_links": invalid_links,
    }


def _feishu_link_value(value) -> str:
    """Read the URL field returned by Feishu without guessing a profile URL."""
    if isinstance(value, dict):
        return str(value.get("link") or value.get("url") or value.get("text") or "").strip()
    if isinstance(value, list):
        for item in value:
            link = _feishu_link_value(item)
            if link:
                return link
        return ""
    return str(value or "").strip()


def _account_email_is_empty(value) -> bool:
    return not str(value or "").strip() or str(value or "").strip() == scraper_module.NO_EMAIL


def load_data_protection() -> dict:
    data, _source = load_json_with_backup(DATA_PROTECTION_FILE)
    if not isinstance(data, dict):
        return {}
    return {
        str(account_uid): fields
        for account_uid, fields in data.items()
        if isinstance(fields, dict) and str(account_uid).strip()
    }


def _save_data_protection(data: dict) -> None:
    atomic_write_json(DATA_PROTECTION_FILE, data)


def _merge_data_protection(
    protection: dict, account_uid: str, values: dict[str, str], source: str, task_id: str, updated_at: str
) -> bool:
    if not account_uid:
        return False
    changed = False
    account_fields = protection.setdefault(account_uid, {})
    incoming_priority = DATA_PROTECTION_PRIORITY.get(source, 0)
    for field, value in values.items():
        if field not in PROTECTED_DATA_FIELDS or not str(value or "").strip():
            continue
        current = account_fields.get(field)
        current_priority = DATA_PROTECTION_PRIORITY.get(str((current or {}).get("source") or ""), 0)
        if isinstance(current, dict) and str(current.get("value") or "").strip() and current_priority > incoming_priority:
            continue
        account_fields[field] = {
            "value": str(value),
            "source": source,
            "task_id": task_id,
            "updated_at": updated_at,
        }
        changed = True
    return changed


def _task_email_source(task: dict) -> str:
    task_type = str(task.get("task_type") or "scrape")
    if task_type == "email_recheck":
        return "邮箱补全"
    if task_type == "manual":
        return "人工+系统补充" if task.get("has_system_supplement") else "人工录入"
    return "系统抓取"


def _email_recheck_summary(task_id: str) -> dict:
    try:
        _task, paths = task_manager.load_task(TASKS_DIR, task_id)
        if not paths["results"].exists():
            return {"email_found_count": 0, "email_failed_count": 0}
        _fieldnames, rows = _read_task_csv(paths["results"])
    except (OSError, ValueError):
        return {"email_found_count": 0, "email_failed_count": 0}
    found = sum(
        1
        for row in rows
        if not _account_email_is_empty(row.get(scraper_module.FIELD_EMAIL))
    )
    return {"email_found_count": found, "email_failed_count": max(0, len(rows) - found)}


def create_email_recheck_task() -> dict:
    """Create a task only for existing account-table records with no email."""
    config = get_four_table_feishu_config()
    required = ("app_id", "app_secret", "app_token", "account_table_id")
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"达人账号表飞书配置不完整: {', '.join(missing)}")

    accounts, duplicate_uids = scraper_module.fetch_existing_creator_accounts(config, include_duplicates=True)
    rows: list[dict] = []
    skipped: list[str] = []
    platform_counts = {"TikTok": 0, "Instagram": 0, "YouTube": 0}
    for account_uid, account in accounts.items():
        if account_uid in duplicate_uids:
            skipped.append(f"duplicate_uid: {account_uid}")
            continue
        fields = account.get("fields") if isinstance(account, dict) else {}
        fields = fields if isinstance(fields, dict) else {}
        if not _account_email_is_empty(fields.get(scraper_module.FOUR_TABLE_ACCOUNT_FIELD_EMAIL)):
            continue
        platform = str(fields.get(scraper_module.FOUR_TABLE_ACCOUNT_FIELD_PLATFORM) or "").strip()
        profile_url = _feishu_link_value(fields.get(scraper_module.FOUR_TABLE_ACCOUNT_FIELD_PROFILE_URL))
        normalized = scraper_module.normalize_link_record(profile_url)
        result = scraper_module.build_result(
            url=str(normalized.get("normalized_url") or ""),
            platform=platform,
            status="待补全",
            data_status="待检查",
        )
        if (
            platform not in platform_counts
            or not normalized.get("valid")
            or scraper_module.build_creator_uid(result) != account_uid
        ):
            skipped.append(f"{account_uid}: 账号唯一ID、平台或主页链接不完整/不一致")
            continue
        rows.append(scraper_module.result_to_row(result))
        platform_counts[platform] += 1

    if not rows:
        return {
            "task": None,
            "scanned_accounts": len(accounts),
            "created_count": 0,
            "skipped_count": len(skipped),
            "skipped": skipped,
            "duplicate_uids": sorted(duplicate_uids),
        }

    task = task_manager.create_task(
        TASKS_DIR,
        [str(row.get(scraper_module.FIELD_URL) or "") for row in rows],
        [],
        len(rows),
        name=f"缺失邮箱补全-{time.strftime('%Y%m%d')}",
        target_platform="全部",
        platform_summary=platform_counts,
        task_type="email_recheck",
    )
    task.update(
        {
            "status": "email_recheck_created",
            "email_recheck_source": "account_table_empty_email",
            "scan_skipped_count": len(skipped),
        }
    )
    _task, paths = task_manager.load_task(TASKS_DIR, task["id"])
    progress_rows = [dict(row, **{scraper_module.FIELD_STATUS: "待补全"}) for row in rows]
    task_manager.atomic_write_files(
        {
            paths["results"]: _csv_content(scraper_module.OUTPUT_FIELDS, rows),
            paths["progress"]: _csv_content(scraper_module.PROGRESS_FIELDS, progress_rows),
            paths["modifications"]: b"[]",
            paths["metadata"]: json.dumps(task, ensure_ascii=False, indent=2).encode("utf-8"),
        }
    )
    return {
        "task": task,
        "scanned_accounts": len(accounts),
        "created_count": len(rows),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "duplicate_uids": sorted(duplicate_uids),
    }


def create_manual_task(payload: dict) -> dict:
    """Create a one-record task that enters the same review and four-table flow."""
    profile_url = str(payload.get("profile_url") or "").strip()
    if not profile_url:
        raise ValueError("主页链接不能为空。")

    normalized = scraper_module.normalize_link_record(profile_url)
    if not normalized.get("valid"):
        raise ValueError(str(normalized.get("reason") or "主页链接无效。"))

    platform_by_key = {
        "tiktok": "TikTok",
        "instagram": "Instagram",
        "youtube": "YouTube",
    }
    normalized_platform = platform_by_key.get(str(normalized.get("platform") or "").lower(), "")
    selected_platform = str(payload.get("platform") or "").strip()
    if selected_platform not in {"TikTok", "Instagram", "YouTube"}:
        raise ValueError("请选择平台。")
    if selected_platform != normalized_platform:
        raise ValueError(f"主页链接属于 {normalized_platform}，请确认所选平台。")

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip()
    whatsapp = str(payload.get("whatsapp") or "").strip()
    note = str(payload.get("note") or "")
    source_contact = _resolve_source_contact(payload.get("source_contact_record_id"))
    follower_count = _normalize_follower_count(payload.get("follower_count"))
    if email:
        _validate_review_updates({scraper_module.FIELD_NAME: name or "未命名"}, {scraper_module.FIELD_EMAIL: email})
    if whatsapp:
        _validate_review_updates(
            {scraper_module.FIELD_NAME: name or "未命名"},
            {REVIEW_FIELD_WHATSAPP: whatsapp},
        )
    if follower_count:
        _validate_review_updates(
            {scraper_module.FIELD_NAME: name or "未命名"},
            {scraper_module.FIELD_FOLLOWER_COUNT: follower_count},
        )

    url = str(normalized.get("normalized_url") or "").strip()
    task = task_manager.create_task(
        TASKS_DIR,
        [url],
        [],
        1,
        name=payload.get("task_name"),
        target_platform=selected_platform,
        platform_summary={"TikTok": int(selected_platform == "TikTok"), "Instagram": int(selected_platform == "Instagram"), "YouTube": int(selected_platform == "YouTube")},
        task_type="manual",
    )
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result = scraper_module.build_result(
        url=url,
        platform=selected_platform,
        name=name,
        emails=[] if not email else [item.strip() for item in email.split(",") if item.strip()],
        email_source="人工录入" if email else "",
        follower_count=follower_count,
        status="手动录入",
        whatsapp=whatsapp,
        note=note,
        data_status="待检查",
        last_modified_at=now,
    )
    account_uid = scraper_module.build_creator_uid(result)
    result_row = scraper_module.result_to_row(result)
    progress_row = dict(result_row)
    # Keep the manual URL pending so supplemental crawling can reuse the existing crawler.
    progress_row[scraper_module.FIELD_STATUS] = "待补充抓取"
    manual_values = {
        field: value
        for field, value in {
            scraper_module.FIELD_NAME: name,
            scraper_module.FIELD_EMAIL: email,
            scraper_module.FIELD_FOLLOWER_COUNT: follower_count,
            REVIEW_FIELD_WHATSAPP: whatsapp,
            REVIEW_FIELD_NOTE: note,
        }.items()
        if value
    }
    modifications = []
    if manual_values:
        modifications.append(
            {
                "account_uid": account_uid,
                "modified_fields": {
                    field: {"old": "", "new": value} for field, value in manual_values.items()
                },
                "status": "pending_sync",
                "time": now,
                "source": "manual_task",
            }
        )
    task.update(
        {
            "status": "manual_created",
            "completed_count": 0,
            "modified_count": len(modifications),
            "last_modified_time": now if manual_values else "",
            "source_contact_record_id": source_contact["record_id"] if source_contact else "",
        }
    )
    if source_contact:
        task["source_contact_name"] = source_contact["name"]
    _task, paths = task_manager.load_task(TASKS_DIR, task["id"])
    task_manager.atomic_write_files(
        {
            paths["results"]: _csv_content(scraper_module.OUTPUT_FIELDS, [result_row]),
            paths["progress"]: _csv_content(scraper_module.PROGRESS_FIELDS, [progress_row]),
            paths["modifications"]: json.dumps(modifications, ensure_ascii=False, indent=2).encode("utf-8"),
            paths["metadata"]: json.dumps(task, ensure_ascii=False, indent=2).encode("utf-8"),
        }
    )
    if manual_values:
        protection = load_data_protection()
        if _merge_data_protection(protection, account_uid, manual_values, "人工录入", task["id"], now):
            _save_data_protection(protection)
    return {"task": task, "account_uid": account_uid}


def _normalize_follower_count(value: object) -> str:
    raw = str(value or "").strip()
    normalized = scraper_module.normalize_follower_count(raw)
    if raw and not normalized:
        raise ValueError("粉丝数格式错误，请填写如 10K、1.2M 或 100000。")
    return normalized


def _validate_review_updates(row: dict, fields: dict) -> dict[str, str]:
    if not isinstance(fields, dict) or not fields:
        raise ValueError("缺少可保存的审核字段。")
    unknown_fields = set(fields) - REVIEW_EDITABLE_FIELDS
    if unknown_fields:
        raise ValueError(f"不允许修改字段：{', '.join(sorted(unknown_fields))}")

    final_name = str(fields.get(scraper_module.FIELD_NAME, row.get(scraper_module.FIELD_NAME) or "")).strip()
    if not final_name:
        raise ValueError("达人名称不能为空。")

    final_email = str(fields.get(scraper_module.FIELD_EMAIL, row.get(scraper_module.FIELD_EMAIL) or "")).strip()
    email_for_validation = "" if final_email == scraper_module.NO_EMAIL else final_email
    if email_for_validation:
        if any(char.isspace() for char in email_for_validation):
            raise ValueError("邮箱格式错误：邮箱不能包含空格。")
        for email in email_for_validation.split(","):
            if not REVIEW_EMAIL_PATTERN.fullmatch(email):
                raise ValueError("邮箱格式错误。")

    final_whatsapp = str(fields.get(REVIEW_FIELD_WHATSAPP, row.get(REVIEW_FIELD_WHATSAPP) or "")).strip()
    if final_whatsapp:
        if not REVIEW_WHATSAPP_PATTERN.fullmatch(final_whatsapp):
            raise ValueError("WhatsApp号码格式异常。")
        digits = re.sub(r"\D", "", final_whatsapp)
        if not 7 <= len(digits) <= 20:
            raise ValueError("WhatsApp号码格式异常。")

    final_follower_count = _normalize_follower_count(
        fields.get(scraper_module.FIELD_FOLLOWER_COUNT, row.get(scraper_module.FIELD_FOLLOWER_COUNT) or "")
    )

    normalized: dict[str, str] = {}
    if scraper_module.FIELD_NAME in fields:
        normalized[scraper_module.FIELD_NAME] = final_name
    if scraper_module.FIELD_EMAIL in fields:
        normalized[scraper_module.FIELD_EMAIL] = final_email
    if scraper_module.FIELD_FOLLOWER_COUNT in fields:
        normalized[scraper_module.FIELD_FOLLOWER_COUNT] = final_follower_count
    if REVIEW_FIELD_WHATSAPP in fields:
        normalized[REVIEW_FIELD_WHATSAPP] = final_whatsapp
    if REVIEW_FIELD_NOTE in fields:
        normalized[REVIEW_FIELD_NOTE] = str(fields[REVIEW_FIELD_NOTE] or "")
    return normalized


def _csv_content(fieldnames: list[str], rows: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def update_task_review_result(task_id: str, account_uid: str, fields: dict) -> dict:
    if SCRAPE_JOB.running and SCRAPE_JOB.task_id == task_id:
        raise RuntimeError("任务正在运行，暂不能审核结果。")
    account_uid = str(account_uid or "").strip()
    if not account_uid:
        raise ValueError("缺少账号唯一ID。")

    with task_manager.task_lock():
        task, paths = task_manager.load_task(TASKS_DIR, task_id)
        result_fieldnames, result_rows = _read_task_csv(paths["results"])
        progress_fieldnames, progress_rows = _read_task_csv(paths["progress"])

        result_matches = [row for row in result_rows if _account_uid_for_row(row) == account_uid]
        if len(result_matches) != 1:
            raise ValueError("未找到唯一的任务结果记录。")
        progress_matches = [row for row in progress_rows if _account_uid_for_row(row) == account_uid]
        if not progress_matches:
            raise ValueError("未找到对应的任务进度记录。")

        target_row = result_matches[0]
        updates = _validate_review_updates(target_row, fields)
        modified_fields = {
            field: {"old": str(target_row.get(field) or ""), "new": value}
            for field, value in updates.items()
            if str(target_row.get(field) or "") != value
        }
        if not modified_fields:
            raise ValueError("没有检测到需要保存的修改。")

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        task_result_fields = [scraper_module.FIELD_FOLLOWER_COUNT, *REVIEW_CSV_FIELDS]
        for row in result_rows:
            for field in task_result_fields:
                row.setdefault(field, "待检查" if field == REVIEW_FIELD_DATA_STATUS else "")
            if _account_uid_for_row(row) == account_uid:
                row.update(updates)
                row[REVIEW_FIELD_DATA_STATUS] = "待同步"
                row[REVIEW_FIELD_MODIFIED_AT] = now

        for row in progress_rows:
            for field in task_result_fields:
                row.setdefault(field, "待检查" if field == REVIEW_FIELD_DATA_STATUS else "")
            if _account_uid_for_row(row) == account_uid:
                row.update(updates)
                row[REVIEW_FIELD_DATA_STATUS] = "待同步"
                row[REVIEW_FIELD_MODIFIED_AT] = now

        result_fieldnames = list(dict.fromkeys(result_fieldnames + task_result_fields))
        progress_fieldnames = list(dict.fromkeys(progress_fieldnames + task_result_fields))
        modifications = task_manager.load_modifications(TASKS_DIR, task_id)
        modifications.append(
            {
                "account_uid": account_uid,
                "modified_fields": modified_fields,
                "status": "pending_sync",
                "time": now,
            }
        )
        task["modified_count"] = len(modifications)
        task["last_modified_time"] = now

        task_manager.atomic_write_files(
            {
                paths["results"]: _csv_content(result_fieldnames, result_rows),
                paths["progress"]: _csv_content(progress_fieldnames, progress_rows),
                paths["modifications"]: json.dumps(modifications, ensure_ascii=False, indent=2).encode("utf-8"),
                paths["metadata"]: json.dumps(task, ensure_ascii=False, indent=2).encode("utf-8"),
            }
        )
    protection = load_data_protection()
    protection_source = "人工录入" if task.get("task_type") == "manual" else "审核修改"
    if _merge_data_protection(protection, account_uid, updates, protection_source, task_id, now):
        _save_data_protection(protection)
    return {
        "task_id": task_id,
        "account_uid": account_uid,
        "modified_fields": modified_fields,
        "data_status": "待同步",
        "modified_at": now,
    }


def _validate_task_sync_results(rows: list[dict]) -> tuple[list[dict], list[str]]:
    results: list[dict] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        result = scraper_module.row_to_result(row)
        account_uid = scraper_module.build_creator_uid(result)
        reference = account_uid or f"第 {index} 条"
        name = str(result.get("name") or "").strip()
        if not name:
            errors.append(f"{reference}：达人名称不能为空。")

        # Validate the stored review value before row_to_result() cleans candidates.
        email_display = str(row.get(scraper_module.FIELD_EMAIL) or "").strip()
        if email_display and email_display != scraper_module.NO_EMAIL:
            if any(char.isspace() for char in email_display):
                errors.append(f"{reference}：邮箱格式错误，邮箱不能包含空格。")
            else:
                for email in email_display.split(","):
                    if not REVIEW_EMAIL_PATTERN.fullmatch(email.strip()):
                        errors.append(f"{reference}：邮箱格式错误：{email.strip() or email_display}")

        whatsapp = str(row.get(REVIEW_FIELD_WHATSAPP) or "").strip()
        if whatsapp:
            digits = re.sub(r"\D", "", whatsapp)
            if not REVIEW_WHATSAPP_PATTERN.fullmatch(whatsapp) or not 7 <= len(digits) <= 20:
                errors.append(f"{reference}：WhatsApp号码格式异常。")

        try:
            _normalize_follower_count(row.get(scraper_module.FIELD_FOLLOWER_COUNT) or "")
        except ValueError as exc:
            errors.append(f"{reference}：{exc}")
        results.append(result)
    return results, errors


def _task_data_source(task: dict) -> str:
    task_type = str(task.get("task_type") or "scrape")
    if task_type == "email_recheck":
        return "系统抓取"
    if task_type == "manual":
        return "人工+系统补充" if task.get("has_system_supplement") else "人工录入"
    return "系统抓取"


def sync_task_results_to_four_tables(task_id: str) -> dict:
    """Sync one task's reviewed CSV through the existing four-table sync implementation."""
    if SCRAPE_JOB.running and SCRAPE_JOB.task_id == task_id:
        raise RuntimeError("任务正在运行，暂不能同步审核结果。")

    task, paths = task_manager.load_task(TASKS_DIR, task_id)
    data_source = _task_data_source(task)
    email_source = _task_email_source(task)
    data_protection = load_data_protection()
    source_contact_record_id = (
        str(task.get("source_contact_record_id") or "").strip()
        if task.get("task_type") == "manual"
        else ""
    )
    _fieldnames, rows = _read_task_csv(paths["results"])
    email_recheck_only = task.get("task_type") == "email_recheck"
    if email_recheck_only:
        results = [scraper_module.row_to_result(row) for row in rows]
        validation_errors = []
    else:
        results, validation_errors = _validate_task_sync_results(rows)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    empty_summary = {
        "created_creators": 0,
        "created_accounts": 0,
        "updated_accounts": 0,
        "updated_creators": 0,
        "skipped": 0,
        "errors": 0,
    }

    if not rows:
        validation_errors.append("当前任务没有可同步的抓取结果。")
    if validation_errors:
        task_manager.update_task(
            TASKS_DIR,
            task_id,
            sync_status="failed",
            sync_time=now,
            sync_summary=empty_summary,
            sync_errors=validation_errors,
        )
        return {
            "task_id": task_id,
            "record_count": len(rows),
            "sync_status": "failed",
            "sync_summary": empty_summary,
            "sync_errors": validation_errors,
        }

    try:
        summary = scraper_module.push_to_feishu_four_tables(
            results,
            get_four_table_feishu_config(),
            email_recheck_only=email_recheck_only,
            data_source=data_source,
            email_source=email_source,
            data_protection=data_protection,
            source_contact_record_id=source_contact_record_id,
        )
        sync_errors = [str(item) for item in summary.get("errors", [])]
        sync_summary = {
            "created_creators": int(summary.get("created_creators") or 0),
            "created_accounts": int(summary.get("created_accounts") or 0),
            "updated_accounts": int(summary.get("updated_accounts") or 0),
            "updated_creators": int(summary.get("updated_creators") or 0),
            "skipped": int(summary.get("skipped") or 0),
            "errors": len(sync_errors),
        }
        sync_status = "success" if not sync_errors else "failed"
    except Exception as exc:
        sync_errors = [str(exc)]
        sync_summary = dict(empty_summary)
        sync_summary["errors"] = 1
        sync_status = "failed"

    task_manager.update_task(
        TASKS_DIR,
        task_id,
        sync_status=sync_status,
        sync_time=now,
        last_sync_source=data_source,
        sync_summary=sync_summary,
        sync_errors=sync_errors,
        sync_log=summary.get("sync_logs", []) if "summary" in locals() else [],
    )
    if "summary" in locals():
        result_by_uid = {
            scraper_module.build_creator_uid(result): result
            for result in results
            if scraper_module.build_creator_uid(result)
        }
        protection_changed = False
        for entry in summary.get("sync_logs", []):
            if not isinstance(entry, dict) or scraper_module.FOUR_TABLE_ACCOUNT_FIELD_EMAIL not in entry.get("updated_fields", []):
                continue
            account_uid = str(entry.get("account_uid") or "")
            result = result_by_uid.get(account_uid) or {}
            email = str(result.get("email_display") or "")
            if email and email != scraper_module.NO_EMAIL:
                protection_changed = _merge_data_protection(
                    data_protection, account_uid, {scraper_module.FIELD_EMAIL: email}, data_source, task_id,
                    str(entry.get("updated_at") or now),
                ) or protection_changed
        if protection_changed:
            _save_data_protection(data_protection)
    return {
        "task_id": task_id,
        "record_count": len(rows),
        "sync_status": sync_status,
        "sync_summary": sync_summary,
        "sync_errors": sync_errors,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, **extra) -> None:
        data = {"ok": True}
        data.update(extra)
        self._json(data)

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status=status)

    def _save_state_and_ok(self) -> None:
        save_state(STATE)
        self._ok()

    def _normalize_save_state_and_ok(self) -> None:
        global STATE
        STATE = normalize_state(STATE)
        save_state(STATE)
        self._ok()

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _serve_file(self, file_path: Path) -> None:
        try:
            static_root = STATIC_DIR.resolve()
            resolved_path = file_path.resolve()
            resolved_path.relative_to(static_root)
        except (OSError, ValueError):
            self.send_error(404)
            return

        if not resolved_path.exists() or not resolved_path.is_file():
            self.send_error(404)
            return
        suffix = resolved_path.suffix.lower()
        mime = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(suffix, "application/octet-stream")
        data = resolved_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/tasks":
            return self._json({"ok": True, **get_task_list()})

        task_results_match = re.fullmatch(r"/api/tasks/([^/]+)/results", parsed.path)
        if task_results_match:
            try:
                return self._json({"ok": True, **get_task_review_results(task_results_match.group(1))})
            except ValueError as exc:
                return self._error(str(exc))

        if parsed.path == "/api/agency-contacts":
            try:
                return self._ok(**get_agency_contact_options())
            except RuntimeError as exc:
                return self._error(str(exc))

        if parsed.path == "/api/state":
            four_table_config = get_four_table_feishu_config()
            client_state = state_for_client(STATE)
            client_feishu = client_state["feishu"]
            return self._json(
                {
                    "ui": client_state["ui"],
                    "profiles": get_profiles(),
                    "selectedProfile": client_state["profiles"].get("selected", "Default"),
                    "accounts": build_accounts_payload(),
                    "feishu": {
                        "app_id": client_feishu.get("app_id", ""),
                        "app_secret": client_feishu.get("app_secret", ""),
                        "has_app_secret": bool(STATE["feishu"].get("app_secret")),
                        "app_token": client_feishu.get("app_token", ""),
                        "has_app_token": bool(four_table_config["app_token"]),
                        "creator_table_id": four_table_config["creator_table_id"],
                        "account_table_id": four_table_config["account_table_id"],
                        "agency_table_id": four_table_config["agency_table_id"],
                        "contact_table_id": four_table_config["contact_table_id"],
                    },
                    "mail": client_state["mail"],
                }
            )

        if parsed.path == "/api/scrape/status":
            return self._json(SCRAPE_JOB.snapshot())

        if parsed.path == "/api/mail/inbox/messages":
            data = mail_sync_module.load_mail_messages()
            messages = data.get("messages") if isinstance(data.get("messages"), list) else []
            summary = {
                "total": len(messages),
                "unread": sum(1 for item in messages if isinstance(item, dict) and item.get("is_unread")),
                "matched": sum(1 for item in messages if isinstance(item, dict) and item.get("reply_status") == "matched"),
            }
            return self._ok(
                updated_at=str(data.get("updated_at") or ""),
                summary=summary,
                messages=messages[:50],
                accounts=data.get("accounts") if isinstance(data.get("accounts"), dict) else {},
            )

        if parsed.path in {"", "/"}:
            return self._serve_file(STATIC_DIR / "index.html")

        return self._serve_file(STATIC_DIR / parsed.path.lstrip("/"))

    def do_POST(self) -> None:
        global STATE
        parsed = urlparse(self.path)
        payload = self._read_json()

        try:
            task_result_update_match = re.fullmatch(r"/api/tasks/([^/]+)/results/update", parsed.path)
            if task_result_update_match:
                try:
                    result = update_task_review_result(
                        task_result_update_match.group(1),
                        payload.get("account_uid"),
                        payload.get("fields"),
                    )
                    return self._ok(**result)
                except (ValueError, RuntimeError) as exc:
                    return self._error(str(exc))

            task_sync_match = re.fullmatch(r"/api/tasks/([^/]+)/sync-four-tables", parsed.path)
            if task_sync_match:
                try:
                    result = sync_task_results_to_four_tables(task_sync_match.group(1))
                    if result["sync_status"] != "success":
                        return self._json({"ok": False, "error": "任务四表同步失败。", **result}, status=400)
                    return self._ok(**result)
                except (ValueError, RuntimeError) as exc:
                    return self._error(str(exc))

            task_open_results_match = re.fullmatch(r"/api/tasks/([^/]+)/results/open", parsed.path)
            if task_open_results_match:
                try:
                    _task, task_paths = task_manager.load_task(TASKS_DIR, task_open_results_match.group(1))
                    if not task_paths["results"].exists():
                        return self._error("当前任务尚未生成结果文件。")
                    subprocess.Popen(["explorer.exe", str(task_paths["results"])])
                    return self._ok()
                except ValueError as exc:
                    return self._error(str(exc))

            task_rename_match = re.fullmatch(r"/api/tasks/([^/]+)/rename", parsed.path)
            if task_rename_match:
                try:
                    task = rename_task(task_rename_match.group(1), payload.get("name"))
                    return self._ok(task=task)
                except ValueError as exc:
                    return self._error(str(exc))

            if parsed.path == "/api/settings/ui":
                language = (payload.get("language") or "").strip()
                STATE["ui"]["language"] = "en" if language == "en" else "zh"
                return self._save_state_and_ok()

            if parsed.path == "/api/settings/profiles":
                STATE["profiles"]["selected"] = (payload.get("selected") or "").strip() or AUTOMATION_PROFILE_NAME
                return self._save_state_and_ok()

            if parsed.path == "/api/settings/accounts":
                entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
                STATE["accounts"]["entries"] = [
                    {
                        "profile": str(item.get("profile") or "").strip(),
                        "alias": str(item.get("alias") or "").strip(),
                        "usage": str(item.get("usage") or "通用").strip() or "通用",
                    }
                    for item in entries
                    if isinstance(item, dict) and str(item.get("profile") or "").strip()
                ]
                return self._save_state_and_ok()

            if parsed.path == "/api/account/open":
                profile = (payload.get("profile") or "").strip()
                if not profile:
                    return self._error("缺少 profile。")
                open_chrome_profile(profile)
                return self._ok()

            if parsed.path == "/api/settings/feishu":
                STATE["feishu"]["app_id"] = str(payload.get("app_id") or "").strip()
                new_secret = str(payload.get("app_secret") or "").strip()
                if new_secret and not is_sensitive_mask(new_secret):
                    STATE["feishu"]["app_secret"] = new_secret
                for key in (
                    "app_token",
                    "creator_table_id",
                    "account_table_id",
                    "agency_table_id",
                    "contact_table_id",
                ):
                    if key in payload:
                        value = str(payload.get(key) or "").strip()
                        if key == "app_token" and is_sensitive_mask(value):
                            continue
                        STATE["feishu"][key] = value
                return self._normalize_save_state_and_ok()

            if parsed.path == "/api/settings/mail":
                STATE["mail"] = normalize_mail_state(merge_masked_mail_passwords(payload, STATE.get("mail")))
                return self._save_state_and_ok()

            if parsed.path == "/api/mail/test":
                raw_account = payload.get("account") if isinstance(payload.get("account"), dict) else payload
                merged_test_accounts = merge_masked_mail_passwords(
                    {"accounts": [raw_account]}, STATE.get("mail")
                ).get("accounts", [])
                account = normalize_mail_account(merged_test_accounts[0] if merged_test_accounts else None)
                test_imap_login(account)
                test_smtp_login(account)
                return self._ok(imap_ok=True, smtp_ok=True)

            if parsed.path == "/api/mail/inbox/sync":
                accounts = STATE.get("mail", {}).get("accounts") if isinstance(STATE.get("mail"), dict) else []
                enabled_accounts = [item for item in accounts if isinstance(item, dict) and item.get("enabled")]
                if not enabled_accounts:
                    return self._error("没有启用的邮箱账户。")
                limit_per_account = payload.get("limit_per_account") or 20
                four_table_config = get_four_table_feishu_config()
                required_four_table_keys = ("app_id", "app_secret", "app_token", "creator_table_id", "account_table_id")
                missing_four_table_keys = [key for key in required_four_table_keys if not four_table_config.get(key)]
                if missing_four_table_keys:
                    return self._error(f"四表飞书配置不完整：缺少 {', '.join(missing_four_table_keys)}。")
                summary = mail_sync_module.sync_enabled_mail_accounts(
                    enabled_accounts,
                    {
                        "limit_per_account": limit_per_account,
                        "four_table_config": four_table_config,
                    },
                )
                return self._ok(
                    updated_at=str(summary.get("updated_at") or ""),
                    accounts_checked=int(summary.get("accounts_checked") or 0),
                    messages_fetched=int(summary.get("messages_fetched") or 0),
                    messages_new=int(summary.get("messages_new") or 0),
                    matched_messages=int(summary.get("matched_messages") or 0),
                    messages_total=int(summary.get("messages_total") or 0),
                    errors=summary.get("errors") if isinstance(summary.get("errors"), list) else [],
                )

            if parsed.path == "/api/mail/inbox/sync-crm-replies":
                four_table_config = get_four_table_feishu_config()
                required_four_table_keys = ("app_id", "app_secret", "app_token", "creator_table_id")
                missing_four_table_keys = [key for key in required_four_table_keys if not four_table_config.get(key)]
                if missing_four_table_keys:
                    return self._error(f"达人表飞书配置不完整：缺少 {', '.join(missing_four_table_keys)}。")
                summary = mail_sync_module.sync_creator_replies(four_table_config)
                return self._ok(
                    updated_at=str(summary.get("updated_at") or ""),
                    updated=int(summary.get("updated") or 0),
                    time_only=int(summary.get("time_only") or 0),
                    skipped=int(summary.get("skipped") or 0),
                    failed=int(summary.get("failed") or 0),
                    processed_messages=int(summary.get("processed_messages") or 0),
                    errors=summary.get("errors") if isinstance(summary.get("errors"), list) else [],
                )

            if parsed.path == "/api/normalize-links":
                if isinstance(payload.get("links"), list):
                    raw_links = [str(item or "").strip() for item in payload.get("links", [])]
                else:
                    text = str(payload.get("text") or "")
                    raw_links = [line.strip() for line in text.splitlines() if line.strip()]
                normalized = scraper_module.build_normalize_payload(raw_links)
                return self._ok(
                    normalized_links=normalized.get("normalized_links", []),
                    invalid_links=normalized.get("invalid_links", []),
                )

            if parsed.path == "/api/tasks/manual":
                try:
                    return self._ok(**create_manual_task(payload))
                except ValueError as exc:
                    return self._error(str(exc))

            if parsed.path == "/api/tasks/email-recheck/scan":
                try:
                    return self._ok(**create_email_recheck_task())
                except (RuntimeError, ValueError) as exc:
                    return self._error(str(exc))

            if parsed.path == "/api/tasks":
                text = str(payload.get("text") or "")
                raw_links = [line.strip() for line in text.splitlines() if line.strip()]
                if not raw_links:
                    return self._error("请粘贴至少一个链接。")
                prepared = prepare_task_links(raw_links, payload.get("target_platform"))
                normalized_links = prepared["normalized_links"]
                if not normalized_links:
                    return self._error("没有符合目标平台的有效链接。")
                task = task_manager.create_task(
                    TASKS_DIR,
                    normalized_links,
                    prepared["invalid_links"],
                    len(raw_links),
                    name=payload.get("name"),
                    target_platform=prepared["target_platform"],
                    platform_summary=prepared["platform_summary"],
                    filtered_links=prepared["filtered_links"],
                )
                return self._ok(
                    task=task,
                    invalid_links=prepared["invalid_links"],
                    filtered_links=prepared["filtered_links"],
                )

            if parsed.path == "/api/scrape/start":
                try:
                    return self._ok(**start_scrape(payload))
                except RuntimeError as exc:
                    return self._error(str(exc), status=409)

            if parsed.path == "/api/scrape/stop":
                try:
                    return self._ok(**request_stop_scrape())
                except RuntimeError as exc:
                    return self._error(str(exc), status=409)

            if parsed.path == "/api/scrape/pause":
                try:
                    return self._ok(**pause_scrape())
                except RuntimeError as exc:
                    return self._error(str(exc), status=409)

            if parsed.path == "/api/scrape/resume":
                try:
                    return self._ok(**resume_scrape())
                except RuntimeError as exc:
                    return self._error(str(exc), status=409)

            return self._error("接口不存在。", status=404)
        except Exception as exc:
            return self._error(str(exc), status=500)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        task_match = re.fullmatch(r"/api/tasks/([^/]+)", parsed.path)
        if not task_match:
            return self._error("接口不存在。", status=404)
        try:
            return self._ok(**delete_local_task(task_match.group(1)))
        except RuntimeError as exc:
            return self._error(str(exc), status=409)
        except ValueError as exc:
            return self._error(str(exc), status=404)


def run() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    if os.environ.get("KOLCONNECT_DESKTOP") != "1":
        webbrowser.open(f"http://{HOST}:{PORT}/?v={int(time.time())}")
    server.serve_forever()


if __name__ == "__main__":
    run()

