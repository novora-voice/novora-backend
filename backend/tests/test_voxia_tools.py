"""Unit tests for Voxia tool registry."""
from __future__ import annotations
import pytest
from novora.voxia.tools import execute_tool, get_tool_schemas, lookup_order


class TestLookupOrder:
    def test_found_order(self):
        result = lookup_order("ORD-1001")
        assert result["found"] is True
        assert result["order"]["order_id"] == "ORD-1001"
        assert result["order"]["product"] == "Wireless Headphones Pro"

    def test_found_order_case_insensitive(self):
        result = lookup_order("ord-1001")
        assert result["found"] is True

    def test_found_order_with_spaces(self):
        result = lookup_order("  ORD-1002  ")
        assert result["found"] is True
        assert result["order"]["status"] == "processing"

    def test_not_found(self):
        result = lookup_order("ORD-9999")
        assert result["found"] is False
        assert "error" in result

    def test_all_fixture_orders(self):
        for order_id in ["ORD-1001", "ORD-1002", "ORD-1003"]:
            result = lookup_order(order_id)
            assert result["found"] is True


class TestExecuteTool:
    def test_execute_lookup_order(self):
        result = execute_tool("lookup_order", {"order_id": "ORD-1001"})
        assert result["found"] is True

    def test_unauthorized_tool_raises(self):
        with pytest.raises(ValueError, match="not authorized"):
            execute_tool("delete_database", {})

    def test_missing_required_arg_raises(self):
        with pytest.raises(ValueError, match="Missing required argument"):
            execute_tool("lookup_order", {})

    def test_extra_args_ignored(self):
        # Extra arguments that are not in required should be accepted
        result = execute_tool("lookup_order", {"order_id": "ORD-1003", "extra": "ignored"})
        assert result["found"] is True


class TestGetToolSchemas:
    def test_returns_list(self):
        schemas = get_tool_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) >= 1

    def test_lookup_order_schema_structure(self):
        schemas = get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert "lookup_order" in names
        schema = next(s for s in schemas if s["name"] == "lookup_order")
        assert "description" in schema
        assert "parameters" in schema
        assert "required" in schema["parameters"]
        assert "order_id" in schema["parameters"]["required"]
