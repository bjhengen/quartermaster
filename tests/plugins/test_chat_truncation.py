"""Tests for tool result truncation in the chat plugin."""

import json

from plugins.chat.plugin import (
    _MAX_TOOL_RESULT_CHARS,
    _truncate_lists_in_place,
    _truncate_tool_result,
)


def test_small_result_not_truncated() -> None:
    """Results under the limit pass through unchanged."""
    result = json.dumps({"status": "ok", "count": 1})
    assert _truncate_tool_result(result, "test.tool") == result


def test_large_list_truncated_smart() -> None:
    """Large lists are truncated at the domain level, producing valid JSON."""
    data = {
        "account": "personal",
        "summaries": [
            {"id": f"m{i}", "subject": f"Email {i}", "snippet": "x" * 200}
            for i in range(50)
        ],
        "count": 50,
    }
    result = json.dumps(data)
    assert len(result) > _MAX_TOOL_RESULT_CHARS  # confirm it's over the limit

    truncated = _truncate_tool_result(result, "email.unread_summary")

    # Should be valid JSON
    parsed = json.loads(truncated)
    assert len(parsed["summaries"]) == 11  # 10 items + truncation marker
    assert parsed["summaries"][-1]["_truncated"] is True
    assert parsed["summaries"][-1]["_total"] == 50


def test_truncate_lists_in_place_nested() -> None:
    """Truncation works on nested list structures."""
    data = {
        "accounts": [
            {
                "name": "personal",
                "summaries": [{"id": f"m{i}"} for i in range(20)],
            }
        ]
    }
    changed = _truncate_lists_in_place(data, max_items=5)
    assert changed is True
    assert len(data["accounts"][0]["summaries"]) == 6  # 5 + marker


def test_truncate_lists_no_change_when_small() -> None:
    """No truncation when lists are under the limit."""
    data = {"items": [1, 2, 3]}
    changed = _truncate_lists_in_place(data, max_items=10)
    assert changed is False
    assert len(data["items"]) == 3


def test_hard_truncation_fallback() -> None:
    """When smart truncation can't reduce enough, hard truncation kicks in."""
    # Create a result with a single huge string value (no lists to truncate)
    data = {"body": "x" * 20000}
    result = json.dumps(data)
    truncated = _truncate_tool_result(result, "email.read")
    assert len(truncated) < len(result)
    assert "truncated" in truncated
