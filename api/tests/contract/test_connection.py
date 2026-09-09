"""Contract tests against a REAL Typesense (localhost:8108 by default).

Skips cleanly when Typesense isn't running so unit tests stay green anywhere.
"""
import pytest

from app.typesense.client import admin_client


def _typesense_up() -> bool:
    try:
        admin_client().operations.is_healthy()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _typesense_up(), reason="Typesense not running")


def test_health():
    assert admin_client().operations.is_healthy()


def test_roundtrip():
    ts = admin_client()
    name = "throwaway_contract_test"
    try:
        ts.collections[name].delete()
    except Exception:
        pass
    ts.collections.create(
        {"name": name, "fields": [{"name": "title", "type": "string"}]}
    )
    try:
        ts.collections[name].documents.create({"id": "1", "title": "hello"})
        doc = ts.collections[name].documents["1"].retrieve()
        assert doc["title"] == "hello"
    finally:
        ts.collections[name].delete()
