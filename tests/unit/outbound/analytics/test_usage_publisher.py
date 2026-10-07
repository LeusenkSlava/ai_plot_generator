"""Тесты маппинга записи llm_log в событие analytics.llm_calls."""

from src.outbound.analytics.usage_publisher import build_usage_event


def _record(**overrides) -> dict:
    record = {
        "ts": "2026-10-07T09:46:22.802566+00:00",
        "operation": "create_novel",
        "step": "NovelGenerator",
        "model": "deepseek-v4-flash",
        "prompt_tokens": 1013,
        "completion_tokens": 1050,
        "cache_hit_tokens": 768,
        "duration_s": 6.93,
        "error": None,
        "job_id": None,
    }
    record.update(overrides)
    return record


def test_full_mapping():
    event = build_usage_event(_record(), entity_id=42, service="ai_plot_generator")

    assert event == {
        "ts": "2026-10-07T09:46:22.802566+00:00",
        "service": "ai_plot_generator",
        "operation": "create_novel",
        "step": "NovelGenerator",
        "model": "deepseek-v4-flash",
        "entity_id": "42",
        "job_id": "",
        "prompt_tokens": 1013,
        "completion_tokens": 1050,
        "cached_tokens": 768,
        "duration_ms": 6930,
        "llm_requests": 1,
        "tool_calls": 0,
        "error": "",
    }


def test_unassigned_entity_id_becomes_empty_string():
    event = build_usage_event(_record(), entity_id=None, service="svc")

    assert event["entity_id"] == ""


def test_missing_fields_default_to_zero_and_empty():
    record = _record(
        operation=None,
        step=None,
        model=None,
        prompt_tokens=None,
        completion_tokens=None,
        cache_hit_tokens=None,
        duration_s=None,
        error=None,
        job_id=None,
    )
    event = build_usage_event(record, entity_id=None, service="svc")

    assert event["operation"] == ""
    assert event["step"] == ""
    assert event["model"] == ""
    assert event["prompt_tokens"] == 0
    assert event["completion_tokens"] == 0
    assert event["cached_tokens"] == 0
    assert event["duration_ms"] == 0
    assert event["error"] == ""
    assert event["job_id"] == ""


def test_error_is_propagated():
    event = build_usage_event(
        _record(error="Connection error."), entity_id=1, service="svc"
    )

    assert event["error"] == "Connection error."
