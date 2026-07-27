from __future__ import annotations

"""KOL联系助手抓取脚本。

只保留这几件事：
1. 读取达人链接
2. 抓主页邮箱
3. 主页没有邮箱时，尝试从简介外链补抓邮箱
4. 提取最近发布日期
5. 保存 CSV / progress.csv，并可同步飞书
"""

import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import html
import json
import logging
import os
import random
import re
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from runtime_paths import get_external_resources_dir, get_resource_dir

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from webdriver_manager.chrome import ChromeDriverManager
    WDM_AVAILABLE = True
except ImportError:
    WDM_AVAILABLE = False

SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def _log_success(self, msg, *args, **kwargs):
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, msg, args, **kwargs)


logging.Logger.success = _log_success
logging.basicConfig(level=logging.WARNING, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)
log.setLevel(SUCCESS_LEVEL)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
EMAIL_EDGE_CHARS = " \t\r\n.,;:!?)]}>\"'"
LATEST_DATE_PATTERNS = [
    re.compile(r'"uploadDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"'),
    re.compile(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})"'),
    re.compile(r'"taken_at_timestamp"\s*:\s*(\d{10})'),
    re.compile(r'"createTime"\s*:\s*:?\s*"?(\d{10})"?'),
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]
IGNORE_DOMAINS = {"example.com", "example.org", "googleapis.com", "gstatic.com", "sentry.io"}
LOW_VALUE_HOSTS = {
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com",
    "youtube.com", "www.youtube.com", "youtu.be",
    "facebook.com", "www.facebook.com",
    "x.com", "twitter.com", "www.x.com", "www.twitter.com",
}
EXTERNAL_PRIORITY_WORDS = ["contact", "contato", "about", "sobre", "business", "comercial", "parceria", "blog", "site"]
REQUEST_TIMEOUT = 20
PAGE_LOAD_TIMEOUT = 30
REQUEST_DELAY = (8, 25)
MAX_RETRIES = 2
MAX_EXTERNAL_LINKS = 3
MAX_PRIORITY_LINKS = 4
MAX_PAGE_REFRESHES = 5
PROGRESS_FILE = "progress.csv"

NO_EMAIL = "未抓取到"
FIELD_URL = "达人链接"
FIELD_PLATFORM = "平台"
FIELD_NAME = "达人名称"
FIELD_EMAIL = "邮箱"
FIELD_EMAIL_SOURCE = "邮箱来源"
FIELD_EXTERNAL_LINK = "外链"
FIELD_EXTERNAL_SOURCE = "外链来源"
FIELD_LATEST_DATE = "最近发布日期"
FIELD_FOLLOWER_COUNT = "粉丝数"
FIELD_STATUS = "状态"
FIELD_WHATSAPP = "WhatsApp"
FIELD_NOTE = "备注"
FIELD_DATA_STATUS = "数据状态"
FIELD_LAST_MODIFIED_AT = "最后修改时间"

FOLLOWER_COUNT_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)\s*([kKmM])?$")

REVIEW_FIELDS = [
    FIELD_WHATSAPP,
    FIELD_NOTE,
    FIELD_DATA_STATUS,
    FIELD_LAST_MODIFIED_AT,
]

PROGRESS_FIELDS = [
    FIELD_URL,
    FIELD_PLATFORM,
    FIELD_NAME,
    FIELD_EMAIL,
    FIELD_EMAIL_SOURCE,
    FIELD_EXTERNAL_LINK,
    FIELD_EXTERNAL_SOURCE,
    FIELD_LATEST_DATE,
    FIELD_FOLLOWER_COUNT,
    FIELD_STATUS,
    *REVIEW_FIELDS,
]
OUTPUT_FIELDS = [
    FIELD_URL,
    FIELD_PLATFORM,
    FIELD_NAME,
    FIELD_EMAIL,
    FIELD_EMAIL_SOURCE,
    FIELD_EXTERNAL_LINK,
    FIELD_EXTERNAL_SOURCE,
    FIELD_LATEST_DATE,
    FIELD_FOLLOWER_COUNT,
    FIELD_STATUS,
    *REVIEW_FIELDS,
]

CRM_RECORD_PAGE_SIZE = 500

FOUR_TABLE_CREATOR_FIELD_NAME = "达人名称"
FOUR_TABLE_CREATOR_FIELD_ID = "达人ID"
FOUR_TABLE_CREATOR_FIELD_REGION = "国家/地区"
FOUR_TABLE_CREATOR_FIELD_LANGUAGE = "语言"
FOUR_TABLE_CREATOR_FIELD_STAGE = "合作阶段"
FOUR_TABLE_CREATOR_FIELD_OWNER = "负责人"
FOUR_TABLE_CREATOR_FIELD_WHATSAPP = "WhatsApp"
FOUR_TABLE_CREATOR_FIELD_NOTE = "备注"
FOUR_TABLE_CREATOR_FIELD_SOURCE_CONTACT = "来源联系人"

FOUR_TABLE_ACCOUNT_FIELD_UID = "账号唯一ID"
FOUR_TABLE_ACCOUNT_FIELD_PLATFORM = "平台"
FOUR_TABLE_ACCOUNT_FIELD_PROFILE_URL = "主页链接"
FOUR_TABLE_ACCOUNT_FIELD_EMAIL = "账号邮箱"
FOUR_TABLE_ACCOUNT_FIELD_EMAIL_SOURCE = "邮箱来源"
FOUR_TABLE_ACCOUNT_FIELD_LATEST_PUBLISH_AT = "最近发布时间"
FOUR_TABLE_ACCOUNT_FIELD_FOLLOWER_COUNT = "粉丝数"
FOUR_TABLE_ACCOUNT_FIELD_LAST_SCRAPED_AT = "最近抓取时间"
FOUR_TABLE_ACCOUNT_FIELD_SOURCE = "数据来源"
FOUR_TABLE_ACCOUNT_FIELD_SCRAPE_STATUS = "抓取状态"
FOUR_TABLE_ACCOUNT_FIELD_OWNERSHIP_STATUS = "归属状态"
FOUR_TABLE_ACCOUNT_FIELD_CREATOR = "达人"
FOUR_TABLE_ACCOUNT_FIELD_CANDIDATES = "疑似达人候选"

FOUR_TABLE_DEFAULT_REGION = "巴西"
FOUR_TABLE_DEFAULT_LANGUAGE = "葡萄牙语"
FOUR_TABLE_DEFAULT_STAGE = "未联系"
FOUR_TABLE_DEFAULT_SOURCE = "系统抓取"


class BrowserStartError(RuntimeError):
    pass


def setup_console_encoding() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    if "youtube.com" in host or "youtu.be" in host:
        return "YouTube"
    if "tiktok.com" in host:
        return "TikTok"
    if "instagram.com" in host:
        return "Instagram"
    return "Unknown"


def _normalized_host(parsed) -> str:
    host = (parsed.netloc or "").strip().lower()
    if not host:
        return ""
    host = host[4:] if host.startswith("www.") else host
    return f"www.{host}"


def _normalize_tiktok_profile(parsed) -> str:
    parts = [part for part in parsed.path.split("/") if part]
    handle = next((part for part in parts if part.startswith("@")), "")
    return f"https://www.tiktok.com/{handle}" if handle else ""


def _normalize_instagram_profile(parsed) -> str:
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return ""
    first = parts[0]
    first_lower = first.lower()
    reserved = {"reel", "reels", "p", "stories", "tv", "explore", "accounts", "directory"}
    if first_lower in reserved or first_lower.startswith("_"):
        return ""
    return f"https://www.instagram.com/{first}/"


def _normalize_youtube_profile(parsed) -> str:
    host = (parsed.netloc or "").strip().lower()
    host = host[4:] if host.startswith("www.") else host
    if host == "youtu.be":
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return ""
    first = parts[0]
    first_lower = first.lower()
    if first.startswith("@") and (len(parts) == 1 or (len(parts) == 2 and parts[1].lower() == "shorts")):
        return f"https://www.youtube.com/{first}"
    if first_lower in {"channel", "c", "user"} and len(parts) >= 2 and parts[1] and (
        len(parts) == 2 or (len(parts) == 3 and parts[2].lower() == "shorts")
    ):
        return f"https://www.youtube.com/{first_lower}/{parts[1]}"
    return ""


