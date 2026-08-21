import hmac
import importlib.util
import logging
import os
from pathlib import Path
from typing import Any

from aiohttp import web

logger = logging.getLogger("JANUS")
REQUEST_SCHEMA = "janus.scout.remote.request.v1"
RESPONSE_SCHEMA = "janus.scout.remote.response.v1"


def _load_local_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"LOCAL_MODULE_IMPORT_FAILED:{filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scout_recovery = _load_local_module("scout_recovery.py", "janus_scout_recovery")
scout_token = _load_local_module("scout_token.py", "janus_scout_token")


def _authorized(request: web.Request) -> bool:
    expected = request.app.get("scout_token")
    if not expected:
        return False
    auth = request.headers.get("Authorization", "")
    prefix = "Bearer "
    return auth.startswith(prefix) and hmac.compare_digest(auth[len(prefix):], expected)


async def _handle_query(request: web.Request) -> web.Response:
    if not _authorized(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    body = await request.json()
    if body.get("schema") != REQUEST_SCHEMA:
        return web.json_response({"error": "invalid_schema"}, status=400)
    request_id = str(body.get("request_id", "")).strip()
    query = str(body.get("query", "")).strip()
    if not request_id or not query:
        return web.json_response({"error": "missing_request_id_or_query"}, status=400)

    core: Any = request.app["janus_core"]
    report = await scout_recovery.run(core, query=query)
    if report is None:
        return web.json_response({
            "schema": RESPONSE_SCHEMA,
            "request_id": request_id,
            "scout_id": os.environ.get("JANUS_SCOUT_ID", "scout-local"),
            "transport_status": "SCOUT_FAILURE",
            "claim_status": "UNRESOLVED",
            "report": None,
        }, status=503)

    return web.json_response({
        "schema": RESPONSE_SCHEMA,
        "request_id": request_id,
        "scout_id": os.environ.get("JANUS_SCOUT_ID", "scout-local"),
        "transport_status": "OK",
        "claim_status": "UNRESOLVED",
        "report": report,
    })


async def run(core: Any) -> None:
    """Resident authenticated JANUS Scout service loaded by Nexus."""
    try:
        token = scout_token.resolve_service_token(create_if_missing=True)
    except Exception as exc:
        logger.error("РАЗВЕДЧИК token initialization failed: %s", exc)
        return
    if not token:
        logger.error("РАЗВЕДЧИК service hold: no JANUS Scout token")
        return

    app = web.Application(client_max_size=256 * 1024)
    app["janus_core"] = core
    app["scout_token"] = token
    app.router.add_post("/v1/scout/query", _handle_query)

    bind = os.environ.get("JANUS_SCOUT_BIND", "127.0.0.1")
    port = int(os.environ.get("JANUS_SCOUT_PORT", "11381"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, bind, port)
    await site.start()
    logger.info("📡 РАЗВЕДЧИК LIVE %s:%s token_fp=%s", bind, port, scout_token.token_fingerprint(token))

    import asyncio
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
