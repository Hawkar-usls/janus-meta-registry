# -*- coding: utf-8 -*-
"""
[PROJECT JANUS: ATLAS OPTIMIZER v1.0 - WINDOWS TITAN]
Роль: Тяжелый сетевой Дефрагментатор и Компрессор Смыслов.
Суть: Забирает граф с NAS, пересчитывает веса, удаляет мусор, 
строит новые связи на основе математики графов и возвращает обратно.
Связь: Строго по HTTP API (защита базы данных NAS от коррупции).
"""

import os
import sys
import json
import time
import asyncio
import aiohttp
import logging
from datetime import datetime
import math

# --- КОДИРОВКА ДЛЯ WINDOWS ---
if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- ИКОНКИ (UNICODE ESCAPE STRICT) ---
ICONS = {
    "boot": "\U0001F916", "sync": "\U0001F504", "compress": "\u26F1\uFE0F",
    "trash": "\U0001F5D1\uFE0F", "star": "\u2B50", "error": "\u274C",
    "math": "\U0001F9EE", "link": "\U0001F517"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("ATLAS")

class AtlasOptimizer:
    def __init__(self):
        self.config = self._load_config()
        self.nas_url = f"http://{self.config.get('nas_ip', '192.168.1.92')}:{self.config.get('nas_port', 8008)}"
        self.headers = {'Content-Type': 'application/json'}

    def _load_config(self):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            logger.error(f"{ICONS['error']} Не найден config.json. Использую дефолтные IP.")
            return {"nas_ip": "192.168.1.92", "nas_port": 8008}

    async def fetch_graph(self, session):
        """Скачивает сырой граф с NAS."""
        try:
            async with session.get(f"{self.nas_url}/api/hrain/state", timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"{ICONS['error']} NAS ответил кодом {response.status}")
        except Exception as e:
            logger.error(f"{ICONS['error']} Ошибка связи с NAS: {e}")
        return None

    async def push_graph(self, session, nodes, links):
        """Отправляет оптимизированный граф обратно на NAS."""
        payload = {"nodes": nodes, "links": links}
        try:
            async with session.post(f"{self.nas_url}/api/hrain/save", json=payload, timeout=10) as response:
                if response.status == 200:
                    return True
        except Exception as e:
            logger.error(f"{ICONS['error']} Ошибка записи на NAS: {e}")
        return False

    def defragment_and_compress(self, graph_data):
        """ТЯЖЕЛАЯ МАТЕМАТИКА: Архивация и оптимизация графа."""
        nodes = graph_data.get("nodes", [])
        raw_links = graph_data.get("links", [])
        
        if not nodes:
            return nodes, raw_links

        logger.info(f"{ICONS['math']} ATLAS: Начало дефрагментации. Узлов: {len(nodes)}, Связей: {len(raw_links)}")

        # 1. Удаление дубликатов связей
        unique_links = []
        seen_links = set()
        for link in raw_links:
            # Сортируем source и target, чтобы a->b и b->a считались одной связью
            pair = tuple(sorted([str(link.get("source")), str(link.get("target"))]))
            if pair not in seen_links:
                seen_links.add(pair)
                unique_links.append(link)
        
        links_removed = len(raw_links) - len(unique_links)

        # 2. Подсчет гравитации (Degree Centrality)
        degrees = {str(n.get("id")): 0 for n in nodes}
        for link in unique_links:
            src = str(link.get("source"))
            tgt = str(link.get("target"))
            if src in degrees: degrees[src] += 1
            if tgt in degrees: degrees[tgt] += 1

        # 3. Применение физики и лечение боли
        optimized_nodes = []
        orphans_removed = 0
        
        sacred_types = ['root', 'insight', 'genesis_node']

        for node in nodes:
            nid = str(node.get("id"))
            ntype = node.get("type", "concept")
            deg = degrees.get(nid, 0)
            
            # А. Удаление мусора (Архивация нулей)
            if deg == 0 and ntype not in sacred_types:
                orphans_removed += 1
                continue # Пропускаем узел, он удалится из активного графа
                
            # Б. Пересчет массы (val) на основе связей
            base_val = node.get("val", 10)
            # Логарифмический рост: чем больше связей, тем массивнее узел, но без бесконечного раздувания
            new_val = min(100, max(10, int(base_val * 0.5 + (deg * 5))))
            node["val"] = new_val
            
            # В. Охлаждение (снижение pain_score)
            if "pain_score" in node:
                node["pain_score"] = max(0.0, node["pain_score"] * 0.8) # Уменьшаем боль на 20%
                
            optimized_nodes.append(node)

        logger.info(f"{ICONS['compress']} СЖАТИЕ: Удалено {links_removed} дублей связей.")
        logger.info(f"{ICONS['trash']} ОЧИСТКА: Удалено {orphans_removed} мертвых (изолированных) узлов.")
        
        return optimized_nodes, unique_links

    async def run_cycle(self):
        print(f"\n{ICONS['boot']} ATLAS OPTIMIZER ONLINE (ПК-ТИТАН)")
        print(f">> Цель: NAS ({self.nas_url})")
        print(">> Статус: Ожидание накопления энтропии графа...\n")
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            while True:
                try:
                    # Скачиваем
                    graph = await self.fetch_graph(session)
                    if graph and graph.get("nodes"):
                        # Оптимизируем
                        opt_nodes, opt_links = self.defragment_and_compress(graph)
                        
                        # Возвращаем на базу
                        success = await self.push_graph(session, opt_nodes, opt_links)
                        if success:
                            logger.info(f"{ICONS['sync']} АРХИВАЦИЯ ЗАВЕРШЕНА. Граф на NAS обновлен.")
                        else:
                            logger.error(f"{ICONS['error']} Сбой отправки графа.")
                    else:
                        logger.info(f"{ICONS['sync']} Граф пуст или NAS недоступен.")
                        
                except Exception as e:
                    logger.error(f"CRITICAL ERROR: {e}")
                
                # ПК выполняет дефрагментацию раз в 15 минут, чтобы не дергать сеть постоянно
                sleep_time = 15
                logger.info(f"Ожидание {sleep_time} секунд до следующего цикла дефрагментации...")
                await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    atlas = AtlasOptimizer()
    try:
        asyncio.run(atlas.run_cycle())
    except KeyboardInterrupt:
        logger.info("Работа ATLAS завершена вручную.")