def _normalization_failure_reason(raw_url: str, platform: str, parsed) -> str:
    if not raw_url:
        return "链接为空"
    if parsed.scheme not in {"http", "https"}:
        return "链接必须以 http:// 或 https:// 开头"
    if not platform:
        return "不支持的平台链接"
    if platform == "YouTube":
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0].lower() == "shorts":
            return "YouTube Shorts视频链接无法确定达人主页，请提供频道主页"
        return "YouTube 链接无法确定达人主页，请提供频道主页"
    if platform == "Instagram":
        return "Instagram 链接无法确定达人主页，请提供主页链接"
    if platform == "TikTok":
        return "TikTok 链接无法确定达人主页，请提供主页链接"
    return "无法确定达人主页"


def normalize_link_record(raw_url: str) -> dict:
    raw_url = str(raw_url or "").strip()
    if not raw_url:
        return {
            "input": raw_url,
            "platform": "",
            "normalized_url": "",
            "valid": False,
            "status": "failed",
            "reason": "链接为空",
        }
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        return {
            "input": raw_url,
            "platform": "",
            "normalized_url": "",
            "valid": False,
            "status": "failed",
            "reason": _normalization_failure_reason(raw_url, "", parsed),
        }

    normalized_host = _normalized_host(parsed)
    platform = detect_platform(f"https://{normalized_host}{parsed.path}")
    normalized_url = ""
    if platform == "TikTok":
        normalized_url = _normalize_tiktok_profile(parsed)
    elif platform == "Instagram":
        normalized_url = _normalize_instagram_profile(parsed)
    elif platform == "YouTube":
        normalized_url = _normalize_youtube_profile(parsed)

    platform_key = platform.lower()
    valid = bool(normalized_url)
    return {
        "input": raw_url,
        "platform": platform_key,
        "normalized_url": normalized_url,
        "valid": valid,
        "status": "success" if valid else "failed",
        "reason": "" if valid else _normalization_failure_reason(raw_url, platform, parsed),
    }


def normalize_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        record = normalize_link_record(raw)
        clean = record["normalized_url"]
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def build_normalize_payload(urls: list[str]) -> dict:
    normalized_links: list[str] = []
    invalid_links: list[dict[str, str]] = []
    seen_links: set[str] = set()
    seen_invalid: set[str] = set()

    for raw in urls:
        record = normalize_link_record(raw)
        if record["valid"]:
            normalized_url = str(record["normalized_url"])
            if normalized_url and normalized_url not in seen_links:
                seen_links.add(normalized_url)
                normalized_links.append(normalized_url)
        else:
            raw_value = str(record["input"] or "").strip()
            if raw_value and raw_value not in seen_invalid:
                seen_invalid.add(raw_value)
                invalid_links.append(
                    {
                        "original_url": raw_value,
                        "status": "failed",
                        "reason": str(record.get("reason") or "无法确定达人主页"),
                    }
                )

    return {
        "normalized_links": normalized_links,
        "invalid_links": invalid_links,
    }


def build_creator_uid(result: dict) -> str:
    raw_url = str(result.get("url") or "").strip()
    if not raw_url:
        return ""

    normalized_urls = normalize_urls([raw_url])
    normalized_url = normalized_urls[0] if normalized_urls else ""
    if not normalized_url:
        return ""

    platform = str(result.get("platform") or detect_platform(normalized_url)).strip().lower()
    if not platform:
        return ""

    return f"{platform}|{normalized_url}"


def _normalize_crm_profile_url(raw_url: str) -> str:
    raw_url = str(raw_url or "").strip()
    if not raw_url:
        return ""
    normalized_urls = normalize_urls([raw_url])
    return normalized_urls[0] if normalized_urls else ""


def _crm_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _crm_date_to_ms(value: str) -> int | None:
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return None


def _crm_result_name(result: dict) -> str:
    return str(result.get("name") or "").strip()


def _crm_result_email(result: dict) -> str:
    email = str(result.get("email_display") or "").strip()
    return "" if not email or email == NO_EMAIL else email


def clean_email_candidates(candidates: list[str]) -> list[str]:
    """Normalize email candidates and remove only provable escaped-newline duplicates."""
    cleaned: list[str] = []
    for candidate in candidates:
        email = html.unescape(unquote(str(candidate or ""))).strip(EMAIL_EDGE_CHARS)
        email = re.sub(r"^(?:\\\\[nrt])+|(?:\\\\[nrt])+$", "", email).strip(EMAIL_EDGE_CHARS)
        if not EMAIL_REGEX.fullmatch(email):
            continue

        lower = email.lower()
        if "u002f@" in lower or "\\u" in lower:
            continue
        domain = lower.split("@")[-1]
        if any(bad in domain for bad in IGNORE_DOMAINS):
            continue
        cleaned.append(email)

    # Keep a legal n-prefixed address unless the same batch also contains the
    # exact address without that leading n (a common literal "\\n" extraction artifact).
    candidate_keys = {email.lower() for email in cleaned}
    unique: list[str] = []
    seen: set[str] = set()
    for email in cleaned:
        lower = email.lower()
        if lower.startswith("n") and lower[1:] in candidate_keys:
            continue
        if lower not in seen:
            seen.add(lower)
            unique.append(email)
    return unique


def extract_emails_from_text(text: str) -> list[str]:
    return clean_email_candidates(EMAIL_REGEX.findall(text or ""))


def extract_mailto_emails(text: str) -> list[str]:
    matches = re.findall(r"mailto:([^?\"'\s>]+)", text or "", flags=re.I)
    return clean_email_candidates([item for item in matches if "@" in item])


def choose_best_email(emails: list[str]) -> list[str]:
    if not emails:
        return []
    ordered = clean_email_candidates(emails)
    ordered.sort(key=lambda email: (email.lower().startswith(("support@", "info@", "hello@", "admin@")), len(email)))
    return ordered


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
    })
    return session


def fetch_html(url: str, session: requests.Session) -> str | None:
    for attempt in range(MAX_RETRIES + 1):
        session.headers["User-Agent"] = random.choice(USER_AGENTS)
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(2 + attempt)
    return None


def find_chrome_user_data_dir() -> str:
    if sys.platform == "win32":
        return os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    return os.path.expanduser("~/.config/google-chrome")


def copy_chrome_profile(user_data_dir: str, profile: str) -> str:
    """复制 Chrome 登录资料，避免 Selenium 直接占用正在使用的 Profile。"""
    source_root = Path(user_data_dir)
    source_profile = source_root / profile
    if not source_profile.exists():
        raise BrowserStartError(f"找不到 Chrome profile: {profile}")

    temp_root = Path(tempfile.mkdtemp(prefix="potato_chrome_"))
    local_state = source_root / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, temp_root / "Local State")

    ignore_names = {
        "Cache",
        "Code Cache",
        "GPUCache",
        "ShaderCache",
        "GrShaderCache",
        "DawnCache",
        "Crashpad",
        "BrowserMetrics",
        "LOCK",
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
    }
    shutil.copytree(
        source_profile,
        temp_root / profile,
        ignore=shutil.ignore_patterns(*ignore_names),
        dirs_exist_ok=True,
    )
    return str(temp_root)


def should_use_direct_profile(user_data_dir: str) -> bool:
    chrome_default_dir = Path(find_chrome_user_data_dir()).resolve()
    candidate_dir = Path(user_data_dir).resolve()
    return candidate_dir != chrome_default_dir


def find_local_chromedriver() -> Path | None:
    """Find an existing Windows ChromeDriver before attempting a download."""
    resource_dir = get_resource_dir()
    external_resources_dir = get_external_resources_dir()
    direct_candidates = (
        external_resources_dir / "ChromeDriver" / "chromedriver.exe",
        resource_dir / "ChromeDriver" / "chromedriver.exe",
        resource_dir / "chromedriver.exe",
        Path.cwd() / "chromedriver.exe",
    )
    for candidate in direct_candidates:
        if candidate.is_file():
            return candidate

    cache_root = Path.home() / ".wdm" / "drivers" / "chromedriver"
    if not cache_root.is_dir():
        return None

    cached_drivers = [path for path in cache_root.rglob("chromedriver.exe") if path.is_file()]
    if not cached_drivers:
        return None

    return max(cached_drivers, key=lambda path: path.stat().st_mtime)


