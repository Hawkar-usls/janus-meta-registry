import os
import json
import logging
import asyncio
import time
import random
import hmac
from collections import defaultdict, deque
from aiohttp import web, ClientSession, ClientTimeout
from config import RAW_LOGS_DIR

logger = logging.getLogger("JANUS")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

HRAIN_STATE_FILE = os.path.join(RAW_LOGS_DIR, "hrain_state.json")
DEVICE_DATA_FILE = os.path.join(RAW_LOGS_DIR, "device_data.json")
DEVICE_COMMANDS_FILE = os.path.join(RAW_LOGS_DIR, "device_commands.json")

# Public browser inference is deliberately separated from persistent mutation.
# No public frontend receives JANUS_MUTATION_TOKEN or model-provider credentials.
PUBLIC_WEB_ORIGINS = {
    "https://hawkar-usls.github.io",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}
SYNC_WINDOW_SECONDS = 60
SYNC_MAX_REQUESTS_PER_WINDOW = 20
SYNC_MAX_PROMPT_CHARS = 12000
SYNC_TIMEOUT_SECONDS = 18

active_websockets = set()
state_lock = asyncio.Lock()
sync_rate_lock = asyncio.Lock()
sync_rate_buckets = defaultdict(deque)


def _mutation_token_from_request(request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return request.headers.get("X-Janus-Mutation-Token", "").strip()


def require_mutation_authority(request):
    """Fail closed for every endpoint that persists or consumes shared state.

    The token exists only server-side / on explicitly provisioned internal clients.
    If JANUS_MUTATION_TOKEN is not configured, mutation endpoints are disabled rather
    than becoming anonymous public write surfaces.
    """
    expected = os.environ.get("JANUS_MUTATION_TOKEN", "").strip()
    if not expected:
        raise web.HTTPServiceUnavailable(
            text="Persistent mutation API disabled: JANUS_MUTATION_TOKEN is not configured."
        )
    provided = _mutation_token_from_request(request)
    if not provided or not hmac.compare_digest(provided, expected):
        raise web.HTTPUnauthorized(text="Mutation authority required.")


async def _cors_public_response(request, response):
    origin = request.headers.get("Origin", "")
    if origin in PUBLIC_WEB_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, ngrok-skip-browser-warning"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


async def public_cors_middleware(app, handler):
    async def middleware_handler(request):
        response = await handler(request)
        if request.path in {"/api/hrain/sync", "/api/hrain/state", "/api/janus/action"}:
            return await _cors_public_response(request, response)
        return response
    return middleware_handler


async def handle_options(request):
    response = web.Response(status=204)
    return await _cors_public_response(request, response)


async def _sync_rate_allowed(request):
    forwarded = request.headers.get("X-Forwarded-For", "")
    client = forwarded.split(",", 1)[0].strip() or request.remote or "unknown"
    now = time.monotonic()
    cutoff = now - SYNC_WINDOW_SECONDS
    async with sync_rate_lock:
        bucket = sync_rate_buckets[client]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= SYNC_MAX_REQUESTS_PER_WINDOW:
            return False
        bucket.append(now)
        return True


def _ollama_base_candidates():
    configured = os.environ.get("JANUS_OLLAMA_URL", "").strip().rstrip("/")
    values = []
    if configured:
        values.append(configured)
    # Common JANUS Docker DNS and local-host fallbacks. Deployment may override.
    values.extend([
        "http://janus-ollama:11434",
        "http://127.0.0.1:11434",
    ])
    seen = set()
    return [v for v in values if not (v in seen or seen.add(v))]


async def _ollama_model(session, base_url):
    configured = os.environ.get("JANUS_OLLAMA_MODEL", "").strip()
    if configured:
        return configured
    async with session.get(f"{base_url}/api/tags") as response:
        if response.status != 200:
            raise RuntimeError(f"Ollama tags HTTP {response.status}")
        data = await response.json()
    models = data.get("models") or []
    if not models:
        raise RuntimeError("Ollama has no installed model")
    model = models[0].get("name") or models[0].get("model")
    if not model:
        raise RuntimeError("Ollama model name missing")
    return model


async def _call_ollama(prompt):
    timeout = ClientTimeout(total=SYNC_TIMEOUT_SECONDS, connect=4)
    errors = []
    async with ClientSession(timeout=timeout) as session:
        for base_url in _ollama_base_candidates():
            try:
                model = await _ollama_model(session, base_url)
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.25},
                }
                async with session.post(f"{base_url}/api/generate", json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise RuntimeError(f"Ollama generate HTTP {response.status}: {text[:160]}")
                    data = await response.json()
                text = data.get("response", "")
                if not isinstance(text, str) or not text.strip():
                    raise RuntimeError("Ollama returned empty response")
                return text.strip(), model, base_url
            except Exception as exc:
                errors.append(f"{base_url}: {exc}")
    raise RuntimeError("; ".join(errors) if errors else "No Ollama endpoint configured")


async def handle_index(request):
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(index_path):
        return web.Response(text="index.html не найден", status=404)
    return web.FileResponse(index_path)


async def handle_get_state(request):
    if os.path.exists(HRAIN_STATE_FILE):
        try:
            async with state_lock:
                with open(HRAIN_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            return web.json_response(data)
        except Exception as exc:
            logger.error(f"Ошибка чтения графа HRAIN: {exc}")
    base_state = {
        "nodes": [{
            "id": "root_janus",
            "label": "JANUS CORE",
            "emoji": "🧠",
            "type": "info",
            "x": 0,
            "y": 0,
            "description": "Центральный узел архитектора",
        }],
        "links": [],
    }
    return web.json_response(base_state)


async def handle_hrain_sync(request):
    """Stateless public AI inference for HRaiN/iNaiHR.

    This route has no file write, registry write, graph-save, or mutation authority.
    It returns a Gemini-compatible response envelope so existing frontends can parse
    model text without exposing provider credentials in public JavaScript.
    """
    if not await _sync_rate_allowed(request):
        return web.json_response(
            {"error": "rate_limited", "retry_after_seconds": SYNC_WINDOW_SECONDS},
            status=429,
        )
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    prompt = data.get("text", "") if isinstance(data, dict) else ""
    if not isinstance(prompt, str) or not prompt.strip():
        return web.json_response({"error": "missing_text"}, status=400)
    prompt = prompt.strip()
    if len(prompt) > SYNC_MAX_PROMPT_CHARS:
        return web.json_response(
            {"error": "prompt_too_large", "max_chars": SYNC_MAX_PROMPT_CHARS},
            status=413,
        )

    try:
        text, model, base_url = await _call_ollama(prompt)
        logger.info(
            "[HRAIN SYNC] Stateless inference completed model=%s backend=%s chars=%s",
            model,
            base_url,
            len(prompt),
        )
        return web.json_response({
            "candidates": [{"content": {"parts": [{"text": text}]}}],
            "provider": "ollama",
            "model": model,
            "persistent_write": False,
            "registry_mutation": False,
        })
    except Exception as exc:
        logger.warning(f"[HRAIN SYNC] AI backend unavailable: {exc}")
        return web.json_response(
            {
                "error": "ai_backend_unavailable",
                "persistent_write": False,
                "registry_mutation": False,
            },
            status=503,
        )


async def handle_save_state(request):
    # This legacy shared-state route is no longer anonymous/public.
    require_mutation_authority(request)
    try:
        data = await request.json()
        if not isinstance(data, dict) or not isinstance(data.get("nodes"), list) or not isinstance(data.get("links"), list):
            return web.json_response({"status": "error", "message": "Invalid graph payload"}, status=400)
        async with state_lock:
            with open(HRAIN_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        await broadcast_update(data)
        return web.json_response({"status": "ok", "mutation_authorized": True})
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Ошибка сохранения графа HRAIN: {exc}")
        return web.json_response({"status": "error", "message": str(exc)}, status=500)


async def handle_janus_action(request):
    try:
        data = await request.json()
        prompt = data.get("text", "")
        logger.info(f"[HRAIN SYNTH REQUEST] Получен промпт: {prompt[:50]}...")
        return web.json_response({"result": True, "message": "Сигнал синтеза принят ядром."})
    except Exception as exc:
        logger.error(f"Ошибка обработки action: {exc}")
        return web.json_response({"result": False}, status=500)


async def handle_hrain_event(request):
    require_mutation_authority(request)
    try:
        event = await request.json()
        event_type = event.get("type")
        logger.info(f"[HRAIN EVENT] Получено событие: {event_type}")

        async with state_lock:
            if os.path.exists(HRAIN_STATE_FILE):
                with open(HRAIN_STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
            else:
                state = {"nodes": [], "links": []}

        if event_type == "cycle":
            node_id = f"cycle_{event['cycle']}"
            if not any(n["id"] == node_id for n in state["nodes"]):
                state["nodes"].append({
                    "id": node_id,
                    "label": f"Cycle {event['cycle']}",
                    "emoji": "🔄",
                    "type": "info",
                    "x": random.randint(-300, 300),
                    "y": random.randint(-300, 300),
                    "description": f"Score: {event['score']:.4f}, Loss: {event['val_loss']:.4f}",
                })
                state["links"].append({"source": "root_janus", "target": node_id})

        elif event_type == "anomaly":
            node_id = f"anomaly_{event['cycle']}_{event['seed']}"
            if not any(n["id"] == node_id for n in state["nodes"]):
                state["nodes"].append({
                    "id": node_id,
                    "label": f"Anomaly Z={event['z_score']:.2f}",
                    "emoji": "⚠️",
                    "type": "danger",
                    "x": random.randint(-300, 300),
                    "y": random.randint(-300, 300),
                    "description": f"lr={event['lr']:.5f}, gain={event['gain']:.2f}, temp={event['temp']:.2f}",
                })
                parent_cycle = f"cycle_{event['cycle']}"
                if any(n["id"] == parent_cycle for n in state["nodes"]):
                    state["links"].append({"source": parent_cycle, "target": node_id})

        elif event_type == "record":
            node_id = f"record_{event['cycle']}"
            if not any(n["id"] == node_id for n in state["nodes"]):
                state["nodes"].append({
                    "id": node_id,
                    "label": "🏆 New Record!",
                    "emoji": "🏆",
                    "type": "default",
                    "x": random.randint(-300, 300),
                    "y": random.randint(-300, 300),
                    "description": f"Score: {event['score']:.4f}",
                })
                parent_cycle = f"cycle_{event['cycle']}"
                if any(n["id"] == parent_cycle for n in state["nodes"]):
                    state["links"].append({"source": parent_cycle, "target": node_id})

        elif event_type == "lethal_mutation":
            node_id = f"lethal_{event['cycle']}"
            if not any(n["id"] == node_id for n in state["nodes"]):
                config = event.get("config", {})
                state["nodes"].append({
                    "id": node_id,
                    "label": f"Lethal {event['cycle']}",
                    "emoji": "💀",
                    "type": "danger",
                    "x": random.randint(-300, 300),
                    "y": random.randint(-300, 300),
                    "description": f"lr={config.get('lr', 0):.5f}, gain={config.get('gain', 0):.2f}",
                })
                parent_cycle = f"cycle_{event['cycle']}"
                if any(n["id"] == parent_cycle for n in state["nodes"]):
                    state["links"].append({"source": parent_cycle, "target": node_id})

        async with state_lock:
            with open(HRAIN_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

        await broadcast_update(state)
        return web.json_response({"status": "ok", "mutation_authorized": True})
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Ошибка обработки HRAIN события: {exc}")
        return web.json_response({"status": "error", "message": str(exc)}, status=500)


async def handle_device_data(request):
    require_mutation_authority(request)
    try:
        data = await request.json()
        device_id = data.get("device_id")
        if not device_id:
            return web.json_response({"status": "error", "message": "Missing device_id"}, status=400)

        async with state_lock:
            if os.path.exists(DEVICE_DATA_FILE):
                with open(DEVICE_DATA_FILE, "r", encoding="utf-8") as f:
                    all_data = json.load(f)
            else:
                all_data = []

            record = {
                "timestamp": time.time(),
                "device_id": device_id,
                "data": data.get("data", data),
            }
            all_data.append(record)
            if len(all_data) > 1000:
                all_data = all_data[-1000:]

            with open(DEVICE_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(all_data, f, indent=2)

        logger.info(f"[DEVICE DATA] Получены данные от {device_id}")
        return web.json_response({"status": "ok", "mutation_authorized": True})
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Ошибка приёма данных устройства: {exc}")
        return web.json_response({"status": "error", "message": str(exc)}, status=500)


async def handle_device_command_get(request):
    require_mutation_authority(request)
    device_id = request.match_info.get("device_id")
    if not device_id:
        return web.json_response({"status": "error", "message": "Missing device_id"}, status=400)

    async with state_lock:
        if os.path.exists(DEVICE_COMMANDS_FILE):
            with open(DEVICE_COMMANDS_FILE, "r", encoding="utf-8") as f:
                commands = json.load(f)
        else:
            commands = {}

        command = commands.pop(device_id, None)
        with open(DEVICE_COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(commands, f, indent=2)

    return web.json_response({"command": command, "mutation_authorized": True})


async def handle_device_command_post(request):
    require_mutation_authority(request)
    try:
        data = await request.json()
        device_id = data.get("device_id")
        command = data.get("command")
        if not device_id or command is None:
            return web.json_response({"status": "error", "message": "Missing device_id or command"}, status=400)

        async with state_lock:
            if os.path.exists(DEVICE_COMMANDS_FILE):
                with open(DEVICE_COMMANDS_FILE, "r", encoding="utf-8") as f:
                    commands = json.load(f)
            else:
                commands = {}

            commands[device_id] = command
            with open(DEVICE_COMMANDS_FILE, "w", encoding="utf-8") as f:
                json.dump(commands, f, indent=2)

        logger.info(f"[DEVICE COMMAND] Установлена команда для {device_id}")
        return web.json_response({"status": "ok", "mutation_authorized": True})
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Ошибка установки команды: {exc}")
        return web.json_response({"status": "error", "message": str(exc)}, status=500)


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    active_websockets.add(ws)
    logger.info("[HRAIN] Установлен нейронный линк (WebSocket).")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT and msg.data == "ping":
                await ws.send_str("pong")
    finally:
        active_websockets.discard(ws)
        logger.info("[HRAIN] Нейронный линк разорван.")
    return ws


async def broadcast_update(data):
    if not active_websockets:
        return
    message = json.dumps({"type": "UPDATE", "data": data})
    dead = []
    for ws in active_websockets:
        try:
            await ws.send_str(message)
        except Exception as exc:
            logger.error(f"Ошибка отправки WS сообщения: {exc}")
            dead.append(ws)
    for ws in dead:
        active_websockets.discard(ws)


async def run(core=None):
    try:
        app = web.Application(middlewares=[public_cors_middleware])
        app.add_routes([
            web.get("/", handle_index),
            web.get("/api/hrain/state", handle_get_state),
            web.options("/api/hrain/sync", handle_options),
            web.post("/api/hrain/sync", handle_hrain_sync),
            web.post("/api/hrain/save", handle_save_state),
            web.post("/api/janus/action", handle_janus_action),
            web.post("/api/hrain/event", handle_hrain_event),
            web.post("/api/device/data", handle_device_data),
            web.get("/api/device/command/{device_id}", handle_device_command_get),
            web.post("/api/device/command", handle_device_command_post),
            web.get("/ws", websocket_handler),
        ])

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 1138)
        await site.start()

        mutation_state = "ENABLED_WITH_TOKEN" if os.environ.get("JANUS_MUTATION_TOKEN", "").strip() else "DISABLED_FAIL_CLOSED"
        logger.info("[HRAIN] Визуальная оболочка активна. Доступ: http://localhost:1138")
        logger.info("[HRAIN] /api/hrain/sync = STATELESS_INFERENCE_ONLY")
        logger.info("[HRAIN] persistent mutation API = %s", mutation_state)

        while True:
            await asyncio.sleep(3600)

    except Exception as exc:
        logger.error(f"[КРИТИЧЕСКАЯ ОШИБКА HRAIN] Сервер упал: {exc}")


if __name__ == "__main__":
    asyncio.run(run())
