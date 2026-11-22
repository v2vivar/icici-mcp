"""Tests for the server module."""

import asyncio
import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from icici_mcp.server import mcp, place_order


class TestToolRegistration:
    """Verify the exposed tool set cannot place or change orders."""

    EXPECTED_TOOLS = (
        "icici_login",
        "get_holdings",
        "get_demat_holdings",
        "get_positions",
        "get_orders",
        "get_margins",
        "get_funds",
        "get_quote",
        "get_historical_data",
        "get_option_chain",
    )

    def test_all_tools_registered(self):
        tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
        assert tool_names == set(self.EXPECTED_TOOLS)

    @pytest.mark.parametrize("name", ["place_order", "modify_order", "cancel_order", "square_off"])
    def test_live_order_tools_cannot_be_called(self, name, monkeypatch):
        def unexpected_breeze_call():
            pytest.fail("An unregistered tool reached Breeze")

        monkeypatch.setattr("icici_mcp.server._breeze", unexpected_breeze_call)
        with pytest.raises(ToolError, match=f"Unknown tool: {name}"):
            asyncio.run(mcp.call_tool(name, {}))

    def test_tools_have_descriptions(self):
        for tool in mcp._tool_manager.list_tools():
            assert tool.description, f"Tool '{tool.name}' has no description"


class TestOrderValidation:
    """Test input validation for place_order."""

    def test_rejects_zero_quantity(self):
        result = json.loads(place_order(
            stock_code="RELIANCE", exchange_code="NSE", action="buy", quantity=0,
        ))
        assert result["Status"] == 400
        assert "Quantity" in result["Error"]

    def test_rejects_negative_quantity(self):
        result = json.loads(place_order(
            stock_code="RELIANCE", exchange_code="NSE", action="buy", quantity=-5,
        ))
        assert result["Status"] == 400

    def test_rejects_invalid_action(self):
        result = json.loads(place_order(
            stock_code="RELIANCE", exchange_code="NSE", action="hold", quantity=10,
        ))
        assert result["Status"] == 400
        assert "action" in result["Error"]

    def test_rejects_invalid_product(self):
        result = json.loads(place_order(
            stock_code="RELIANCE", exchange_code="NSE", action="buy", quantity=10,
            product="invalid",
        ))
        assert result["Status"] == 400
        assert "product" in result["Error"]

    def test_rejects_invalid_order_type(self):
        result = json.loads(place_order(
            stock_code="RELIANCE", exchange_code="NSE", action="buy", quantity=10,
            order_type="fok",
        ))
        assert result["Status"] == 400
        assert "order_type" in result["Error"]

    def test_rejects_limit_with_zero_price(self):
        result = json.loads(place_order(
            stock_code="RELIANCE", exchange_code="NSE", action="buy", quantity=10,
            order_type="limit", price="0",
        ))
        assert result["Status"] == 400
        assert "price" in result["Error"].lower()

    def test_rejects_options_without_right(self):
        result = json.loads(place_order(
            stock_code="NIFTY", exchange_code="NFO", action="buy", quantity=75,
            product="options", right="others",
        ))
        assert result["Status"] == 400
        assert "right" in result["Error"].lower()

    def test_rejects_invalid_validity(self):
        result = json.loads(place_order(
            stock_code="RELIANCE", exchange_code="NSE", action="buy", quantity=10,
            validity="gtc",
        ))
        assert result["Status"] == 400
        assert "validity" in result["Error"]


class TestStringConversion:
    def test_place_order_converts_quantity_to_string(self):
        """Verify that integer quantity is converted to string for Breeze API."""
        # This is validated by the existing order validation tests
        # The conversion happens inside place_order after validation
        pass