def make_chrome_driver(user_data_dir: str | None = None, profile: str = "Default"):
    if not SELENIUM_AVAILABLE:
        raise BrowserStartError("selenium 未安装")

    options = Options()
    temp_user_data_dir = None
    if user_data_dir:
        source_root = Path(user_data_dir)
        source_profile = source_root / profile
        if not source_root.exists():
            raise BrowserStartError(f"找不到 Chrome 用户目录: {user_data_dir}")
        if not source_profile.exists():
            source_root.mkdir(parents=True, exist_ok=True)
            source_profile.mkdir(parents=True, exist_ok=True)
        use_direct_profile = should_use_direct_profile(user_data_dir)
        if use_direct_profile:
            options.add_argument(f"--user-data-dir={source_root}")
        else:
            temp_user_data_dir = copy_chrome_profile(user_data_dir, profile)
            options.add_argument(f"--user-data-dir={temp_user_data_dir}")
        options.add_argument(f"--profile-directory={profile}")
        log.warning("Selenium Chrome 用户目录: %s", source_root if use_direct_profile else temp_user_data_dir)
        log.warning("Selenium Chrome profile: %s", profile)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")

    try:
        local_driver = find_local_chromedriver()
        if local_driver:
            log.warning("使用本机 ChromeDriver: %s", local_driver)
            service = Service(str(local_driver))
            driver = webdriver.Chrome(service=service, options=options)
        elif WDM_AVAILABLE:
            log.warning("未找到本机 ChromeDriver，正在下载匹配版本。")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options)
    except WebDriverException as exc:
        raise BrowserStartError(
            "Chrome 启动失败，可能是 profile 正被其它 Chrome 窗口占用。请先关闭正在使用同一用户目录的 Chrome 窗口后再运行。"
            f" 原始错误: {exc}"
        ) from exc

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver._potato_temp_user_data_dir = temp_user_data_dir
    return driver


def load_page_source(url: str, driver, session: requests.Session) -> str:
    if driver:
        try:
            driver.get(url)
            ensure_driver_on_url(driver, url)
            wait_until_page_ready(driver, url)
            return driver.page_source
        except WebDriverException:
            pass
    return fetch_html(url, session) or ""


def ensure_driver_on_url(driver, url: str) -> None:
    """Chrome 偶尔停在新标签页时，强制再跳一次目标链接。"""
    current = (driver.current_url or "").lower()
    if current.startswith("chrome://") or current in {"about:blank", "data:,"}:
        driver.execute_script("window.location.href = arguments[0];", url)


def wait_until_page_ready(driver, url: str) -> None:
    """遇到明显失败页时刷新，最多尝试 5 次。"""
    for attempt in range(MAX_PAGE_REFRESHES + 1):
        time.sleep(3)
        ensure_driver_on_url(driver, url)
        page_text = driver.execute_script("return document.body ? document.body.innerText : '';") or ""
        if not is_bad_page(page_text):
            human_scroll(driver)
            return
        if attempt < MAX_PAGE_REFRESHES:
            log.warning("页面未加载成功，正在刷新 %d/%d", attempt + 1, MAX_PAGE_REFRESHES)
            driver.get(url)
    log.warning("页面刷新 %d 次后仍未成功，跳过刷新继续处理。", MAX_PAGE_REFRESHES)


def is_bad_page(text: str) -> bool:
    bad_markers = [
        "出错了",
        "请稍后重试",
        "连接到互联网",
        "你没有联网",
        "No internet",
        "Something went wrong",
        "Try again",
    ]
    return any(marker.lower() in (text or "").lower() for marker in bad_markers)


def human_scroll(driver) -> None:
    """轻量模拟真人浏览，避免页面完全停留在首屏。"""
    for _ in range(random.randint(2, 5)):
        driver.execute_script(f"window.scrollBy(0, {random.randint(250, 650)});")
        time.sleep(random.uniform(0.5, 1.2))
    if random.random() < 0.35:
        driver.execute_script(f"window.scrollBy(0, -{random.randint(120, 320)});")
        time.sleep(random.uniform(0.4, 0.9))


