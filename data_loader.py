import os
import json
import numpy as np
import logging
from collections import Counter
from config import VOCAB_SIZE, RAW_LOGS_DIR

logger = logging.getLogger("JANUS")

DEVICE_DATA_FILE = os.path.join(RAW_LOGS_DIR, "device_data.json")
HISTORY_FILE = os.path.join(RAW_LOGS_DIR, "physical_history.json")
CACHE_SIZE = 2000

def load_real_data(num_sequences=128, seq_len=64):
    if not os.path.exists(DEVICE_DATA_FILE):
        raise FileNotFoundError(f"Файл {DEVICE_DATA_FILE} не найден.")

    try:
        with open(DEVICE_DATA_FILE, 'r', encoding='utf-8') as f:
            all_records = json.load(f)
    except json.JSONDecodeError:
        raise ValueError("Файл данных пуст или перезаписывается (JSONDecodeError)")

    if not all_records:
        raise ValueError("Нет данных в device_data.json")

    recent_records = all_records[-CACHE_SIZE:] if len(all_records) > CACHE_SIZE else all_records

    history = []
    device_counter = Counter()
    
    for rec in recent_records:
        device_id = rec.get('device_id', 'unknown')
        d = rec.get('data', {})
        
        # Базовые физические метрики
        t = d.get('temperature', 20.0)
        p = d.get('pressure', 1013.0)
        
        raw_accel = d.get('accel', [0, 0, 0])
        s = d.get('shock', sum([abs(x) for x in raw_accel]) if isinstance(raw_accel, list) else 0.0)
        
        m = d.get('micLevel', 0.0)
        e = d.get('entropy', 1.0)
        m2r = d.get('m2r', d.get('m2r_index', 0.0))

        # Визуальные метрики с экрана
        screen_data = d.get('screen', {})
        brightness = screen_data.get('brightness', 0.5)
        motion = screen_data.get('motion', 0.0)
        screen_entropy = screen_data.get('entropy', 0.0)
        hist = screen_data.get('histogram', [0.0] * 10)
        if len(hist) != 10:
            hist = [0.0] * 10

        # Метрики мыши
        mouse_data = d.get('mouse', {})
        clicks_per_sec = mouse_data.get('clicks_per_sec', 0.0)
        scrolls_per_sec = mouse_data.get('scrolls_per_sec', 0.0)
        move_distance = mouse_data.get('move_distance_per_sec', 0.0)

        # Метрики клавиатуры
        keyboard_data = d.get('keyboard', {})
        keys_per_sec = keyboard_data.get('keys_per_sec', 0.0)

        # 22-мерный вектор (6 физических + 4 экран + 4 мышь + 1 клавиатура = 15? давай посчитаем)
        # Физика: t,p,s,m,e,m2r (6)
        # Экран: brightness, motion, screen_entropy, 10 hist = 13
        # Мышь: clicks_per_sec, scrolls_per_sec, move_distance = 3
        # Клавиатура: keys_per_sec = 1
        # Итого: 6 + 13 + 3 + 1 = 23
        snapshot = [t, p, s, m, e, m2r, brightness, motion, screen_entropy] + hist + [clicks_per_sec, scrolls_per_sec, move_distance, keys_per_sec]
        history.append(snapshot)
        device_counter[device_id] += 1

    if len(history) < seq_len:
        pad_size = seq_len - len(history)
        history = (history * (pad_size // len(history) + 2))[-seq_len:]

    # Нормализация 23 каналов
    signals = np.array(history, dtype=np.float32)
    for i in range(signals.shape[1]):
        col = signals[:, i]
        min_val, max_val = col.min(), col.max()
        if max_val - min_val > 1e-6:
            signals[:, i] = (col - min_val) / (max_val - min_val)
        else:
            signals[:, i] = 0.5

    # Коллапс в единую энтропию среды
    combined = signals.mean(axis=1)
    
    # Квантование в токены
    tokens = (combined * (VOCAB_SIZE - 1)).astype(int)

    # Нарезка последовательностей
    sequences = []
    max_start = len(tokens) - seq_len
    for _ in range(num_sequences):
        start_idx = np.random.randint(0, max_start + 1) if max_start > 0 else 0
        seq = tokens[start_idx : start_idx + seq_len].tolist()
        sequences.append(seq)

    return sequences, dict(device_counter)