# -*- coding: utf-8 -*-
"""
JANUS TACHYON BRIDGE v1.1 — SYMBIOTIC EDITION
Синхронизирован с core.py v1.3 и прошивкой маяка v7.5.1
Внедрена система GPU-квотирования (Time-Slicing) для теневых процессов.
"""

import asyncio
import ctypes
import json
import logging
import os
import subprocess
import serial
import psutil
import math
import time

# Импорт константы квотирования (если config.py лежит в той же папке)
try:
    from config import GPU_TICKET_PATH
except ImportError:
    BASE_DIR = r"E:\Janus_BFaiN"
    GPU_TICKET_PATH = os.path.join(BASE_DIR, "raw_logs", "gpu_ticket.json")

logger = logging.getLogger("JANUS_TACHYON")

# ------------------------------------------------------------
# НАСТРОЙКИ ПУТЕЙ
# ------------------------------------------------------------
BASE_DIR = r"E:\Janus_BFaiN"
RAW_LOGS_DIR = os.path.join(BASE_DIR, "raw_logs")
MODEL_ZOO_DIR = os.path.join(BASE_DIR, "Model_Zoo")

CORE_STATE_PATH = os.path.join(BASE_DIR, "core_state.json")
DEVICE_LOG_PATH = os.path.join(RAW_LOGS_DIR, "device_data.json")
TEMP_PATH = DEVICE_LOG_PATH + ".tmp"
AM_PATH = r"C:\ArtMoney\am818.exe"

os.makedirs(RAW_LOGS_DIR, exist_ok=True)

# ------------------------------------------------------------
# СТРУКТУРА ПАМЯТИ ДЛЯ ARTMONEY
# ------------------------------------------------------------
class JanusMemory(ctypes.Structure):
    _fields_ = [
        ("magic", ctypes.c_int),
        ("f1", ctypes.c_float),
        ("f2", ctypes.c_float),
        ("gain_control", ctypes.c_float)
    ]

# ------------------------------------------------------------
# GPU TICKET MONITOR (СИСТЕМА КВОТ)
# ------------------------------------------------------------
def check_gpu_ticket():
    """
    Проверяет наличие валидной квоты на использование GPU.
    Возвращает (bool: можно_ли_использовать, float: осталось_времени_в_сек).
    """
    if not os.path.exists(GPU_TICKET_PATH):
        return False, 0.0

    try:
        with open(GPU_TICKET_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if data.get("janus_can_use_gpu") and data.get("duration", 0) > 0:
            remaining = data["duration"] - (time.time() - data["timestamp"])
            if remaining > 0.05:  # Оставляем запас в 50мс на переключение контекста
                return True, remaining
    except (json.JSONDecodeError, IOError):
        # Файл может быть заблокирован Демиургом в момент записи. Считаем, что квоты нет.
        pass
    except Exception as e:
        logger.error(f"[!] Ошибка чтения квоты: {e}")
        
    return False, 0.0

# ------------------------------------------------------------
# УТИЛИТЫ (Атомарная запись)
# ------------------------------------------------------------
def atomic_write(filepath, data):
    tmp = filepath + ".tmp"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, filepath)
    except Exception as e:
        logger.error(f"Atomic write error: {e}")

# ------------------------------------------------------------
# КЛАСС TACHYON FIELD
# ------------------------------------------------------------
class TachyonField:
    def __init__(self, lead_factor=1.8):
        self.prev_val = None
        self.prev_prev_val = None
        self.lead = lead_factor

    def step(self, current_val):
        if self.prev_val is None:
            self.prev_val = current_val
            self.prev_prev_val = current_val
            return current_val, 0.0, 0.0

        velocity = current_val - self.prev_val
        acceleration = current_val - 2 * self.prev_val + self.prev_prev_val
        predicted = current_val + velocity * self.lead + 0.5 * acceleration

        self.prev_prev_val = self.prev_val
        self.prev_val = current_val

        return predicted, velocity, acceleration

