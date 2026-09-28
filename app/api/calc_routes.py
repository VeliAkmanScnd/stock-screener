"""Proxy ranking JSON from the Node calc sidecar."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.services.calc_sidecar import calc_api_base

router = APIRouter()


@router.get("/api/screener")
async def screener_proxy(request: Request):
    target = f"{calc_api_base()}/api/screener"
    query = str(request.query_params)
    if query:
        target = f"{target}?{query}"
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.get(target)
    except httpx.RequestError:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Sıralama servisi henüz hazır değil.",
                "rows": [],
                "names": {},
            },
        )
    media = response.headers.get("content-type", "application/json")
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=media,
    )