def normalize_external_link(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        url = "https://" + url.strip().lstrip("/")
        parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return clean or None


def is_low_value_external_link(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host in LOW_VALUE_HOSTS:
        return True
    return any(word in host for word in ["amazon.", "amzn."])


def extract_instagram_external_links(page: str) -> list[str]:
    matches = re.findall(r'"external_url"\s*:\s*"([^\"]+)"', page)
    matches += re.findall(r'linktr\.ee/[^\"\s<]+', page)
    return [unquote(item.replace("\\/", "/")) for item in matches]


def extract_tiktok_external_links(page: str) -> list[str]:
    matches = re.findall(r'"bioLink"\s*:\s*\{.*?"link"\s*:\s*"([^\"]+)"', page)
    return [unquote(item.replace("\\/", "/")) for item in matches]


def extract_youtube_external_links(page: str) -> list[str]:
    matches = re.findall(r'https?://[^\"\s<]+', page)
    return [item for item in matches if detect_platform(item) == "Unknown"]


def extract_external_links(platform: str, page: str) -> list[str]:
    if platform == "Instagram":
        raw = extract_instagram_external_links(page)
    elif platform == "TikTok":
        raw = extract_tiktok_external_links(page)
    elif platform == "YouTube":
        raw = extract_youtube_external_links(page)
    else:
        raw = []

    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        normalized = normalize_external_link(item)
        if not normalized or is_low_value_external_link(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result[:MAX_EXTERNAL_LINKS]


def extract_priority_links_from_page(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for tag in soup.find_all("a", href=True):
        href = urljoin(base_url, tag["href"])
        text = (tag.get_text(" ", strip=True) or "").lower()
        url = normalize_external_link(href)
        if not url or is_low_value_external_link(url):
            continue
        score = 0
        for word in EXTERNAL_PRIORITY_WORDS:
            if word in text or word in url.lower():
                score += 10
        if score > 0:
            candidates.append((score, url))
    candidates.sort(key=lambda item: item[0], reverse=True)
    ordered: list[str] = []
    seen: set[str] = set()
    for _, url in candidates:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered[:MAX_PRIORITY_LINKS]


def classify_external_email(email: str, source_url: str, html: str) -> str:
    lower = email.lower()
    if lower.startswith(("support@", "noreply@", "no-reply@", "privacy@", "legal@", "admin@")):
        return "低"
    host = urlparse(source_url).netloc.lower()
    if host and lower.endswith(host.replace("www.", "")):
        return "高"
    if any(word in html.lower() for word in ["contact", "contato", "business", "comercial", "parceria"]):
        return "中"
    return "中"


def choose_best_external_email(candidates: list[dict]) -> dict:
    if not candidates:
        return {"email": "", "source": "", "confidence": "", "status": "未发现外链邮箱"}
    rank = {"高": 0, "中": 1, "低": 2}
    best = sorted(candidates, key=lambda item: (rank.get(item["confidence"], 9), len(item["email"])))[0]
    return {
        "email": best["email"],
        "source": best["source"],
        "confidence": best["confidence"],
        "status": "已通过外链补抓",
    }


def scrape_external_link_emails(platform: str, page: str, session: requests.Session) -> dict:
    links = extract_external_links(platform, page)
    if not links:
        return {"email": "", "link": "", "source": "", "status": "未发现外链"}

    candidates: list[dict] = []
    for link in links:
        html = fetch_html(link, session)
        if not html:
            continue

        emails = choose_best_email(extract_mailto_emails(html) + extract_emails_from_text(html))
        if emails:
            candidates.extend({"email": email, "source": link, "confidence": classify_external_email(email, link, html)} for email in emails)
            continue

        for child in extract_priority_links_from_page(link, html):
            child_html = fetch_html(child, session)
            if not child_html:
                continue
            emails = choose_best_email(extract_mailto_emails(child_html) + extract_emails_from_text(child_html))
            if emails:
                candidates.extend({"email": email, "source": child, "confidence": classify_external_email(email, child, child_html)} for email in emails)

    best = choose_best_external_email(candidates)
    return {
        "email": best["email"],
        "link": links[0],
        "source": best["source"],
        "status": best["status"],
    }


def collect_page_emails_with_external_fallback(platform: str, page: str, session: requests.Session | None) -> tuple[list[str], dict]:
    emails = choose_best_email(extract_mailto_emails(page) + extract_emails_from_text(page))
    external = {"email": "", "link": "", "source": "", "status": ""}
    if not emails and session:
        external = scrape_external_link_emails(platform, page, session)
        if external["email"]:
            emails = [external["email"]]
    return emails, external


def _meta_content(page: str, attr_name: str, attr_value: str) -> str:
    pattern = rf'<meta[^>]+{attr_name}=["\']{re.escape(attr_value)}["\'][^>]+content=["\']([^"\']+)["\']'
    match = re.search(pattern, page or "", flags=re.I)
    if match:
        return html.unescape(match.group(1)).strip()
    pattern = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+{attr_name}=["\']{re.escape(attr_value)}["\']'
    match = re.search(pattern, page or "", flags=re.I)
    return html.unescape(match.group(1)).strip() if match else ""


def _title_text(page: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page or "", flags=re.I | re.S)
    if not match:
        return ""
    return re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()


def _extract_json_string(page: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, page or "", flags=re.I)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _clean_creator_name(value: str, platform: str) -> str:
    value = re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()
    if not value:
        return ""
    if platform == "TikTok":
        value = re.sub(r"\s*(\|\s*TikTok|on TikTok.*)$", "", value, flags=re.I).strip()
    elif platform == "Instagram":
        value = re.sub(r"\s*\(@[^)]+\)\s*.*$", "", value).strip()
        value = re.sub(r"\s*(•|on Instagram.*|Instagram photos.*)$", "", value, flags=re.I).strip()
    elif platform == "YouTube":
        value = re.sub(r"\s*-\s*YouTube.*$", "", value, flags=re.I).strip()
        value = re.sub(r"\s*\|\s*YouTube.*$", "", value, flags=re.I).strip()
    if value in {"Instagram", "TikTok", "YouTube"}:
        return ""
    return value


def extract_creator_name(platform: str, page: str) -> str:
    candidates: list[str] = []
    if platform == "TikTok":
        candidates.extend([
            _extract_json_string(page, [r'"nickname"\s*:\s*"([^"]+)"', r'"displayName"\s*:\s*"([^"]+)"']),
            _meta_content(page, "property", "og:title"),
            _meta_content(page, "name", "twitter:title"),
            _title_text(page),
        ])
    elif platform == "Instagram":
        candidates.extend([
            _extract_json_string(page, [r'"full_name"\s*:\s*"([^"]+)"']),
            _meta_content(page, "property", "og:title"),
            _meta_content(page, "name", "title"),
            _title_text(page),
        ])
    elif platform == "YouTube":
        candidates.extend([
            _extract_json_string(page, [r'"channelName"\s*:\s*"([^"]+)"', r'"ownerChannelName"\s*:\s*"([^"]+)"']),
            _meta_content(page, "property", "og:title"),
            _meta_content(page, "name", "title"),
            _title_text(page),
        ])

    for item in candidates:
        cleaned = _clean_creator_name(item, platform)
        if cleaned:
            return cleaned
    return ""


def extract_latest_publish_date(text: str) -> str:
    for pattern in LATEST_DATE_PATTERNS:
        match = pattern.search(text or "")
        if not match:
            continue
        value = match.group(1)
        if len(value) == 10 and value.isdigit():
            try:
                return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                continue
        return value
    return ""


def scrape_instagram(url: str, driver=None, session=None) -> dict:
    page = load_page_source(url, driver, session)
    emails, external = collect_page_emails_with_external_fallback("Instagram", page, session)
    return build_result(
        url=url,
        platform="Instagram",
        name=extract_creator_name("Instagram", page),
        emails=emails,
        email_source="主页" if emails and not external["email"] else ("外链" if external["email"] else ""),
        external_link=external["link"],
        external_source=external["source"],
        latest_publish_date=extract_latest_publish_date(page),
    )


def scrape_tiktok(url: str, driver=None, session=None) -> dict:
    page = load_page_source(url, driver, session)
    emails, external = collect_page_emails_with_external_fallback("TikTok", page, session)
    return build_result(
        url=url,
        platform="TikTok",
        name=extract_creator_name("TikTok", page),
        emails=emails,
        email_source="主页" if emails and not external["email"] else ("外链" if external["email"] else ""),
        external_link=external["link"],
        external_source=external["source"],
        latest_publish_date=extract_latest_publish_date(page),
    )


def scrape_youtube(url: str, driver=None, session=None) -> dict:
    about_url = url.rstrip("/") + "/about"
    page = load_page_source(about_url, driver, session)
    emails, external = collect_page_emails_with_external_fallback("YouTube", page, session)
    return build_result(
        url=url,
        platform="YouTube",
        name=extract_creator_name("YouTube", page),
        emails=emails,
        email_source="主页" if emails and not external["email"] else ("外链" if external["email"] else ""),
        external_link=external["link"],
        external_source=external["source"],
        latest_publish_date=extract_latest_publish_date(page),
    )


def normalize_follower_count(value: object) -> str:
    """Return a compact K/M display value, or an empty string for invalid input."""
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return ""
    match = FOLLOWER_COUNT_PATTERN.fullmatch(raw)
    if not match:
        return ""
    number_text, suffix = match.groups()
    if not suffix and "." in number_text:
        return ""
    try:
        number = Decimal(number_text)
    except InvalidOperation:
        return ""
    multiplier = {"k": 1000, "m": 1_000_000}.get((suffix or "").lower(), 1)
    count = number * multiplier
    if count != count.to_integral_value() or count < 0:
        return ""
    count = int(count)
    if count >= 1_000_000:
        compact = (Decimal(count) / Decimal(1_000_000)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{format(compact, 'f').rstrip('0').rstrip('.')}M"
    if count >= 1000:
        compact = (Decimal(count) / Decimal(1000)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{format(compact, 'f').rstrip('0').rstrip('.')}K"
    return str(count)


def build_result(*, url: str, platform: str, name: str = "", emails: list[str] | None = None, email_source: str = "", external_link: str = "", external_source: str = "", latest_publish_date: str = "", follower_count: str = "", status: str = "ok", whatsapp: str = "", note: str = "", data_status: str = "待检查", last_modified_at: str = "") -> dict:
    unique_emails = clean_email_candidates(emails or [])
    return {
        "url": url,
        "platform": platform,
        "name": str(name or "").strip(),
        "emails": unique_emails,
        "email_display": ", ".join(unique_emails) if unique_emails else NO_EMAIL,
        "email_source": email_source,
        "external_link": external_link,
        "external_source": external_source,
        "latest_publish_date": latest_publish_date,
        "follower_count": normalize_follower_count(follower_count),
        "status": status,
        "whatsapp": str(whatsapp or "").strip(),
        "note": str(note or ""),
        "data_status": str(data_status or "待检查").strip() or "待检查",
        "last_modified_at": str(last_modified_at or "").strip(),
    }


def result_to_row(result: dict) -> dict:
    return {
        FIELD_URL: result["url"],
        FIELD_PLATFORM: result["platform"],
        FIELD_NAME: result["name"],
        FIELD_EMAIL: result["email_display"],
        FIELD_EMAIL_SOURCE: result["email_source"],
        FIELD_EXTERNAL_LINK: result["external_link"],
        FIELD_EXTERNAL_SOURCE: result["external_source"],
        FIELD_LATEST_DATE: result["latest_publish_date"],
        FIELD_FOLLOWER_COUNT: result.get("follower_count", ""),
        FIELD_STATUS: "完成" if result["status"] == "ok" else result["status"],
        FIELD_WHATSAPP: result.get("whatsapp", ""),
        FIELD_NOTE: result.get("note", ""),
        FIELD_DATA_STATUS: result.get("data_status", "待检查"),
        FIELD_LAST_MODIFIED_AT: result.get("last_modified_at", ""),
    }


def row_to_result(row: dict) -> dict:
    email_display = str(row.get(FIELD_EMAIL, NO_EMAIL) or "").strip()
    result = build_result(
        url=row.get(FIELD_URL, ""),
        platform=row.get(FIELD_PLATFORM, "Unknown"),
        name=row.get(FIELD_NAME, ""),
        emails=[] if email_display in ("", NO_EMAIL) else [item.strip() for item in email_display.split(",") if item.strip()],
        email_source=row.get(FIELD_EMAIL_SOURCE, ""),
        external_link=row.get(FIELD_EXTERNAL_LINK, ""),
        external_source=row.get(FIELD_EXTERNAL_SOURCE, ""),
        latest_publish_date=row.get(FIELD_LATEST_DATE, ""),
        follower_count=row.get(FIELD_FOLLOWER_COUNT, ""),
        status="ok" if row.get(FIELD_STATUS, "") == "完成" else row.get(FIELD_STATUS, "error"),
        whatsapp=row.get(FIELD_WHATSAPP, ""),
        note=row.get(FIELD_NOTE, ""),
        data_status=row.get(FIELD_DATA_STATUS, "待检查"),
        last_modified_at=row.get(FIELD_LAST_MODIFIED_AT, ""),
    )
    # An explicit manual email clear must survive the CSV round-trip.
    if email_display == "":
        result["email_display"] = ""
    return result


def load_progress(progress_file: str) -> dict:
    done: dict[str, dict] = {}
    path = Path(progress_file)
    if not path.exists():
        return done
    with open(path, encoding="utf-8-sig", newline="", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get(FIELD_STATUS) != "完成":
                continue
            result = row_to_result(row)
            if result["url"]:
                done[result["url"]] = result
    return done


def ensure_progress_review_fields(progress_file: str) -> None:
    """Add audit columns to legacy task progress files without dropping existing data."""
    path = Path(progress_file)
    if not path.exists():
        return

    with open(path, encoding="utf-8-sig", newline="", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        existing_fields = reader.fieldnames or []
        if all(field in existing_fields for field in PROGRESS_FIELDS):
            return
        rows = list(reader)

    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with open(temp_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROGRESS_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row.setdefault(FIELD_WHATSAPP, "")
            row.setdefault(FIELD_NOTE, "")
            row.setdefault(FIELD_FOLLOWER_COUNT, "")
            row.setdefault(FIELD_DATA_STATUS, "待检查")
            row.setdefault(FIELD_LAST_MODIFIED_AT, "")
            writer.writerow(row)
    os.replace(temp_path, path)


def load_existing_progress_by_uid(progress_file: str) -> dict[str, dict]:
    """Load all historical task rows, including failed rows that may have manual edits."""
    path = Path(progress_file)
    if not path.exists():
        return {}

    existing: dict[str, dict] = {}
    with open(path, encoding="utf-8-sig", newline="", errors="ignore") as handle:
        for row in csv.DictReader(handle):
            result = row_to_result(row)
            account_uid = build_creator_uid(result)
            if account_uid:
                existing[account_uid] = result
    return existing


def load_manual_fields_by_uid(progress_file: str) -> dict[str, set[str]]:
    """Reuse review history to protect explicitly edited values during a later crawl."""
    modifications_path = Path(progress_file).parent / "modifications.json"
    if not modifications_path.exists():
        return {}
    try:
        entries = json.loads(modifications_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("无法读取审核修改记录，继续抓取将仅保留非空旧值: %s", exc)
        return {}

    manual_fields: dict[str, set[str]] = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        account_uid = str(entry.get("account_uid") or "").strip()
        modified_fields = entry.get("modified_fields")
        if not account_uid or not isinstance(modified_fields, dict):
            continue
        protected = {field for field in modified_fields if field in (FIELD_NAME, FIELD_EMAIL, FIELD_FOLLOWER_COUNT)}
        if protected:
            manual_fields.setdefault(account_uid, set()).update(protected)
    return manual_fields


def _set_result_email(result: dict, email_display: str) -> None:
    value = str(email_display or "").strip()
    result["email_display"] = value
    result["emails"] = [] if value in ("", NO_EMAIL) else clean_email_candidates(
        [item.strip() for item in value.split(",") if item.strip()]
    )


def merge_scrape_result_with_review(existing: dict | None, fresh: dict, manual_fields: set[str] | None = None) -> dict:
    """Keep task review data while accepting better non-manual crawler values."""
    if not existing:
        return fresh

    manual_fields = manual_fields or set()
    merged = dict(fresh)

    old_name = str(existing.get("name") or "").strip()
    if FIELD_NAME in manual_fields or (not merged.get("name") and old_name):
        merged["name"] = old_name

    old_email = str(existing.get("email_display") or "").strip()
    fresh_email = str(merged.get("email_display") or "").strip()
    if FIELD_EMAIL in manual_fields or (fresh_email in ("", NO_EMAIL) and old_email not in ("", NO_EMAIL)):
        _set_result_email(merged, old_email)
        merged["email_source"] = existing.get("email_source", "")

    old_follower_count = str(existing.get("follower_count") or "").strip()
    if FIELD_FOLLOWER_COUNT in manual_fields or (not merged.get("follower_count") and old_follower_count):
        merged["follower_count"] = old_follower_count

    if not merged.get("latest_publish_date") and existing.get("latest_publish_date"):
        merged["latest_publish_date"] = existing["latest_publish_date"]

    # These fields are audit-owned: crawler output must never overwrite them.
    merged["whatsapp"] = existing.get("whatsapp", "")
    merged["note"] = existing.get("note", "")
    merged["data_status"] = existing.get("data_status", "待检查") or "待检查"
    merged["last_modified_at"] = existing.get("last_modified_at", "")
    return merged


def save_progress(result: dict, progress_file: str) -> None:
    path = Path(progress_file)
    ensure_progress_review_fields(progress_file)
    file_exists = path.exists()
    with open(path, "a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROGRESS_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(result_to_row(result))
        handle.flush()
        os.fsync(handle.fileno())


def _read_task_control(task_file: str | None) -> dict:
    """Read optional task controls without letting a transient file read stop scraping."""
    if not task_file:
        return {}
    try:
        data = json.loads(Path(task_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def wait_for_task_control(task_file: str | None) -> bool:
    """Pause between creators or end gracefully when the task requests a stop."""
    announced_pause = False
    while task_file:
        control = _read_task_control(task_file)
        if control.get("stop_requested"):
            log.warning("收到停止请求，正在保存当前进度。")
            return False
        if not control.get("pause_requested"):
            if announced_pause:
                log.warning("任务恢复运行。")
            return True
        if not announced_pause:
            log.warning("任务已暂停，等待继续。")
            announced_pause = True
        time.sleep(0.5)
    return True


def scrape_all(
    urls: list[str], driver=None, progress_file: str = PROGRESS_FILE, task_file: str | None = None,
) -> list[dict]:
    session = make_session()
    ensure_progress_review_fields(progress_file)
    done = load_progress(progress_file)
    existing_by_uid = load_existing_progress_by_uid(progress_file)
    manual_fields_by_uid = load_manual_fields_by_uid(progress_file)
    results = [done[url] for url in urls if url in done]
    pending = [url for url in urls if url not in done]

    for index, url in enumerate(pending):
        if not wait_for_task_control(task_file):
            break
        platform = detect_platform(url)
        if platform == "Instagram":
            result = scrape_instagram(url, driver=driver, session=session)
        elif platform == "TikTok":
            result = scrape_tiktok(url, driver=driver, session=session)
        elif platform == "YouTube":
            result = scrape_youtube(url, driver=driver, session=session)
        else:
            result = build_result(url=url, platform="Unknown", status="unsupported")

        account_uid = build_creator_uid(result)
        result = merge_scrape_result_with_review(
            existing_by_uid.get(account_uid),
            result,
            manual_fields_by_uid.get(account_uid),
        )
        results.append(result)
        save_progress(result, progress_file)
        log.success("[%s] %s | %s -> %s", result["platform"], result.get("name", ""), result["url"], result["email_display"])

        if index < len(pending) - 1:
            time.sleep(random.uniform(*REQUEST_DELAY))
    return results


def read_text_file_with_fallback(path: str) -> str:
    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
    for encoding in encodings:
        try:
            return Path(path).read_text(encoding=encoding, errors="ignore")
        except Exception:
            continue
    raise RuntimeError(f"无法读取文件: {path}")


def read_from_file(path: str) -> list[str]:
    content = read_text_file_with_fallback(path)
    return [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]


def read_from_excel(path: str, column: str) -> list[str]:
    if not PANDAS_AVAILABLE:
        sys.exit("需要安装 pandas 和 openpyxl")
    if path.endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    else:
        for encoding in ["utf-8-sig", "utf-8", "gb18030", "gbk"]:
            try:
                df = pd.read_csv(path, encoding=encoding)
                break
            except Exception:
                df = None
        if df is None:
            sys.exit("CSV 读取失败")
    if column not in df.columns:
        sys.exit(f"找不到列: {column}")
    return df[column].dropna().astype(str).tolist()


def read_interactive() -> list[str]:
    print("请一行一个粘贴达人主页链接，空行结束：")
    urls: list[str] = []
    while True:
        line = input().strip()
        if not line:
            break
        urls.append(line)
    return urls


def _four_table_access_token(config: dict) -> str:
    token_resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": config["app_id"], "app_secret": config["app_secret"]},
        timeout=10,
    )
    access_token = token_resp.json().get("tenant_access_token")
    if not access_token:
        raise RuntimeError(f"Feishu token 获取失败: {token_resp.text}")
    return access_token


def _four_table_list_records(table_id: str, config: dict, headers: dict) -> list[dict]:
    list_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{config['app_token']}/tables/{table_id}/records"
    records: list[dict] = []
    page_token = ""

    while True:
        params = {"page_size": CRM_RECORD_PAGE_SIZE}
        if page_token:
            params["page_token"] = page_token
        response = requests.get(list_url, headers=headers, params=params, timeout=15)
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu four-table read error: {data}")
        payload = data.get("data") or {}
        records.extend(payload.get("items") or [])
        if not payload.get("has_more"):
            return records
        page_token = str(payload.get("page_token") or "").strip()
        if not page_token:
            return records


def fetch_existing_creator_accounts(config: dict, *, include_duplicates: bool = False):
    """Read the account table and index records by the stable account UID."""
    access_token = _four_table_access_token(config)
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    indexed: dict[str, dict] = {}
    duplicate_uids: set[str] = set()
    for item in _four_table_list_records(config["account_table_id"], config, headers):
        fields = item.get("fields") or {}
        account_uid = str(fields.get(FOUR_TABLE_ACCOUNT_FIELD_UID) or "").strip()
        if not account_uid:
            continue
        if account_uid in indexed:
            duplicate_uids.add(account_uid)
            log.warning("达人账号表中发现重复账号唯一ID，已标记为异常：%s", account_uid)
            continue
        indexed[account_uid] = {"record_id": item.get("record_id", ""), "fields": fields}
    log.warning("达人账号表只读索引完成：共载入 %d 条唯一账号，重复 UID %d 条", len(indexed), len(duplicate_uids))
    if include_duplicates:
        return indexed, duplicate_uids
    return indexed


def fetch_existing_creators(config: dict) -> dict[str, dict]:
    """Read all creator records for conservative candidate detection."""
    access_token = _four_table_access_token(config)
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    indexed: dict[str, dict] = {}
    for item in _four_table_list_records(config["creator_table_id"], config, headers):
        record_id = str(item.get("record_id") or "").strip()
        if record_id:
            indexed[record_id] = {"record_id": record_id, "fields": item.get("fields") or {}}
    log.warning("达人表只读载入完成：共载入 %d 条达人", len(indexed))
    return indexed


def _four_table_creator_display_name(result: dict) -> str:
    name = _crm_result_name(result)
    if name:
        return name
    normalized_url = _normalize_crm_profile_url(result.get("url") or "")
    path_parts = [part for part in urlparse(normalized_url).path.split("/") if part]
    handle = path_parts[-1].lstrip("@") if path_parts else "unknown"
    platform = str(result.get("platform") or "Unknown").strip() or "Unknown"
    return f"未命名-{platform}-{handle}"


def _four_table_scrape_status(result: dict) -> str:
    status = str(result.get("status") or "").strip().lower()
    if status == "ok":
        return "完成"
    if status == "unsupported":
        return "不支持"
    return "失败"


def _four_table_account_fields(
    result: dict,
    *,
    creator_record_id: str = "",
    candidate_record_ids: list[str] | None = None,
    data_source: str = FOUR_TABLE_DEFAULT_SOURCE,
    email_source: str = "",
) -> dict:
    account_uid = build_creator_uid(result)
    profile_url = _normalize_crm_profile_url(result.get("url") or "")
    fields = {
        FOUR_TABLE_ACCOUNT_FIELD_UID: account_uid,
        FOUR_TABLE_ACCOUNT_FIELD_PLATFORM: str(result.get("platform") or "").strip(),
        FOUR_TABLE_ACCOUNT_FIELD_PROFILE_URL: {"link": profile_url, "text": profile_url} if profile_url else "",
        FOUR_TABLE_ACCOUNT_FIELD_EMAIL: _crm_result_email(result),
        FOUR_TABLE_ACCOUNT_FIELD_LAST_SCRAPED_AT: _crm_now_ms(),
        FOUR_TABLE_ACCOUNT_FIELD_SOURCE: data_source or FOUR_TABLE_DEFAULT_SOURCE,
        FOUR_TABLE_ACCOUNT_FIELD_SCRAPE_STATUS: _four_table_scrape_status(result),
    }
    if _crm_result_email(result):
        fields[FOUR_TABLE_ACCOUNT_FIELD_EMAIL_SOURCE] = email_source
    latest_publish_at = _crm_date_to_ms(result.get("latest_publish_date") or "")
    if latest_publish_at is not None:
        fields[FOUR_TABLE_ACCOUNT_FIELD_LATEST_PUBLISH_AT] = latest_publish_at
    follower_count = _crm_result_follower_count(result)
    if follower_count is not None:
        fields[FOUR_TABLE_ACCOUNT_FIELD_FOLLOWER_COUNT] = follower_count
    if creator_record_id:
        fields[FOUR_TABLE_ACCOUNT_FIELD_CREATOR] = [creator_record_id]
        fields[FOUR_TABLE_ACCOUNT_FIELD_OWNERSHIP_STATUS] = "已归属"
    elif candidate_record_ids:
        fields[FOUR_TABLE_ACCOUNT_FIELD_CANDIDATES] = candidate_record_ids
        fields[FOUR_TABLE_ACCOUNT_FIELD_OWNERSHIP_STATUS] = "待确认"
    else:
        fields[FOUR_TABLE_ACCOUNT_FIELD_OWNERSHIP_STATUS] = "未归属"
    return fields


def _four_table_account_update_fields(result: dict, *, email_source: str = "") -> dict:
    """Only refresh scraper-owned account fields; leave ownership and notes untouched."""
    fields = _four_table_account_fields(result, email_source=email_source)
    for key in (
        FOUR_TABLE_ACCOUNT_FIELD_UID,
        FOUR_TABLE_ACCOUNT_FIELD_OWNERSHIP_STATUS,
        FOUR_TABLE_ACCOUNT_FIELD_CREATOR,
        FOUR_TABLE_ACCOUNT_FIELD_CANDIDATES,
    ):
        fields.pop(key, None)
    # A failed or empty extraction must not erase the account email in Feishu.
    if not _crm_result_email(result):
        fields.pop(FOUR_TABLE_ACCOUNT_FIELD_EMAIL, None)
    return fields


def _crm_result_follower_count(result: dict) -> str | None:
    value = normalize_follower_count(result.get("follower_count"))
    return value or None


def _four_table_field_is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def _four_table_relation_record_ids(value) -> list[str]:
    """Read record IDs from either Feishu relation response shape."""
    if not isinstance(value, list):
        value = [value]
    record_ids: list[str] = []
    for item in value:
        record_id = str(
            item.get("record_id") if isinstance(item, dict) else item or ""
        ).strip()
        if record_id and record_id not in record_ids:
            record_ids.append(record_id)
    return record_ids


def _four_table_account_fill_empty_fields(
    existing_fields: dict, result: dict, data_source: str, email_source: str
) -> dict:
    """Only supplement blank account fields; never replace an existing final-database value."""
    candidates = _four_table_account_update_fields(result, email_source=email_source)
    candidates[FOUR_TABLE_ACCOUNT_FIELD_SOURCE] = data_source or FOUR_TABLE_DEFAULT_SOURCE
    fields = {
        field: value
        for field, value in candidates.items()
        if not _four_table_field_is_empty(value) and _four_table_field_is_empty(existing_fields.get(field))
    }
    # Email provenance only changes together with an actual email value.
    if FOUR_TABLE_ACCOUNT_FIELD_EMAIL not in fields:
        fields.pop(FOUR_TABLE_ACCOUNT_FIELD_EMAIL_SOURCE, None)
    return fields


def _protection_priority(source: str) -> int:
    return {
        "人工维护": 50,
        "人工录入": 40,
        "审核修改": 30,
        "系统补全": 20,
        "邮箱补全": 20,
        "人工+系统补充": 20,
        "人工补充": 20,
        "系统抓取": 10,
    }.get(str(source or "").strip(), 0)


def _email_is_protected(account_uid: str, data_protection: dict | None, data_source: str) -> bool:
    item = ((data_protection or {}).get(account_uid) or {}).get("邮箱")
    if not isinstance(item, dict) or not str(item.get("value") or "").strip():
        return False
    return _protection_priority(str(item.get("source") or "")) > _protection_priority(data_source)


def _four_table_sync_log(account_uid: str, data_source: str, updated_fields: dict, action: str) -> dict:
    return {
        "account_uid": account_uid,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "data_source": data_source,
        "updated_fields": list(updated_fields),
        "action": action,
    }


def _four_table_creator_fields(result: dict, *, source_contact_record_id: str = "") -> dict:
    fields = {
        FOUR_TABLE_CREATOR_FIELD_NAME: _four_table_creator_display_name(result),
        FOUR_TABLE_CREATOR_FIELD_ID: f"creator_{uuid.uuid7().hex}",
        FOUR_TABLE_CREATOR_FIELD_REGION: FOUR_TABLE_DEFAULT_REGION,
        FOUR_TABLE_CREATOR_FIELD_LANGUAGE: FOUR_TABLE_DEFAULT_LANGUAGE,
        FOUR_TABLE_CREATOR_FIELD_STAGE: FOUR_TABLE_DEFAULT_STAGE,
        FOUR_TABLE_CREATOR_FIELD_OWNER: "",
    }
    for field, value in (
        (FOUR_TABLE_CREATOR_FIELD_WHATSAPP, str(result.get("whatsapp") or "").strip()),
        (FOUR_TABLE_CREATOR_FIELD_NOTE, str(result.get("note") or "").strip()),
    ):
        if value:
            fields[field] = value
    if source_contact_record_id:
        fields[FOUR_TABLE_CREATOR_FIELD_SOURCE_CONTACT] = [source_contact_record_id]
    return fields


def _four_table_creator_fill_empty_fields(existing_fields: dict, result: dict) -> dict:
    """Supplement only empty creator fields; never replace Feishu-maintained values."""
    candidates = {
        FOUR_TABLE_CREATOR_FIELD_NAME: _crm_result_name(result),
        FOUR_TABLE_CREATOR_FIELD_WHATSAPP: str(result.get("whatsapp") or "").strip(),
        FOUR_TABLE_CREATOR_FIELD_NOTE: str(result.get("note") or "").strip(),
    }
    return {
        field: value
        for field, value in candidates.items()
        if value and _four_table_field_is_empty(existing_fields.get(field))
    }


def _four_table_creator_candidates(result: dict, creators: dict[str, dict]) -> list[str]:
    """Use only an exact non-empty creator-name match as a test-stage candidate signal."""
    name = _crm_result_name(result).casefold()
    if not name:
        return []
    return [
        record_id
        for record_id, creator in creators.items()
        if str((creator.get("fields") or {}).get(FOUR_TABLE_CREATOR_FIELD_NAME) or "").strip().casefold() == name
    ]


def _four_table_batch_create(table_id: str, fields: dict, config: dict, headers: dict) -> str:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{config['app_token']}/tables/{table_id}/records/batch_create"
    response = requests.post(url, headers=headers, json={"records": [{"fields": fields}]}, timeout=15)
    data = response.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu four-table create error: {data}")
    records = ((data.get("data") or {}).get("records") or [])
    record_id = str((records[0] if records else {}).get("record_id") or "").strip()
    if not record_id:
        raise RuntimeError(f"Feishu four-table create returned no record_id: {data}")
    return record_id


def _four_table_batch_update(table_id: str, record_id: str, fields: dict, config: dict, headers: dict) -> None:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{config['app_token']}/tables/{table_id}/records/batch_update"
    response = requests.post(url, headers=headers, json={"records": [{"record_id": record_id, "fields": fields}]}, timeout=15)
    data = response.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu four-table update error: {data}")


def push_to_feishu_four_tables(
    results: list[dict], config: dict, *, email_recheck_only: bool = False,
    data_source: str = FOUR_TABLE_DEFAULT_SOURCE, email_source: str = "",
    data_protection: dict | None = None, source_contact_record_id: str = "",
) -> dict[str, int | list[str]]:
    """Synchronize all supplied scrape results to the creator and account tables."""
    summary: dict[str, int | list[str]] = {
        "created_creators": 0,
        "created_accounts": 0,
        "updated_accounts": 0,
        "updated_creators": 0,
        "skipped": 0,
        "errors": [],
        "sync_logs": [],
    }
    log.warning("抓取结果总数：%d", len(results))
    if not results:
        log.warning("没有可同步的抓取结果。")
        return summary

    required = ("app_id", "app_secret", "app_token", "account_table_id")
    if not email_recheck_only:
        required = (*required, "creator_table_id")
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"四表飞书配置不完整: {', '.join(missing)}")

    log.warning("四表同步处理数量：%d", len(results))
    log.warning("四表同步开始")
    account_index, duplicate_uids = fetch_existing_creator_accounts(config, include_duplicates=True)
    creator_index = {} if email_recheck_only else fetch_existing_creators(config)
    access_token = _four_table_access_token(config)
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    for result in results:
        account_uid = build_creator_uid(result)
        if not account_uid:
            summary["skipped"] += 1
            log.warning("四表同步跳过：账号唯一ID为空 -> %s", result.get("url") or "")
            continue
        if account_uid in duplicate_uids:
            summary["skipped"] += 1
            summary["errors"].append(f"duplicate_uid: {account_uid}")
            summary["sync_logs"].append(_four_table_sync_log(account_uid, data_source, {}, "duplicate_uid"))
            log.warning("四表同步跳过重复账号唯一ID：%s", account_uid)
            continue

        try:
            existing_account = account_index.get(account_uid)
            if email_recheck_only:
                if not existing_account:
                    summary["skipped"] += 1
                    log.warning("邮箱补全跳过：达人账号不存在 -> %s", account_uid)
                    summary["sync_logs"].append(_four_table_sync_log(account_uid, data_source, {}, "skipped_missing_account"))
                    continue
                existing_email = str((existing_account.get("fields") or {}).get(FOUR_TABLE_ACCOUNT_FIELD_EMAIL) or "").strip()
                extracted_email = _crm_result_email(result)
                if existing_email or not extracted_email or _email_is_protected(account_uid, data_protection, data_source):
                    summary["skipped"] += 1
                    action = "skipped_protected_email" if _email_is_protected(account_uid, data_protection, data_source) else "skipped"
                    summary["sync_logs"].append(_four_table_sync_log(account_uid, data_source, {}, action))
                    continue
                update_fields = {
                    FOUR_TABLE_ACCOUNT_FIELD_EMAIL: extracted_email,
                    FOUR_TABLE_ACCOUNT_FIELD_EMAIL_SOURCE: email_source,
                }
                if _four_table_field_is_empty((existing_account.get("fields") or {}).get(FOUR_TABLE_ACCOUNT_FIELD_SOURCE)):
                    update_fields[FOUR_TABLE_ACCOUNT_FIELD_SOURCE] = data_source
                _four_table_batch_update(
                    config["account_table_id"],
                    existing_account["record_id"],
                    update_fields,
                    config,
                    headers,
                )
                summary["updated_accounts"] += 1
                summary["sync_logs"].append(_four_table_sync_log(account_uid, data_source, update_fields, "updated"))
                continue
            if existing_account:
                update_fields = _four_table_account_fill_empty_fields(
                    existing_account.get("fields") or {}, result, data_source, email_source
                )
                if _email_is_protected(account_uid, data_protection, data_source):
                    update_fields.pop(FOUR_TABLE_ACCOUNT_FIELD_EMAIL, None)
                    update_fields.pop(FOUR_TABLE_ACCOUNT_FIELD_EMAIL_SOURCE, None)
                creator_update_fields: dict = {}
                creator_record_ids = _four_table_relation_record_ids(
                    (existing_account.get("fields") or {}).get(FOUR_TABLE_ACCOUNT_FIELD_CREATOR)
                )
                if len(creator_record_ids) == 1:
                    creator = creator_index.get(creator_record_ids[0])
                    if creator:
                        creator_update_fields = _four_table_creator_fill_empty_fields(
                            creator.get("fields") or {}, result
                        )

                if not update_fields and not creator_update_fields:
                    summary["skipped"] += 1
                    summary["sync_logs"].append(_four_table_sync_log(account_uid, data_source, {}, "skipped"))
                    continue
                if update_fields:
                    _four_table_batch_update(
                        config["account_table_id"],
                        existing_account["record_id"],
                        update_fields,
                        config,
                        headers,
                    )
                    summary["updated_accounts"] += 1
                if creator_update_fields:
                    creator_record_id = creator_record_ids[0]
                    _four_table_batch_update(
                        config["creator_table_id"],
                        creator_record_id,
                        creator_update_fields,
                        config,
                        headers,
                    )
                    creator_index[creator_record_id]["fields"].update(creator_update_fields)
                    summary["updated_creators"] += 1
                summary["sync_logs"].append(
                    _four_table_sync_log(
                        account_uid,
                        data_source,
                        {**update_fields, **creator_update_fields},
                        "updated",
                    )
                )
                continue

            candidate_record_ids = _four_table_creator_candidates(result, creator_index)
            if candidate_record_ids:
                _four_table_batch_create(
                    config["account_table_id"],
                    _four_table_account_fields(result, candidate_record_ids=candidate_record_ids, data_source=data_source, email_source=email_source),
                    config,
                    headers,
                )
                summary["created_accounts"] += 1
                summary["sync_logs"].append(_four_table_sync_log(account_uid, data_source, _four_table_account_fields(result, candidate_record_ids=candidate_record_ids, data_source=data_source, email_source=email_source), "created_account"))
                continue

            creator_fields = _four_table_creator_fields(
                result,
                source_contact_record_id=source_contact_record_id,
            )
            creator_record_id = _four_table_batch_create(config["creator_table_id"], creator_fields, config, headers)
            creator_index[creator_record_id] = {"record_id": creator_record_id, "fields": creator_fields}
            summary["created_creators"] += 1

            _four_table_batch_create(
                config["account_table_id"],
                _four_table_account_fields(result, creator_record_id=creator_record_id, data_source=data_source, email_source=email_source),
                config,
                headers,
            )
            summary["created_accounts"] += 1
            summary["sync_logs"].append(_four_table_sync_log(account_uid, data_source, _four_table_account_fields(result, creator_record_id=creator_record_id, data_source=data_source, email_source=email_source), "created_creator_and_account"))
        except Exception as exc:
            error = f"账号 {account_uid} 同步失败: {exc}"
            summary["errors"].append(error)
            summary["sync_logs"].append(_four_table_sync_log(account_uid, data_source, {}, "failed"))
            log.warning(error)

    log.warning(
        "四表同步完成：创建达人 %d，创建达人账号 %d，更新达人账号 %d，补充达人 %d，跳过 %d，错误数量 %d",
        summary["created_creators"],
        summary["created_accounts"],
        summary["updated_accounts"],
        summary["updated_creators"],
        summary["skipped"],
        len(summary["errors"]),
    )
    return summary


def build_output_rows(results: list[dict]) -> list[dict]:
    return [
        {field: result_to_row(item).get(field, "") for field in OUTPUT_FIELDS}
        for item in results
    ]


def write_sync_result(path: str | None, sync_status: str, summary: dict | None = None, sync_errors: list[str] | None = None) -> None:
    """Write a task-only handoff file without changing the sync implementation."""
    if not path:
        return
    result_path = Path(path)
    payload = {
        "sync_status": sync_status,
        "sync_summary": summary or {},
        "sync_errors": sync_errors or [],
    }
    temp_path = result_path.with_suffix(f"{result_path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(result_path)


def main() -> None:
    setup_console_encoding()

    parser = argparse.ArgumentParser(description="KOL联系助手邮箱抓取")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", help="txt 文件，一行一个链接")
    source.add_argument("--excel", help="xlsx / csv 文件")
    source.add_argument("--urls", nargs="+")
    parser.add_argument("--column", default="url")
    parser.add_argument("--chrome-dir", default=None)
    parser.add_argument("--chrome-profile", default="Default")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--progress-file", default=PROGRESS_FILE)
    parser.add_argument("--task-file", default=None, help="任务控制文件路径")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--feishu-app-id", default=None)
    parser.add_argument("--feishu-app-secret", default=None)
    parser.add_argument("--feishu-app-token", default=None)
    parser.add_argument("--feishu-table-id", default=None)
    parser.add_argument("--feishu-creator-table-id", default=None)
    parser.add_argument("--feishu-account-table-id", default=None)
    parser.add_argument("--four-table-sync", action="store_true")
    parser.add_argument("--no-feishu", action="store_true")
    parser.add_argument("--output", default="results.csv")
    parser.add_argument("--sync-result-file", default=None)
    args = parser.parse_args()

    if args.file:
        urls = read_from_file(args.file)
    elif args.excel:
        urls = read_from_excel(args.excel, args.column)
    elif args.urls:
        urls = args.urls
    else:
        urls = read_interactive()

    urls = normalize_urls(urls)
    if not urls:
        sys.exit("没有可处理的链接")

    if args.reset and Path(args.progress_file).exists():
        Path(args.progress_file).unlink()

    driver = None
    if not args.no_browser and SELENIUM_AVAILABLE:
        chrome_dir = args.chrome_dir or find_chrome_user_data_dir()
        log.warning("当前为有头模式。若同一用户目录的 Chrome 正在运行，请先关闭对应 Chrome 窗口后再运行。")
        log.warning("Selenium Chrome 用户目录: %s", chrome_dir)
        log.warning("Selenium Chrome profile: %s", args.chrome_profile)
        try:
            driver = make_chrome_driver(user_data_dir=chrome_dir, profile=args.chrome_profile)
            log.warning("Chrome 已启动，当前 profile: %s", args.chrome_profile)
        except Exception as exc:
            raise BrowserStartError(f"Chrome 启动失败: {exc}")

    try:
        results = scrape_all(
            urls,
            driver=driver,
            progress_file=args.progress_file,
            task_file=args.task_file,
        )
    finally:
        if driver:
            temp_user_data_dir = getattr(driver, "_potato_temp_user_data_dir", None)
            driver.quit()
            if temp_user_data_dir:
                shutil.rmtree(temp_user_data_dir, ignore_errors=True)

    print("\n" + "=" * 96)
    print(f"{FIELD_PLATFORM:<12} {FIELD_EMAIL:<36} {FIELD_LATEST_DATE:<14} {FIELD_URL}")
    print("=" * 96)
    for item in results:
        print(f"{item['platform']:<12} {item['email_display']:<36} {item['latest_publish_date']:<14} {item['url']}")
    print("=" * 96)
    found = sum(1 for item in results if item.get("emails"))
    print(f"\n使用的 Chrome profile: {args.chrome_profile}")
    print(f"找到邮箱: {found}/{len(results)}\n")
    if _read_task_control(args.task_file).get("stop_requested"):
        print("任务已停止，当前进度已保存。")
    else:
        print("任务完成。")

    rows = build_output_rows(results)
    if PANDAS_AVAILABLE:
        pd.DataFrame(rows, columns=OUTPUT_FIELDS).to_csv(args.output, index=False, encoding="utf-8-sig")
    else:
        with open(args.output, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    if not args.no_feishu:
        if args.four_table_sync:
            log.warning("同步模式：四表同步")
            cfg = {
                "app_id": args.feishu_app_id or os.getenv("FEISHU_APP_ID"),
                "app_secret": args.feishu_app_secret or os.getenv("FEISHU_APP_SECRET"),
                "app_token": args.feishu_app_token or os.getenv("FEISHU_APP_TOKEN"),
                "creator_table_id": args.feishu_creator_table_id or os.getenv("FEISHU_CREATOR_TABLE_ID"),
                "account_table_id": args.feishu_account_table_id or os.getenv("FEISHU_ACCOUNT_TABLE_ID"),
            }
            try:
                summary = push_to_feishu_four_tables(results, cfg)
            except Exception as exc:
                summary = {
                    "created_creators": 0,
                    "created_accounts": 0,
                    "updated_accounts": 0,
                    "skipped": 0,
                    "errors": [str(exc)],
                }
                log.warning("四表同步失败: %s", exc)

            sync_errors = [str(error) for error in summary.get("errors", [])]
            write_sync_result(
                args.sync_result_file,
                "success" if not sync_errors else "failed",
                summary,
                sync_errors,
            )

            log.warning("创建达人: %d", summary["created_creators"])
            log.warning("创建达人账号: %d", summary["created_accounts"])
            log.warning("更新达人账号: %d", summary["updated_accounts"])
            log.warning("跳过: %d", summary["skipped"])
            log.warning("错误数量: %d", len(summary["errors"]))
            for error in summary["errors"]:
                log.warning("错误: %s", error)
            log.warning("四表同步完成")
        else:
            log.warning("旧 CRM 同步已废弃，已跳过。请使用四表同步模式。")


if __name__ == "__main__":
    main()
