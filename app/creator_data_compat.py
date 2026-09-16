"""Compatibility boundary for creator data helpers owned by the scraper module.

Services use this narrow facade instead of depending on scraper runtime details.
The wrappers resolve attributes at call time so existing scraper patch points keep
working while the underlying helpers remain in their current module.
"""

from __future__ import annotations

import scraper as _scraper


FIELD_EMAIL = _scraper.FIELD_EMAIL
FIELD_EMAIL_SOURCE = _scraper.FIELD_EMAIL_SOURCE
FIELD_FOLLOWER_COUNT = _scraper.FIELD_FOLLOWER_COUNT
FIELD_ACCOUNT_NAME = _scraper.FIELD_ACCOUNT_NAME
FIELD_LAST_SCRAPE_TIME = _scraper.FIELD_LAST_SCRAPE_TIME
FIELD_NAME = _scraper.FIELD_NAME
FIELD_RETRY_COUNT = _scraper.FIELD_RETRY_COUNT
FIELD_SCRAPE_STATUS = _scraper.FIELD_SCRAPE_STATUS
FIELD_STATUS = _scraper.FIELD_STATUS
FIELD_STATUS_REASON = _scraper.FIELD_STATUS_REASON
FIELD_URL = _scraper.FIELD_URL
FOUR_TABLE_ACCOUNT_FIELD_EMAIL = _scraper.FOUR_TABLE_ACCOUNT_FIELD_EMAIL
NO_EMAIL = _scraper.NO_EMAIL


def build_creator_uid(*args, **kwargs):
    return _scraper.build_creator_uid(*args, **kwargs)


def build_result(*args, **kwargs):
    return _scraper.build_result(*args, **kwargs)


def detect_platform(*args, **kwargs):
    return _scraper.detect_platform(*args, **kwargs)


def normalize_follower_count(*args, **kwargs):
    return _scraper.normalize_follower_count(*args, **kwargs)


def normalize_link_record(*args, **kwargs):
    return _scraper.normalize_link_record(*args, **kwargs)


def push_to_feishu_four_tables(*args, **kwargs):
    return _scraper.push_to_feishu_four_tables(*args, **kwargs)


def row_to_result(*args, **kwargs):
    return _scraper.row_to_result(*args, **kwargs)
