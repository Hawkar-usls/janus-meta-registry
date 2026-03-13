import os
import json
import logging
import asyncio
import time
import random
from aiohttp import web
from config import RAW_LOGS_DIR

logger = logging.getLogger("JANUS")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

HRAIN_STATE_FILE = os.path.join(RAW_LOGS_DIR, "hrain_state.json")
DEVICE_DATA_FILE = os.path.join(RAW_LOGS_DIR, "device_data.json")
DEVICE_COMMANDS_FILE = os.path.join(RAW_LOGS_DIR, "device_commands.json")

active_websockets = set()
state_lock = asyncio.Lock()

async def handle_index(request):
    index_path = os.path.join(os.path.dirname(__file__), 'index.html')
    if not os.path.exists(index_path):
        return web.Response(text="index.html не найден", status=404)
    return web.FileResponse(index_path)

async def handle_get_state(request):
    if os.path.exists(HRAIN_STATE_FILE):
        try:
            async with state_lock:
                with open(HRAIN_STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            return web.json_response(data)
        except Exception as e:
            logger.error(f"Ошибка чтения графа HRAIN: {e}")
    base_state = {
        "nodes": [{
            "id": "root_janus",
            "label": "JANUS CORE",
            "emoji": "\U0001F9E0",
            "type": "info",
            "x": 0, "y": 0,
            "description": "Центральный узел архитектора"
        }],
        "links": []
    }
    return web.json_response(base_state)

async def handle_save_state(request):
    try:
        data = await request.json()
        async with state_lock:
            with open(HRAIN_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        await broadcast_update(data)
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Ошибка сохранения графа HRAIN: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_janus_action(request):
    try:
        data = await request.json()
        prompt = data.get('text', '')
        logger.info(f"[HRAIN SYNTH REQUEST] Получен промпт: {prompt[:50]}...")
        return web.json_response({"result": True, "message": "Сигнал синтеза принят ядром."})
    except Exception as e:
        logger.error(f"Ошибка обработки action: {e}")
        return web.json_response({"result": False}, status=500)

async def handle_hrain_event(request):
    try:
        event = await request.json()
        event_type = event.get('type')
        logger.info(f"[HRAIN EVENT] Получено событие: {event_type}")

        async with state_lock:
            if os.path.exists(HRAIN_STATE_FILE):
                with open(HRAIN_STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
            else:
                state = {"nodes": [], "links": []}

        if event_type == 'cycle':
            node_id = f"cycle_{event['cycle']}"
            if not any(n['id'] == node_id for n in state['nodes']):
                state['nodes'].append({
                    "id": node_id,
                    "label": f"Cycle {event['cycle']}",
                    "emoji": "🔄",
                    "type": "info",
                    "x": random.randint(-300, 300),
                    "y": random.randint(-300, 300),
                    "description": f"Score: {event['score']:.4f}, Loss: {event['val_loss']:.4f}"
                })
                state['links'].append({"source": "root_janus", "target": node_id})

        elif event_type == 'anomaly':
            node_id = f"anomaly_{event['cycle']}_{event['seed']}"
            if not any(n['id'] == node_id for n in state['nodes']):
                state['nodes'].append({
                    "id": node_id,
                    "label": f"Anomaly Z={event['z_score']:.2f}",
                    "emoji": "⚠️",
                    "type": "danger",
                    "x": random.randint(-300, 300),
                    "y": random.randint(-300, 300),
                    "description": f"lr={event['lr']:.5f}, gain={event['gain']:.2f}, temp={event['temp']:.2f}"
                })
                parent_cycle = f"cycle_{event['cycle']}"
                if any(n['id'] == parent_cycle for n in state['nodes']):
                    state['links'].append({"source": parent_cycle, "target": node_id})

        elif event_type == 'record':
            node_id = f"record_{event['cycle']}"
            if not any(n['id'] == node_id for n in state['nodes']):
                state['nodes'].append({
                    "id": node_id,
                    "label": "🏆 New Record!",
                    "emoji": "🏆",
                    "type": "default",
                    "x": random.randint(-300, 300),
                    "y": random.randint(-300, 300),
                    "description": f"Score: {event['score']:.4f}"
                })
                parent_cycle = f"cycle_{event['cycle']}"
                if any(n['id'] == parent_cycle for n in state['nodes']):
                    state['links'].append({"source": parent_cycle, "target": node_id})

        elif event_type == 'lethal_mutation':
            node_id = f"lethal_{event['cycle']}"
            if not any(n['id'] == node_id for n in state['nodes']):
                config = event.get('config', {})
                state['nodes'].append({
                    "id": node_id,
                    "label": f"Lethal {event['cycle']}",
                    "emoji": "💀",
                    "type": "danger",
                    "x": random.randint(-300, 300),
                    "y": random.randint(-300, 300),
                    "description": f"lr={config.get('lr',0):.5f}, gain={config.get('gain',0):.2f}"
                })
                parent_cycle = f"cycle_{event['cycle']}"
                if any(n['id'] == parent_cycle for n in state['nodes']):
                    state['links'].append({"source": parent_cycle, "target": node_id})

        async with state_lock:
            with open(HRAIN_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

        await broadcast_update(state)
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Ошибка обработки HRAIN события: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_device_data(request):
    try:
        data = await request.json()
        device_id = data.get('device_id')
        if not device_id:
            return web.json_response({"status": "error", "message": "Missing device_id"}, status=400)

        async with state_lock:
            if os.path.exists(DEVICE_DATA_FILE):
                with open(DEVICE_DATA_FILE, 'r') as f:
                    all_data = json.load(f)
            else:
                all_data = []

            record = {
                'timestamp': time.time(),
                'device_id': device_id,
                'data': data.get('data', data)
            }
            all_data.append(record)
            if len(all_data) > 1000:
                all_data = all_data[-1000:]

            with open(DEVICE_DATA_FILE, 'w') as f:
                json.dump(all_data, f, indent=2)

        logger.info(f"[DEVICE DATA] Получены данные от {device_id}")
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Ошибка приёма данных устройства: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_device_command_get(request):
    device_id = request.match_info.get('device_id')
    if not device_id:
        return web.json_response({"status": "error", "message": "Missing device_id"}, status=400)

    async with state_lock:
        if os.path.exists(DEVICE_COMMANDS_FILE):
            with open(DEVICE_COMMANDS_FILE, 'r') as f:
                commands = json.load(f)
        else:
            commands = {}

        command = commands.pop(device_id, None)
        with open(DEVICE_COMMANDS_FILE, 'w') as f:
            json.dump(commands, f, indent=2)

    return web.json_response({"command": command})

async def handle_device_command_post(request):
    try:
        data = await request.json()
        device_id = data.get('device_id')
        command = data.get('command')
        if not device_id or command is None:
            return web.json_response({"status": "error", "message": "Missing device_id or command"}, status=400)

        async with state_lock:
            if os.path.exists(DEVICE_COMMANDS_FILE):
                with open(DEVICE_COMMANDS_FILE, 'r') as f:
                    commands = json.load(f)
            else:
                commands = {}

            commands[device_id] = command
            with open(DEVICE_COMMANDS_FILE, 'w') as f:
                json.dump(commands, f, indent=2)

        logger.info(f"[DEVICE COMMAND] Установлена команда для {device_id}")
        return web.json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Ошибка установки команды: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    active_websockets.add(ws)
    logger.info("[HRAIN] Установлен нейронный линк (WebSocket).")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT and msg.data == 'ping':
                await ws.send_str('pong')
    finally:
        active_websockets.remove(ws)
        logger.info("[HRAIN] Нейронный линк разорван.")
    return ws

async def broadcast_update(data):
    if not active_websockets:
        return
    message = json.dumps({"type": "UPDATE", "data": data})
    for ws in active_websockets:
        try:
            await ws.send_str(message)
        except Exception as e:
            logger.error(f"Ошибка отправки WS сообщения: {e}")

async def run(core=None):
    try:
        app = web.Application()
        app.add_routes([
            web.get('/', handle_index),
            web.get('/api/hrain/state', handle_get_state),
            web.post('/api/hrain/save', handle_save_state),
            web.post('/api/janus/action', handle_janus_action),
            web.post('/api/hrain/event', handle_hrain_event),
            web.post('/api/device/data', handle_device_data),
            web.get('/api/device/command/{device_id}', handle_device_command_get),
            web.post('/api/device/command', handle_device_command_post),
            web.get('/ws', websocket_handler)
        ])

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 1138)
        await site.start()

        logger.info("[HRAIN] Визуальная оболочка активна. Доступ: http://localhost:1138")

        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logger.error(f"[КРИТИЧЕСКАЯ ОШИБКА HRAIN] Сервер упал: {e}")

if __name__ == "__main__":
    asyncio.run(run())