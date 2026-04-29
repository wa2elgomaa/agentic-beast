import json

import pandas as pd

from app.tools.analytics_function_tools import _get_top_content_impl, _safe_truncate, _sanitize_text


def test_sanitize_text_removes_newlines_and_control_chars() -> None:
    raw = 'Line 1\nLine 2\r\nBad\x00Char "quoted"'
    cleaned = _sanitize_text(raw)

    assert "\n" not in cleaned
    assert "\r" not in cleaned
    assert "\x00" not in cleaned
    assert cleaned == 'Line 1 Line 2 BadChar "quoted"'


def test_safe_truncate_adds_ascii_ellipsis() -> None:
    truncated = _safe_truncate("abcdefghijklmnopqrstuvwxyz", 10)
    assert truncated == "abcdefg..."


def test_get_top_content_impl_serializes_quote_heavy_rows(monkeypatch) -> None:
    frame = pd.DataFrame(
        [
            {
                "platform": "linkedin",
                "content_type": "post",
                "published_at": "2026-02-24 17:39:04",
                "video_view_count": 9876,
                "title": 'CEO says "AI is now a weapon" and we must adapt',
                "content": 'First line\nSecond line with "quotes" and URL https://example.com/test',
                "view_on_platform": "https://linkedin.example/post/1",
            }
        ]
    )

    monkeypatch.setattr("app.tools.analytics_function_tools._load_all_data", lambda: frame)

    payload = json.loads(_get_top_content_impl(metric="video_view_count", top_n=1))
    assert payload["metric"] == "video_view_count"
    assert len(payload["results"]) == 1

    row = payload["results"][0]
    assert row["platform"] == "linkedin"
    assert "\n" not in row["content"]
    assert row["content"].startswith("First line Second line")
    assert '"quotes"' in row["content"]


def test_get_top_content_impl_caps_content_length(monkeypatch) -> None:
    long_text = "x" * 800
    frame = pd.DataFrame(
        [
            {
                "platform": "instagram",
                "content_type": "post",
                "published_at": "2026-01-01 08:00:00",
                "video_view_count": 42,
                "title": "A" * 400,
                "content": long_text,
                "view_on_platform": "https://example.com/post/2",
            }
        ]
    )

    monkeypatch.setattr("app.tools.analytics_function_tools._load_all_data", lambda: frame)

    payload = json.loads(_get_top_content_impl(metric="video_view_count", top_n=1))
    row = payload["results"][0]

    assert len(row["title"]) <= 240
    assert len(row["content"]) <= 480
