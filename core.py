#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JANUS DEMIURGE CORE v2.3 — ГРАВИТАЦИОННОЕ ИСКРИВЛЕНИЕ С КВАНТОВЫМ ТУННЕЛИРОВАНИЕМ
"""

import os
import time
import json
import hashlib
import threading
import requests
import numpy as np
from datetime import datetime
import random

import torch
from config import (
    SEEDS_PER_CYCLE, STEPS_PER_CYCLE, TRAIN_SIZE, VAL_SIZE,
    MODEL_ZOO_DIR, RAW_LOGS_DIR, DEVICE, BASE_BATCH_SIZE,
    HALF_LIFE_STEPS, LR_DECAY_ENABLE
)
from environment import DemiurgeEnvironment
from memory import EvolutionaryMemory
from trainer import run_training_cluster
from system_monitor import SystemMonitor

android_mag = 0.0
android_loss = 0.0
android_entropy = 0.0
android_m2r = 0.0

HOMEOSTATIC_STATE_FILE = os.path.join(RAW_LOGS_DIR, "homeostatic_state.json")
DEVICE_DATA_FILE = os.path.join(RAW_LOGS_DIR, "device_data.json")

def save_homeostatic_state(cycle, last_score, last_mi, best_score, failed_configs):
    state = {
        'cycle': cycle,
        'last_score': last_score,
        'last_mi': last_mi,
        'best_score': best_score,
        'failed_configs': failed_configs
    }
    with open(HOMEOSTATIC_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def load_homeostatic_state():
    if os.path.exists(HOMEOSTATIC_STATE_FILE):
        with open(HOMEOSTATIC_STATE_FILE, 'r') as f:
            return json.load(f)
    return None

def is_valid_metrics(score, val_loss, div, mi, gn_mean):
    if score is None:
        return False
    for x in [val_loss, div, mi, gn_mean]:
        if x is None or np.isnan(x) or np.isinf(x):
            return False
    return True

class TachyonField:
    def __init__(self, lead_factor=1.8):
        self.prev_score = None
        self.prev_prev_score = None
        self.prev_mi = None
        self.lead = lead_factor

    def step(self, score, mi):
        if self.prev_score is None:
            self.prev_score = score
            self.prev_prev_score = score
            self.prev_mi = mi
            return score, mi, 0.0, 0.0

        velocity = score - self.prev_score
        acceleration = score - 2 * self.prev_score + self.prev_prev_score
        predicted_score = score + velocity * self.lead + 0.5 * acceleration
        predicted_mi = mi + (mi - self.prev_mi) * self.lead

        self.prev_prev_score = self.prev_score
        self.prev_score = score
        self.prev_mi = mi

        return predicted_score, predicted_mi, velocity, acceleration

class SymbiosisController:
    def __init__(self):
        self.base_batch = BASE_BATCH_SIZE

    def adapt(self, gpu_load, cpu_load, gpu_temp):
        if gpu_load < 30 and gpu_temp < 65:
            return self.base_batch, 0.0
        stress_factor = max(gpu_load / 100.0, cpu_load / 100.0, (gpu_temp - 50) / 40.0)
        stress_factor = min(1.0, stress_factor)
        current_batch = max(8, int(self.base_batch * (1.0 - stress_factor)))
        current_batch = 2 ** max(3, int(np.log2(current_batch)))
        current_pause = stress_factor * 2.5
        return current_batch, current_pause

def send_hrain_event(event_data):
    try:
        requests.post("http://localhost:1138/api/hrain/event", json=event_data, timeout=1)
    except Exception:
        pass

def update_hrain_graph(memory, current_cycle):
    operations = []
    
    top_configs = memory.get_top_configs(10)
    for conf in top_configs:
        node_id = f"config_{conf.get('timestamp', str(time.time()))}"
        label = f"LR:{conf['lr']:.4f} G:{conf['gain']:.2f} T:{conf['temperature']:.2f}"
        operations.append({
            "type": "add_node",
            "node": {
                "id": node_id,
                "label": label,
                "emoji": "\u2699\uFE0F",
                "type": "info",
                "x": random.randint(-400, 400),
                "y": random.randint(-400, 400),
                "description": f"Score: {conf['score']:.4f}"
            }
        })
    
    anomalies = memory.get_recent_anomalies(5)
    for anom in anomalies:
        node_id = f"anomaly_{anom.get('timestamp', str(time.time()))}"
        operations.append({
            "type": "add_node",
            "node": {
                "id": node_id,
                "label": "\u26A0\uFE0F Anomaly",
                "emoji": "\u26A0\uFE0F",
                "type": "danger",
                "x": random.randint(-400, 400),
                "y": random.randint(-400, 400),
                "description": f"Z-score: {anom.get('z_score', 0):.2f}"
            }
        })

    singularities = memory.get_singularities()
    for sing in singularities:
        node_id = f"singularity_{sing.get('timestamp', str(time.time()))}"
        operations.append({
            "type": "add_node",
            "node": {
                "id": node_id,
                "label": "\u26AB Singularity",
                "emoji": "\u26AB",
                "type": "danger",
                "x": random.randint(-400, 400),
                "y": random.randint(-400, 400),
                "description": f"Score: {sing['score']:.4f} (масса)"
            }
        })
    
    if operations:
        try:
            requests.post("http://localhost:1138/api/hrain/update_graph", json=operations, timeout=2)
            print(f"[\U0001F4CA] Граф HRAIN обновлён: {len(operations)} операций")
        except Exception as e:
            print(f"[\u26A0\uFE0F] Ошибка обновления графа: {e}")

def run_demiurge_loop():
    print("=" * 70)
    print("JANUS DEMIURGE CORE v2.3 — ГРАВИТАЦИОННОЕ ИСКРИВЛЕНИЕ")
    print("=" * 70)

    monitor = SystemMonitor(poll_interval=1.0)

    registry_path = "janus_nuclear_emulation_v1.3.json"
    registry_params = None
    if os.path.exists(registry_path):
        with open(registry_path, 'r', encoding='utf-8') as f:
            reg_data = json.load(f)
            registry_params = reg_data.get('emulation_parameters', None)
            print(f"[\u2705] Ядерный реестр '{registry_path}' загружен.")
    else:
        print(f"[\u26A0\uFE0F] Файл '{registry_path}' не найден. Используются параметры по умолчанию.")

    env = DemiurgeEnvironment(registry_params=registry_params)
    memory = EvolutionaryMemory(registry_path=registry_path)
    tachyon = TachyonField(lead_factor=1.8)
    symbiote = SymbiosisController()

    state = load_homeostatic_state()
    if state:
        cycle = state['cycle']
        last_score = state['last_score']
        last_mi = state['last_mi']
        best_score = state['best_score']
        failed_configs = state.get('failed_configs', [])
        print(f"[\U0001F504] Восстановлено: цикл {cycle}, best_score {best_score:.4f}, failed_configs {len(failed_configs)}")
    else:
        cycle = 0
        last_score = None
        last_mi = None
        best_score = -float('inf')
        failed_configs = []
    best_cycle = 0

    try:
        while True:
            cycle += 1

            metrics = monitor.get_current_metrics()
            gpu_data = metrics.get('gpu', [{}])[0] if isinstance(metrics.get('gpu'), list) else {}
            gpu_load = gpu_data.get('gpu_util', 0.0)
            gpu_temp = gpu_data.get('temperature', 40.0)
            cpu_load = metrics.get('cpu', {}).get('percent_total', 0.0)

            batch_size, pause = symbiote.adapt(gpu_load, cpu_load, gpu_temp)

            print(f"\n{'-'*60}")
            if gpu_load > 40.0 or gpu_temp > 65.0:
                print(f"[\u25B6\uFE0F] CYCLE {cycle} | [\U0001F9A0 СИМБИОЗ] Архитектор активен (GPU: {gpu_load}%, Temp: {gpu_temp}°C)")
            else:
                print(f"[\u25B6\uFE0F] CYCLE {cycle} | [\U0001F525 ДОМИНАЦИЯ] Система свободна (GPU: {gpu_load}%, Temp: {gpu_temp}°C)")
            print(f"   Batch: {batch_size}, Пауза: {pause:.2f}с")
            print(f"{'-'*60}")

            global android_mag, android_loss, android_entropy, android_m2r
            try:
                if os.path.exists(DEVICE_DATA_FILE):
                    with open(DEVICE_DATA_FILE, 'r', encoding='utf-8') as f:
                        all_dev_data = json.load(f)
                    android_records = [r for r in all_dev_data if r.get('device_id', '').lower().startswith('android')]
                    if android_records:
                        last_android = android_records[-1]
                        adata = last_android.get('data', {})
                        mx = adata.get('mag_x', 0.0)
                        my = adata.get('mag_y', 0.0)
                        mz = adata.get('mag_z', 0.0)
                        android_mag = np.sqrt(mx*mx + my*my + mz*mz)
                        android_loss = adata.get('loss', 0.0)
                        android_entropy = adata.get('entropy', 0.0)
                        android_m2r = adata.get('m2r', 0.0)
                        print(f"[\U0001F4F1] Android: mag={android_mag:.2f}, loss={android_loss:.4f}, entropy={android_entropy:.2f}")
            except Exception:
                pass

            try:
                if os.path.exists(DEVICE_DATA_FILE):
                    with open(DEVICE_DATA_FILE, 'r', encoding='utf-8') as f:
                        all_dev_data = json.load(f)
                    for rec in reversed(all_dev_data):
                        if "screen" in rec.get("data", {}):
                            scr = rec["data"]["screen"]
                            b_val = scr.get('brightness', 0)
                            m_val = scr.get('motion', 0)
                            e_val = scr.get('entropy', 0)
                            print(f"[\U0001F5A5\uFE0F] Зеркало: ярк={b_val:.2f} | движ={m_val:.2f} | энтр={e_val:.2f}")
                            break
            except Exception:
                pass

            try:
                if os.path.exists(DEVICE_DATA_FILE):
                    with open(DEVICE_DATA_FILE, 'r', encoding='utf-8') as f:
                        all_dev_data = json.load(f)
                    for rec in reversed(all_dev_data):
                        if "mouse" in rec.get("data", {}):
                            mou = rec["data"]["mouse"]
                            clicks = mou.get('clicks_per_sec', 0)
                            move = mou.get('move_distance_per_sec', 0)
                            print(f"[\U0001F5B1] Мышь: клики/с={clicks:.2f} | движ/с={move:.0f}")
                            break
            except Exception:
                pass

            try:
                d_data = {}
                if os.path.exists(DEVICE_DATA_FILE):
                    with open(DEVICE_DATA_FILE, 'r', encoding='utf-8') as f:
                        d_data = json.load(f)
                if isinstance(d_data, dict) and "data" in d_data:
                    d_data["data"]["pc_gpu_load"] = gpu_load
                    d_data["data"]["pc_gpu_temp"] = gpu_temp
                    d_data["data"]["pc_cpu_load"] = cpu_load
                elif isinstance(d_data, dict):
                    d_data["pc_gpu_load"] = gpu_load
                    d_data["pc_gpu_temp"] = gpu_temp
                    d_data["pc_cpu_load"] = cpu_load
                tmp = DEVICE_DATA_FILE + ".tmp"
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(d_data, f)
                os.replace(tmp, DEVICE_DATA_FILE)
            except Exception:
                pass

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            attempts = 0
            while attempts < 10:
                config, is_mutation, quantum_tunnel = memory.propose()
                if config is None:
                    print("[\U0001F573\uFE0F] Конфигурация поглощена чёрной дырой, цикл пропущен.")
                    time.sleep(pause)
                    continue
                if config in failed_configs:
                    attempts += 1
                    continue
                break
            else:
                print("[\u26A0\uFE0F] Не удалось найти допустимую конфигурацию. Завершение.")
                break

            config = config.copy()
            config['batch_size'] = batch_size
            config['half_life_steps'] = HALF_LIFE_STEPS
            config['lr_decay_enable'] = LR_DECAY_ENABLE

            print(f"[\u2699\uFE0F] Архитектура: n_embd={config['n_embd']}, n_head={config['n_head']}, n_layer={config['n_layer']}")
            print(f"[\u2699\uFE0F] Параметры: lr={config['lr']:.6f}, gain={config['gain']:.3f}, temp={config['temperature']:.3f}")
            if quantum_tunnel:
                print("     [\u26A1] Квантовый туннель активирован!")

            try:
                train_tensor = env.generate_tensors(TRAIN_SIZE).to(DEVICE, non_blocking=True)
                val_tensor = env.generate_tensors(VAL_SIZE).to(DEVICE, non_blocking=True)
                train_hash = hashlib.sha256(train_tensor.cpu().numpy().tobytes()).hexdigest()[:12]
                val_hash = hashlib.sha256(val_tensor.cpu().numpy().tobytes()).hexdigest()[:12]
                print(f"[\U0001F6E1\uFE0F] TrainHash={train_hash} | ValHash={val_hash}")
            except Exception as e:
                print(f"[\u274C] Ошибка генерации данных: {e}")
                save_homeostatic_state(cycle, last_score, last_mi, best_score, failed_configs)
                continue

            res = run_training_cluster(
                config, train_tensor, val_tensor, SEEDS_PER_CYCLE, STEPS_PER_CYCLE,
                batch_size=batch_size, device=DEVICE
            )
            success_count = res[0]
            if success_count == 0:
                print(f"[\U0001F4A5] ЛЕТАЛЬНАЯ МУТАЦИЯ: Взрыв градиентов во всех {SEEDS_PER_CYCLE} потоках.")
                print(f"     Конфигурация (lr: {config['lr']:.5f}, gain: {config['gain']:.2f}) признана нежизнеспособной.")
                failed_configs.append(config)
                memory.register_lethal(config)
                threading.Thread(target=send_hrain_event, args=({
                    "type": "lethal_mutation",
                    "cycle": cycle,
                    "config": {
                        "lr": config['lr'],
                        "gain": config['gain'],
                        "temperature": config['temperature'],
                        "n_embd": config['n_embd'],
                        "n_head": config['n_head'],
                        "n_layer": config['n_layer']
                    },
                    "reason": "gradient_explosion"
                },), daemon=True).start()
                time.sleep(pause)
                continue

            score, val_loss, div, mi, train_loss_avg, gn_min, gn_max, gn_mean, w_norm, vram, step_t, best_state = res[1:]

            if not is_valid_metrics(score, val_loss, div, mi, gn_mean):
                print("[!] Сбой расчёта метрик у выживших потоков — пропускаем цикл.")
                time.sleep(pause)
                continue

            gap = train_loss_avg - val_loss

            print(f"[\U0001F4CA] ВЫЖИВАЕМОСТЬ: {success_count}/{SEEDS_PER_CYCLE} потоков")
            origin = "МУТАЦИЯ" if is_mutation else "СКРЕЩИВАНИЕ"
            print(f"[\U0001F9EC] ПРОИСХОЖДЕНИЕ: {origin}")
            print(f"[\U0001F4C8] Score: {score:.4f} | Loss: {val_loss:.4f} | MI: {mi:.4f} | Div: {div:.3f} | Gap: {gap:.4f}")
            print(f"[\U0001F4C9] Градиенты: min={gn_min:.3f}, max={gn_max:.3f}, mean={gn_mean:.3f}")
            print(f"[\U0001F6E0\uFE0F] VRAM={vram:.0f} MB | Step={step_t:.2f} ms")

            pred_score, pred_mi, velocity, acceleration = tachyon.step(score, mi)
            print(f"[\U0001F52E] ТАХИОН: Pred={pred_score:.4f} | V={velocity:.5f} | A={acceleration:.5f}")

            mode_str = "EXPLORE" if memory.mode == 0 else "EXPLOIT"
            print(f"     [\U0001F300] Режим: {mode_str}")
            if memory.candidate_score > -float('inf'):
                print(f"     [\U0001F3C5] Кандидат: {memory.candidate_score:.4f} (режим {memory.candidate_mode})")
            if len(memory.singularities) > 0:
                print(f"     [\u26AB] Сингулярностей: {len(memory.singularities)}")
            print(f"     [\u2764\uFE0F] Окситоцин: {memory.oxytocin:.2f}")
            if memory.black_hole is not None:
                print(f"     [\U0001F573\uFE0F] Чёрная дыра: масса={memory.black_hole.get('score',0):.4f}, радиус={memory.absorption_radius:.3f}")

            if velocity > 0.1 and pred_score > score:
                print("     [\u26A1] WAKE ME UP INSIDE (Evanescence)")
            elif success_count < SEEDS_PER_CYCLE / 2 and memory.candidate_score > -float('inf'):
                print("     [\U0001F30A] I'M LOST FOREVER (Nightwish)")
            elif success_count == 0:
                print("     [\U0001F6AA] LEFT OUTSIDE ALONE (Anastacia)")

            if last_score is not None:
                if pred_score < score:
                    config['lr'] = min(config.get('lr', 0.001) * 1.25, 0.02)
                    print("     [\u26A1] TACHYON BOOST: lr ↑")
                if acceleration < 0:
                    config['temperature'] = max(config.get('temperature', 1.0) * 0.85, 0.2)
                    print("     [\U0001F9CA] PHASE DAMPING: temp ↓")
                if velocity > 0.05:
                    env.complexity_level += 1
                    print(f"     [\U0001F30A] PHASE SURGE: сложность ↑ {env.complexity_level}")

            if last_score is not None and last_mi is not None:
                mi_growth = mi - last_mi
                score_growth = score - last_score
                if (abs(mi_growth) < 0.01 * (abs(last_mi) + 1e-9)) or (score_growth < 0.01):
                    config['lr'] = min(config.get('lr', 0.001) * 1.2, 0.01)
                    config['gain'] = min(config.get('gain', 1.0) + 0.1, 2.5)
                    print("     [\u2622\uFE0F] ОБОГАЩЕНИЕ: lr ↑, gain ↑")
                elif (score > 0.95 * best_score) and (abs(gap) < 0.05):
                    config['lr'] = max(config.get('lr', 0.001) * 0.5, 1e-4)
                    config['temperature'] = max(config.get('temperature', 1.0) * 0.9, 0.3)
                    print("     [\U0001F9CA] ОБЕДНЕНИЕ: lr ↓, temp ↓")

            additional = {
                'val_loss': val_loss,
                'diversity': div,
                'mutual_info_unbiased': mi,
                'gap': gap,
                'grad_norm_min': gn_min,
                'grad_norm_max': gn_max,
                'grad_norm_mean': gn_mean,
                'weight_norm': w_norm,
                'vram_mb': vram,
                'step_time_ms': step_t,
                'seeds': success_count,
                'complexity_level': env.complexity_level,
                'train_hash': train_hash,
                'val_hash': val_hash,
                'gpu_load': gpu_load,
                'gpu_temp': gpu_temp,
                'cpu_load': cpu_load,
                'batch_size': batch_size,
                'android_mag': android_mag,
                'android_loss': android_loss,
                'android_entropy': android_entropy,
                'android_m2r': android_m2r
            }

            is_record = memory.commit(config, score, is_mutation, additional=additional)

            if success_count > 0:
                memory.switch_mode()

            if score > best_score:
                best_score = score
                best_cycle = cycle
                print(f"[\U0001F3C6] НОВЫЙ РЕКОРД: {best_score:.4f} (цикл {best_cycle})")

            threading.Thread(target=send_hrain_event, args=({
                "type": "cycle",
                "cycle": cycle,
                "score": score,
                "val_loss": val_loss,
                "mi": mi,
                "div": div
            },), daemon=True).start()
            if is_record:
                threading.Thread(target=send_hrain_event, args=({
                    "type": "record",
                    "cycle": cycle,
                    "score": score
                },), daemon=True).start()

            if is_record and best_state is not None:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(MODEL_ZOO_DIR, f"janus_complete_{ts}_C{cycle}_S{score:.4f}.pt")
                torch.save({
                    'model_state': best_state,
                    'config': config,
                    'score': score,
                    'cycle': cycle,
                    'additional': additional
                }, path)
                print(f"[\U0001F4BE] Геном сохранён: {path}")

            env.update_complexity(score)
            last_score, last_mi = score, mi
            save_homeostatic_state(cycle, last_score, last_mi, best_score, failed_configs)

            if cycle % 50 == 0:
                threading.Thread(target=update_hrain_graph, args=(memory, cycle), daemon=True).start()

            if cycle % 100 == 0:
                print(f"\n[\U0001F4CA] СТАТИСТИКА ЛЕТАЛЬНОСТИ за {cycle} циклов:")
                print(f"     Смертей: {memory.total_lethal}, Выживших: {memory.total_alive}")
                for param in ['lr', 'gain', 'temperature']:
                    if param in memory.lethal_stats and memory.lethal_stats[param]['values']:
                        lethal_mean = np.mean(memory.lethal_stats[param]['values'])
                        print(f"     {param}: среднее летальное = {lethal_mean:.5f}")
                print("")

            if pause > 0:
                print(f"[\U0001F4A4] Пауза {pause:.2f}с...")
                time.sleep(pause)

    except (KeyboardInterrupt, Exception) as e:
        print(f"\n[\U0001F6D1] Остановка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        monitor.stop()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("[\u2713] Мониторинг остановлен.")

if __name__ == "__main__":
    run_demiurge_loop()