# ------------------------------------------------------------
# ОСНОВНОЙ ЦИКЛ МОСТА
# ------------------------------------------------------------
async def bridge_loop():
    mem = JanusMemory(1488, 432.0, 439.83, 1.0)
    field = TachyonField(lead_factor=1.8)
    
    logger.info("[*] Инициализация COM3...")
    try:
        ser = serial.Serial('COM3', 115200, timeout=0.1)
    except Exception as e:
        logger.error(f"COM Port error: {e}")
        return

    logger.info("[*] TACHYON BRIDGE ONLINE. Ожидание данных...")
    loop = asyncio.get_event_loop()

    while True:
        # 1. Читаем квоту GPU
        gpu_allowed, time_left = check_gpu_ticket()
        
        # 2. Выбираем вычислительный вектор
        if gpu_allowed:
            compute_device = "CUDA"
            logger.debug(f"[⚡] GPU свободен. Запускаю теневой процесс. Окно: {time_left:.2f}с")
            # TODO: Здесь вызываем тяжёлую нейросеть / семантический поиск Януса
            # await run_shadow_inference_on_gpu(time_left)
        else:
            compute_device = "CPU"
            # TODO: Здесь легковесные расчёты или ожидание

        # 3. Базовая логика обмена данными с маяком
        if ser.in_waiting:
            line = await loop.run_in_executor(None, ser.readline)
            line = line.decode(errors='ignore').strip()
            
            if line.startswith("ID:1488"):
                try:
                    parts = {p.split(':')[0]: p.split(':')[1] for p in line.split('|')}
                    entropy = float(parts.get('E', 0))
                except Exception:
                    continue

                # Читаем состояние ядра
                core_score, core_velocity, core_acceleration = 0, 0, 0
                if os.path.exists(CORE_STATE_PATH):
                    try:
                        with open(CORE_STATE_PATH, 'r') as f:
                            c_data = json.load(f)
                            core_score = c_data.get('score', 0)
                            core_velocity = c_data.get('velocity', 0)
                            core_acceleration = c_data.get('acceleration', 0)
                    except:
                        pass

                # Расчет поля Тахиона
                predicted, velocity, acceleration = field.step(entropy)

                # Обратная связь с Маяком
                if acceleration < -0.1 and core_acceleration < 0:
                    mem.gain_control = max(0.1, mem.gain_control - 0.05)
                elif velocity > 0.05 and core_velocity > 0:
                    mem.gain_control = min(5.0, mem.gain_control + 0.1)

                if predicted < entropy:
                    field.lead = min(3.0, field.lead + 0.05)
                else:
                    field.lead = max(1.0, field.lead - 0.02)

                # Отправка команды
                cmd = f"SET:{mem.f1:.2f}:{mem.f2:.2f}:{mem.gain_control:.2f}\n"
                await loop.run_in_executor(None, ser.write, cmd.encode("utf-8"))

                # Логирование
                log_data = {
                    "entropy": entropy,
                    "predicted_entropy": predicted,
                    "velocity": velocity,
                    "acceleration": acceleration,
                    "core_velocity": core_velocity,
                    "core_acceleration": core_acceleration,
                    "core_score": core_score,
                    "f1": mem.f1,
                    "gain": mem.gain_control,
                    "lead": field.lead,
                    "active_device": compute_device, # Записали, кто работал
                    "timestamp": time.time()
                }
                atomic_write(DEVICE_LOG_PATH, log_data)

        await asyncio.sleep(0.02)

# ------------------------------------------------------------
# ТОЧКА ВХОДА
# ------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - [%(levelname)s] - %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(RAW_LOGS_DIR, "bridge.log")),
            logging.StreamHandler()
        ]
    )
    
    try:
        asyncio.run(bridge_loop())
    except KeyboardInterrupt:
        logger.info("[!] Работа моста завершена пользователем.")
    except Exception as e:
        logger.critical(f"FATAL BRIDGE ERROR: {e}", exc_info=True)