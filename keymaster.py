import asyncio
import ctypes
import json
import logging
import os
import subprocess
import serial

# Настройки путей (согласно твоему конфигу)
AM_PATH = r"C:\ArtMoney\am818.exe"
LOG_DIR = r"E:\Janus_BFaiN\raw_logs"
LOG_PATH = os.path.join(LOG_DIR, "device_data.json")
TEMP_PATH = LOG_PATH + ".tmp"

# Структура для ArtMoney (Magic 1488)
class JanusMemory(ctypes.Structure):
    _fields_ = [
        ("magic", ctypes.c_int), 
        ("f1", ctypes.c_float), 
        ("f2", ctypes.c_float), 
        ("gain_control", ctypes.c_float)
    ]

mem = JanusMemory(1488, 432.0, 439.83, 1.0)

async def keymaster_logic(loop, ser, e_val, m2r_val):
    """Интеллект Ключника: управление Янусом через ArtMoney"""
    if m2r_val > 80.0: # Защита от перегрузки
        mem.f1 = 7.83  
        mem.gain_control = 0.5 
    elif e_val < 0.5: # Поиск резонанса
        mem.f1 = 432.0 
        mem.gain_control = 1.2
        
    cmd = f"SET:{mem.f1:.2f}:{mem.f2:.2f}:{mem.gain_control:.2f}\n"
    await loop.run_in_executor(None, ser.write, cmd.encode('utf-8'))

async def run_bridge():
    if os.path.exists(AM_PATH):
        subprocess.Popen([AM_PATH], shell=True)
    
    os.makedirs(LOG_DIR, exist_ok=True)
    # ПРОВЕРЬ COM-ПОРТ ТУТ!
    ser = serial.Serial('COM3', 115200, timeout=0.1)
    loop = asyncio.get_event_loop()
    
    print(f"[*] КЛЮЧНИК 1488 ЗАПУЩЕН. Ожидание данных...")

    while True:
        if ser.in_waiting:
            line = await loop.run_in_executor(None, ser.readline)
            line = line.decode(errors='ignore').strip()
            
            if line.startswith("ID:1488"):
                try:
                    parts = {p.split(':')[0]: p.split(':')[1] for p in line.split('|')}
                    e_val = float(parts.get('E', 0))
                    m2r_val = float(parts.get('M2R', 0))

                    # Формируем JSON для твоего загрузчика (с полем device_id)
                    data_to_save = [{
                        "device_id": "m5_node_04",
                        "data": {
                            "entropy": e_val,
                            "shock": m2r_val,
                            "f1": mem.f1,
                            "micLevel": e_val * 0.5 # Примерная корреляция
                        }
                    }]
                    
                    with open(TEMP_PATH, 'w', encoding='utf-8') as f:
                        json.dump(data_to_save, f)
                    os.replace(TEMP_PATH, LOG_PATH) 

                    await keymaster_logic(loop, ser, e_val, m2r_val)
                except: pass
        await asyncio.sleep(0.02)

if __name__ == "__main__":
    asyncio.run(run_bridge())
