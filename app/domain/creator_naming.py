from __future__ import annotations

"""Shared, conservative defaults for persisted Creator display names."""


_PLACEHOLDERS = frozenset({"null", "undefined", "n/a", "na", "n.a.", "-", "--", "—"})


def meaningful_name(value: object) -> str:
    """Return trimmed Unicode text unless it is a transport placeholder."""
    text = str(value if value is not None else "").strip()
    return "" if text.casefold() in _PLACEHOLDERS else text


def normalized_handle(value: object) -> str:
    """Normalize a platform username for use as a human-readable Creator name."""
    handle = meaningful_name(meaningful_name(value).lstrip("@").strip())
    return f"@{handle}" if handle else ""


def default_creator_name(
    *,
    display_name: object = "",
    username: object = "",
    profile_title: object = "",
) -> str:
    """Choose a stable seed name without inventing platform identity."""
    return (
        meaningful_name(display_name)
        or normalized_handle(username)
        or meaningful_name(profile_title)
    )


def preserved_or_default_creator_name(
    current_name: object,
    *,
    display_name: object = "",
    username: object = "",
    profile_title: object = "",
) -> str:
    """Never replace an established Creator name with observed account data."""
    current = str(current_name if current_name is not None else "").strip()
    return current or default_creator_name(
        display_name=display_name,
        username=username,
        profile_title=profile_title,
    )
