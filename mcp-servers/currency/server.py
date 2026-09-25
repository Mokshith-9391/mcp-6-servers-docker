"""
Currency MCP Server
===================
Tools for exchange rates (European Central Bank data via Frankfurter):
  - convert_currency(amount, from_currency, to_currency, date)
  - get_exchange_rates(base, symbols)
  - list_currencies()

API: https://frankfurter.dev  -> free, NO API key needed.
Rates update once per working day (~16:00 CET).

Run:  python server.py      ->  http://<MCP_HOST>:8005/mcp
"""

import os
import re

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()  # local runs: finds the project .env | Docker: env comes from compose

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("CURRENCY_PORT", "8005"))
BASE_URL = "https://api.frankfurter.dev/v1"

mcp = FastMCP("currency", host=HOST, port=PORT)


def _code(value: str) -> str:
    return value.strip().upper()


async def _get(path: str, params: dict | None = None) -> dict | str:
    """GET from Frankfurter. Returns JSON dict, or an error string."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(f"{BASE_URL}{path}", params=params)
    except httpx.HTTPError as e:
        return f"Currency service error: {e}"
    if resp.status_code == 404:
        return "Unknown currency code or date. Use list_currencies to see valid codes."
    if resp.status_code != 200:
        return f"Currency API error {resp.status_code}: {resp.text[:200]}"
    return resp.json()


@mcp.tool()
async def convert_currency(amount: float, from_currency: str, to_currency: str,
                           date: str = "latest") -> str:
    """Convert an amount from one currency to another.

    Args:
        amount: Amount to convert, e.g. 100.
        from_currency: 3-letter code, e.g. "USD".
        to_currency: 3-letter code, e.g. "INR".
        date: "latest" (default) or a past date "YYYY-MM-DD" for historical rates.
    """
    src, dst = _code(from_currency), _code(to_currency)
    if src == dst:
        return f"{amount:,.2f} {src} = {amount:,.2f} {dst}"
    if date != "latest" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return "Date must be 'latest' or in YYYY-MM-DD format."

    data = await _get(f"/{date}", {"base": src, "symbols": dst})
    if isinstance(data, str):
        return data
    rate = data["rates"].get(dst)
    if rate is None:
        return f"No rate available for {src} -> {dst}."
    return (
        f"{amount:,.2f} {src} = {amount * rate:,.2f} {dst}\n"
        f"(rate 1 {src} = {rate} {dst}, ECB reference date {data['date']})"
    )


@mcp.tool()
async def get_exchange_rates(base: str = "USD", symbols: str = "INR,EUR,GBP,AED,SGD") -> str:
    """Get the latest exchange rates for a base currency.

    Args:
        base: Base currency code. Default "USD".
        symbols: Comma-separated target codes, e.g. "INR,EUR,JPY". Empty = all currencies.
    """
    params = {"base": _code(base)}
    if symbols.strip():
        params["symbols"] = ",".join(_code(s) for s in symbols.split(",") if s.strip())
    data = await _get("/latest", params)
    if isinstance(data, str):
        return data
    lines = [f"Exchange rates for 1 {data['base']} (ECB date {data['date']}):"]
    lines += [f"- {code}: {rate}" for code, rate in sorted(data["rates"].items())]
    return "\n".join(lines)


@mcp.tool()
async def list_currencies() -> str:
    """List all supported currency codes with their full names."""
    data = await _get("/currencies")
    if isinstance(data, str):
        return data
    return f"{len(data)} supported currencies:\n" + "\n".join(
        f"- {code}: {name}" for code, name in data.items()
    )


if __name__ == "__main__":
    print(f"💱 Currency MCP server running at http://{HOST}:{PORT}/mcp")
    mcp.run(transport="streamable-http")
