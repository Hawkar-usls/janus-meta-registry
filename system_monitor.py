#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import threading
import time
import psutil
import os
from datetime import datetime
import numpy as np
import logging
import multiprocessing as mp

from config import CACHE_PROBE_INTERVAL, CACHE_PROBE_SIZE_MB

logger = logging.getLogger("JANUS")

try:
    import pynvml
    pynvml.nvmlInit()
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False
    logger.warning("[\u26A0\uFE0F] nvidia-ml-py не установлен.")

try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False
    logger.warning("[\u26A0\uFE0F] wmi не установлен. Мониторинг iGPU отключен.")


# ========== ТРЕТИЙ ГЛАЗ (Анализатор 3D V-Cache) ==========
def _cache_worker(size_mb, stride, queue):
    """Изолированный процесс для замера времени доступа к памяти без блокировки GIL"""
    try:
        arr_size = (size_mb * 1024 * 1024) // 4
        arr = np.random.randint(0, 255, arr_size, dtype=np.int32)
        start = time.perf_counter()
        total = 0
        for i in range(0, len(arr), stride):
            total += arr[i]
        elapsed = time.perf_counter() - start
        queue.put((elapsed, total))
    except Exception:
        queue.put((-1.0, 0))

class CacheProbe:
    def __init__(self, interval=60.0, size_mb=50):
        self.interval = interval
        self.size_mb = size_mb
        self.running = True
        self.baseline = None
        self.current_ratio = 1.0
        self.current_elapsed = 0.0
        
        self.lock = threading.Lock()
        self._thread = threading.Thread(target=self._probe_loop, daemon=True)
        self._thread.start()
        logger.info("[\U0001F4E6] CacheProbe запущен (Размер: %d MB)", self.size_mb)

    def _calibrate(self):
        logger.info("[\u2699\uFE0F] Калибровка кэша...")
        times = []
        for _ in range(5):
            q = mp.Queue()
            p = mp.Process(target=_cache_worker, args=(self.size_mb, 16, q))
            p.start()
            p.join(timeout=10)
            if not q.empty():
                elapsed, _ = q.get()
                if elapsed > 0:
                    times.append(elapsed)
        if len(times) >= 3:
            times.remove(max(times))
            times.remove(min(times))
            self.baseline = np.median(times)
            logger.info("[\u2705] Baseline кэша установлен: %.4f сек", self.baseline)
        else:
            self.baseline = 0.01 # Fallback

    def _probe_loop(self):
        self._calibrate()
        while self.running:
            try:
                q = mp.Queue()
                p = mp.Process(target=_cache_worker, args=(self.size_mb, 16, q))
                p.start()
                p.join(timeout=10)
                
                if not q.empty():
                    elapsed, _ = q.get()
                    if elapsed > 0 and self.baseline and self.baseline > 0:
                        ratio = elapsed / self.baseline
                        with self.lock:
                            self.current_elapsed = elapsed
                            self.current_ratio = ratio
            except Exception as e:
                logger.debug("[\u274C] Ошибка CacheProbe: %s", e)
            
            time.sleep(self.interval)

    def get_metrics(self):
        with self.lock:
            return {
                'elapsed': self.current_elapsed,
                'ratio': self.current_ratio,
                'baseline': self.baseline
            }

    def stop(self):
        self.running = False


# ========== ВТОРЫЕ РУКИ (Монитор iGPU через WMI) ==========
class IGpuMonitor:
    def __init__(self, interval=5.0):
        self.interval = interval
        self.running = True
        self.load = 0.0
        self.temp = 0.0
        self.lock = threading.Lock()
        
        if WMI_AVAILABLE:
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            logger.info("[\U0001F4BB] IGpuMonitor (WMI) запущен.")
        else:
            self.running = False

    def _poll_loop(self):
        import pythoncom
        pythoncom.CoInitialize()
        w = wmi.WMI()
        
        while self.running:
            try:
                gpu_counters = w.Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapter()
                max_igpu_load = 0.0
                
                for gpu in gpu_counters:
                    name = gpu.Name.lower()
                    if "nvidia" not in name and "rtx" not in name:
                        load = float(gpu.UtilizationPercentage)
                        if load > max_igpu_load:
                            max_igpu_load = load
                            
                with self.lock:
                    self.load = max_igpu_load
                    
            except Exception as e:
                logger.debug("[\u26A0\uFE0F] Ошибка чтения WMI iGPU: %s", e)
                
            time.sleep(self.interval)
            
        pythoncom.CoUninitialize()

    def get_metrics(self):
        with self.lock:
            return {'load': self.load, 'temp': self.temp}

    def stop(self):
        self.running = False


# ========== ОСНОВНОЙ МОНИТОР ==========
class SystemMonitor:
    def __init__(self, poll_interval=2.0):
        self.poll_interval = poll_interval
        self.running = True
        self.lock = threading.Lock()
        self.metrics = {
            'timestamp': None,
            'gpu': {},
            'cpu': {},
            'memory': {},
            'cache': {},
            'igpu': {}
        }
        
        self.cache_probe = CacheProbe(interval=CACHE_PROBE_INTERVAL, size_mb=CACHE_PROBE_SIZE_MB)
        self.igpu_monitor = IGpuMonitor()
        
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def _poll_loop(self):
        while self.running:
            snapshot = self._collect_metrics()
            with self.lock:
                self.metrics = snapshot
            time.sleep(self.poll_interval)

    def _collect_metrics(self):
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'gpu': self._get_gpu_metrics(),
            'cpu': self._get_cpu_metrics(),
            'memory': self._get_memory_metrics(),
            'cache': self.cache_probe.get_metrics(),
            'igpu': self.igpu_monitor.get_metrics()
        }
        return metrics

    def _get_gpu_metrics(self):
        if not NVML_AVAILABLE:
            return {}
        try:
            device_count = pynvml.nvmlDeviceGetCount()
            gpus = []
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                gpus.append({
                    'index': i,
                    'gpu_util': util.gpu,
                    'memory_util': memory.used / memory.total * 100 if memory.total > 0 else 0,
                    'temperature': temperature
                })
            return gpus
        except Exception:
            return {}

    def _get_cpu_metrics(self):
        return {
            'percent_total': psutil.cpu_percent(),
            'count': psutil.cpu_count()
        }

    def _get_memory_metrics(self):
        mem = psutil.virtual_memory()
        return {'percent': mem.percent}

    def get_current_metrics(self):
        with self.lock:
            return self.metrics.copy()

    def stop(self):
        self.running = False
        self.cache_probe.stop()
        self.igpu_monitor.stop()
        if NVML_AVAILABLE:
            pynvml.nvmlShutdown()