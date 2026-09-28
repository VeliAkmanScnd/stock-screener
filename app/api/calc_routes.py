"""Ranking JSON: prefer Node sidecar, always fall back to Python+yfinance."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.services.calc_screener import get_snapshot, start_calc_screener
from app.services.calc_sidecar import calc_api_base

router = APIRouter()


def _python_snapshot() -> dict:
    start_calc_screener()
    return get_snapshot()


@router.get("/api/screener")
async def screener_proxy(request: Request):
    target = f"{calc_api_base()}/api/screener"
    query = str(request.query_params)
    if query:
        target = f"{target}?{query}"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(target)
        if response.status_code == 200:
            payload = response.json()
            names = payload.get("names") or {}
            rows = payload.get("rows") or []
            if rows or names.get("nasdaq") or names.get("nyse"):
                return Response(
                    content=response.content,
                    status_code=200,
                    media_type="application/json",
                    headers={"Cache-Control": "no-store"},
                )
    except (httpx.RequestError, ValueError):
        pass
    snapshot = _python_snapshot()
    return JSONResponse(snapshot, headers={"Cache-Control": "no-store"})
