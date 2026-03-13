import csv
import json
import random
import numpy as np
import os
import time
import math
from datetime import datetime
from config import RAW_LOGS_DIR, DEBUG_MODE

class EvolutionaryMemory:
    def __init__(self, registry_path=None, elite_size=20, mutation_rate=0.1, crossover_type='intermediate'):
        self.csv_path = os.path.join(RAW_LOGS_DIR, "landscape_map.csv")
        self.best_config_path = os.path.join(RAW_LOGS_DIR, "best_config.json")
        self.history = []
        self.best_config = None
        self.sensitivity = {}

        self.elite_size = elite_size
        self.mutation_rate = mutation_rate
        self.crossover_type = crossover_type

        self.param_ranges = {
            'gain': (0.3, 2.5),
            'temperature': (0.3, 2.0),
            'lr': (1e-4, 5e-3),
            'n_embd': [256, 384, 512, 768],
            'n_head': [8, 12, 16],
            'n_layer': [4, 6, 8, 12]
        }
        for param in self.param_ranges:
            if isinstance(self.param_ranges[param], tuple):
                self.sensitivity[param] = {'up': [], 'down': []}

        # Статистика летальных мутаций
        self.lethal_stats = {param: {'count': 0, 'values': []} for param in self.param_ranges}
        self.total_lethal = 0
        self.total_alive = 0

        # Гравитационные параметры
        self.G = 0.1
        self.singularities = []
        self.space_curvature = 1.0

        # Двухрежимная динамика
        self.mode = 0
        self.candidate_score = -float('inf')
        self.candidate_mode = 0
        self.candidate_config = None

        # Окситоциновая динамика
        self.oxytocin = 1.0
        self.oxytocin_decay = 0.99
        self.last_parents = None

        # === ЧЁРНАЯ ЗВЕЗДА ===
        self.black_hole = None
        self.absorption_radius = 0.2
        self.absorption_growth = 0.1
        self.quantum_tunnel_prob = 0.05

        self.registry_path = registry_path
        self._load_best_config()
        self._load_history_from_csv()
        self._load_lethal_stats()
        self._load_singularities()

    # ===== Загрузка/сохранение =====
    def _load_best_config(self):
        if os.path.exists(self.best_config_path):
            try:
                with open(self.best_config_path, 'r', encoding='utf-8') as f:
                    self.best_config = json.load(f)
            except Exception:
                pass

    def _load_history_from_csv(self):
        if os.path.exists(self.csv_path):
            try:
                with open(self.csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        parsed_row = {}
                        for k, v in row.items():
                            try:
                                parsed_row[k] = float(v)
                            except ValueError:
                                parsed_row[k] = v
                        self.history.append(parsed_row)
                print(f"[\U0001F9E0] Память восстановлена: загружено {len(self.history)} прошлых поколений.")
            except Exception as e:
                print(f"[\u26A0\uFE0F] Ошибка чтения истории: {e}")

    def _load_lethal_stats(self):
        lethal_path = os.path.join(RAW_LOGS_DIR, "lethal_stats.json")
        if os.path.exists(lethal_path):
            try:
                with open(lethal_path, 'r') as f:
                    data = json.load(f)
                    self.lethal_stats = data.get('stats', self.lethal_stats)
                    self.total_lethal = data.get('total_lethal', 0)
                    self.total_alive = data.get('total_alive', 0)
                print(f"[\U0001F480] Загружена статистика летальности: {self.total_lethal} смертей, {self.total_alive} выживших.")
            except Exception as e:
                print(f"[\u26A0\uFE0F] Ошибка загрузки lethal_stats: {e}")

    def _load_singularities(self):
        if self.best_config and 'id' in self.best_config:
            self.singularities.append(self.best_config['id'])

    def save_lethal_stats(self):
        lethal_path = os.path.join(RAW_LOGS_DIR, "lethal_stats.json")
        try:
            with open(lethal_path, 'w') as f:
                json.dump({
                    'stats': self.lethal_stats,
                    'total_lethal': self.total_lethal,
                    'total_alive': self.total_alive
                }, f, indent=2)
        except Exception as e:
            print(f"[\u26A0\uFE0F] Ошибка сохранения lethal_stats: {e}")

    def register_lethal(self, config):
        self.total_lethal += 1
        for param, value in config.items():
            if param in self.lethal_stats:
                self.lethal_stats[param]['count'] += 1
                self.lethal_stats[param]['values'].append(value)
                if len(self.lethal_stats[param]['values']) > 100:
                    self.lethal_stats[param]['values'] = self.lethal_stats[param]['values'][-100:]
        self.save_lethal_stats()

    def register_alive(self, config):
        self.total_alive += 1

    # ===== Гравитационные методы =====
    def _gravitational_distance(self, p1, p2):
        coord_keys = ['lr', 'gain', 'temperature', 'n_embd', 'n_head', 'n_layer']
        vec1 = np.array([p1.get(k, 0) for k in coord_keys])
        vec2 = np.array([p2.get(k, 0) for k in coord_keys])
        euclidean = np.linalg.norm(vec1 - vec2)

        m1 = max(p1.get('score', 0), 0.1)
        m2 = max(p2.get('score', 0), 0.1)

        correction = 1.0 + self.G * (m1 + m2)
        return euclidean / correction

    def _gravitational_potential(self, point, configs):
        pot = 0.0
        for c in configs:
            if c.get('id') == point.get('id'):
                continue
            r = self._gravitational_distance(point, c)
            if r > 1e-9:
                pot += self.G * max(c.get('score', 0), 0.1) / r
        return pot

    def _get_elite(self):
        if not self.history:
            return []
        sorted_hist = sorted(self.history, key=lambda x: x.get('score', -float('inf')), reverse=True)
        return sorted_hist[:min(self.elite_size, len(sorted_hist))]

    def _select_parents(self, elite):
        if len(elite) < 2:
            return random.sample(self.history, 2) if len(self.history) >= 2 else (elite[0], elite[0])

        idx1 = random.randint(0, len(elite)-1)
        parent1 = elite[idx1]

        weights = []
        for i, p2 in enumerate(elite):
            if i == idx1:
                weights.append(0.0)
            else:
                dist = self._gravitational_distance(parent1, p2)
                weight = 1.0 / (dist + 1e-9)
                weight *= (1.0 + self.oxytocin * 0.5)
                weights.append(weight)
        total = sum(weights)
        if total == 0:
            probs = [1.0/(len(elite)-1) if i != idx1 else 0.0 for i in range(len(elite))]
        else:
            probs = [w/total for w in weights]

        idx2 = np.random.choice(len(elite), p=probs)
        parent2 = elite[idx2]

        return parent1, parent2

    # ===== Генетические операторы =====
    def _crossover(self, parent1, parent2):
        child = {}
        for param in self.param_ranges.keys():
            if param in parent1 and param in parent2:
                if isinstance(self.param_ranges[param], tuple):
                    low = min(parent1[param], parent2[param])
                    high = max(parent1[param], parent2[param])
                    child[param] = random.uniform(low, high)
                else:
                    child[param] = random.choice([parent1[param], parent2[param]])
            else:
                child[param] = self._random_param(param)
        child['n_embd'] = int(round(child['n_embd']))
        child['n_head'] = int(round(child['n_head']))
        child['n_layer'] = int(round(child['n_layer']))
        if child['n_embd'] % child['n_head'] != 0:
            child['n_head'] = 8
        return child

    def _mutate(self, individual):
        mutated = False
        for param in self.param_ranges.keys():
            if random.random() < self.mutation_rate:
                mutated = True
                if isinstance(self.param_ranges[param], tuple):
                    low, high = self.param_ranges[param]
                    individual[param] = random.uniform(low, high)
                else:
                    individual[param] = random.choice(self.param_ranges[param])
        if individual['n_embd'] % individual['n_head'] != 0:
            individual['n_head'] = 8
        return individual, mutated

    def _random_param(self, param):
        if isinstance(self.param_ranges[param], tuple):
            low, high = self.param_ranges[param]
            return random.uniform(low, high)
        else:
            return random.choice(self.param_ranges[param])

    def _random_config(self):
        conf = {}
        for param in self.param_ranges.keys():
            conf[param] = self._random_param(param)
        conf['n_embd'] = int(round(conf['n_embd']))
        conf['n_head'] = int(round(conf['n_head']))
        conf['n_layer'] = int(round(conf['n_layer']))
        if conf['n_embd'] % conf['n_head'] != 0:
            conf['n_head'] = 8
        return conf

    # ===== МЕТОД PROPOSE (с квантовым туннелированием) =====
    def propose(self):
        if len(self.history) < 2:
            conf = self._random_config()
            conf['id'] = str(time.time()) + str(random.randint(0, 1000))
            return conf, False, False

        elite = self._get_elite()
        if len(elite) < 2:
            conf = self._random_config()
            conf['id'] = str(time.time()) + str(random.randint(0, 1000))
            return conf, False, False

        parent1, parent2 = self._select_parents(elite)
        self.last_parents = (parent1, parent2)
        child = self._crossover(parent1, parent2)
        child, mutated = self._mutate(child)

        for param in ['lr', 'gain', 'temperature']:
            if param in self.lethal_stats and len(self.lethal_stats[param]['values']) > 10:
                lethal_mean = np.mean(self.lethal_stats[param]['values'])
                if abs(child[param] - lethal_mean) < 0.2 * (self.param_ranges[param][1] - self.param_ranges[param][0]):
                    direction = 1 if random.random() > 0.5 else -1
                    shift = 0.1 * (self.param_ranges[param][1] - self.param_ranges[param][0]) * direction
                    child[param] = np.clip(child[param] + shift, self.param_ranges[param][0], self.param_ranges[param][1])
                    mutated = True

        child['gain'] = round(child['gain'], 5)
        child['temperature'] = round(child['temperature'], 5)
        child['lr'] = round(child['lr'], 5)

        # === КВАНТОВОЕ ТУННЕЛИРОВАНИЕ ===
        quantum_tunnel = False
        if self.black_hole is not None:
            dist = self._gravitational_distance(self.black_hole, child)
            if dist < self.absorption_radius:
                if random.random() < self.quantum_tunnel_prob:
                    quantum_tunnel = True
                    print("     [\u26A1] Квантовый туннель! Конфигурация вырвалась из гравитационного плена.")
                else:
                    self.black_hole['score'] = max(self.black_hole.get('score', 0), child.get('score', 0))
                    self.absorption_radius += self.absorption_growth
                    print(f"     [\U0001F573\uFE0F] Новая конфигурация поглощена чёрной дырой! Радиус: {self.absorption_radius:.3f}")
                    return None, False, False

        child['id'] = str(time.time()) + str(random.randint(0, 1000))
        return child, mutated, quantum_tunnel

    def _detect_anomaly(self, metric_name, current_value, window=30):
        recent_history = self.history[-window:]
        values = [h.get(metric_name, 0) for h in recent_history if metric_name in h]
        if len(values) < 8:
            return False, 0.0, 1.0, 0.0
        mean_val = np.mean(values)
        std_val = np.std(values) + 1e-9
        z_score = abs(current_value - mean_val) / std_val
        cohens_d = z_score
        p_value = math.erfc(z_score / math.sqrt(2))
        alpha = 0.05
        total_experiments_tracked = len(self.history) + 1
        fdr_threshold = alpha / total_experiments_tracked
        is_anomaly = p_value < fdr_threshold and cohens_d > 0.5
        return is_anomaly, z_score, p_value, cohens_d

    # ===== ОСНОВНОЙ МЕТОД COMMIT =====
    def commit(self, config, score, is_mutation, additional=None):
        if self.last_parents is not None:
            parent1, parent2 = self.last_parents
            success = (score is not None) and (not math.isnan(score)) and (score > -float('inf'))
            self._update_oxytocin(parent1, parent2, score, success)
            self.last_parents = None

        config['score'] = score
        config['timestamp'] = datetime.now().isoformat()
        config['monotonic_ns'] = time.monotonic_ns()

        if additional:
            config.update(additional)
            mi_anom, mi_z, mi_p, mi_d = self._detect_anomaly('mutual_info_unbiased', additional.get('mutual_info_unbiased', 0))
            if mi_anom:
                print(f"[\u26A0\uFE0F СТАТ. ПРОБОЙ MI] Эффект подтвержден! p-value: {mi_p:.2e} | Cohen's d: {mi_d:.2f}")

            loss_anom, loss_z, loss_p, loss_d = self._detect_anomaly('val_loss', additional.get('val_loss', 0))
            if loss_anom:
                print(f"[\u26A0\uFE0F СТАТ. ПРОБОЙ LOSS] Аномальное падение! p-value: {loss_p:.2e} | Cohen's d: {loss_d:.2f}")

        self.history.append(config)

        file_exists = os.path.isfile(self.csv_path)
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=config.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(config)

        self.register_alive(config)

        is_record = False
        if score > self.candidate_score:
            self.candidate_score = score
            self.candidate_mode = self.mode
            self.candidate_config = config
        elif score > (self.best_config.get('score', -float('inf')) if self.best_config else -float('inf')) and self.mode == self.candidate_mode:
            self.best_config = config
            with open(self.best_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            self.candidate_score = -float('inf')
            if 'id' in config:
                self.singularities.append(config['id'])
            is_record = True
            self.black_hole = config
            self.absorption_radius = 0.2

        return is_record

    def switch_mode(self):
        self.mode = 1 - self.mode

    def _compute_kinship(self, config1, config2):
        dist = self._gravitational_distance(config1, config2)
        return 1.0 / (dist + 1e-9)

    def _update_oxytocin(self, parent1, parent2, child_score, success):
        kinship = self._compute_kinship(parent1, parent2)
        if success:
            self.oxytocin += kinship * 0.1
        else:
            self.oxytocin -= kinship * 0.2
        self.oxytocin = max(0.1, min(3.0, self.oxytocin * self.oxytocin_decay))

    def get_top_configs(self, n=10):
        sorted_hist = sorted(self.history, key=lambda x: x.get('score', -float('inf')), reverse=True)
        return sorted_hist[:n]

    def get_recent_anomalies(self, n=5):
        anomalies = [h for h in self.history if h.get('mutual_info_unbiased', 0) > 2.0 or h.get('val_loss', 10) < 2.0]
        return anomalies[-n:]

    def get_singularities(self):
        return [h for h in self.history if h.get('id') in self.singularities]