# -*- coding: utf-8 -*-
"""
MCT Grid Search v4 — Physarum Maze (слизевик в лабиринте)
- Дискретная среда с памятью: частица движется по графу, собирает ресурсы.
- Ресурсы исчезают после посещения и восстанавливаются через случайное время.
- Положительная обратная связь: вероятность перехода в узел пропорциональна количеству ресурса.
- Шум (температура) добавляет случайные блуждания.
- Модель учится предсказывать следующее событие (узел + взятие ресурса).
- vocab_size = число узлов * 2 (с ресурсом / без ресурса)
"""

import os
import math
import random
import csv
import time
from collections import defaultdict

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

# ==============================================================================
# Конфигурация эксперимента
# ==============================================================================
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
N_SEEDS = 10               # число сидов на конфигурацию
STEPS = 10000              # шагов обучения
EVAL_EVERY = 1000          # частота оценки
LEARNING_RATE = 0.001      # Adam

# Размеры выборки
TRAIN_SIZE = 5000
VAL_SIZE = 1000

# Параметры среды
N_NODES = 30               # количество узлов в графе
EDGE_PROB = 0.15           # вероятность связи между узлами (чтобы граф был связным, но не полным)
INIT_RESOURCE = 5.0        # начальное количество ресурса в каждом узле
RESOURCE_REGEN = 0.1       # скорость восстановления ресурса за шаг
RESOURCE_THRESHOLD = 0.5   # порог, при котором ресурс считается доступным
EXPLOIT_STRENGTH = 2.0     # μ – нелинейность обратной связи (аналог gain)
NOISE_LEVEL = 0.3          # базовый уровень шума (аналог temperature)

# Модель
N_EMBD = 64
N_LAYER = 2
N_HEAD = 4
SEQ_LEN = 128

# Vocab size: для каждого узла два состояния (с ресурсом / без ресурса)
VOCAB_SIZE = N_NODES * 2

# ==============================================================================
# 1. СРЕДА — Слизевик в лабиринте (Physarum Maze)
# ==============================================================================
class PhysarumMaze:
    def __init__(self, n_nodes, edge_prob, init_resource, resource_regen,
                 resource_threshold, exploit_strength, noise_level, seed=None):
        self.n_nodes = n_nodes
        self.edge_prob = edge_prob
        self.init_resource = init_resource
        self.resource_regen = resource_regen
        self.resource_threshold = resource_threshold
        self.exploit_strength = exploit_strength  # μ
        self.noise_level = noise_level
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        # Создаём случайный граф (эрдёш-реньи)
        self.adj = np.zeros((n_nodes, n_nodes), dtype=bool)
        for i in range(n_nodes):
            for j in range(i+1, n_nodes):
                if random.random() < edge_prob:
                    self.adj[i, j] = self.adj[j, i] = True
        # Убеждаемся, что граф связный (если нет, добавляем рёбра)
        if not self._is_connected():
            self._make_connected()

        # Ресурсы узлов (текущее количество)
        self.resources = np.full(n_nodes, init_resource, dtype=float)

    def _is_connected(self):
        visited = np.zeros(self.n_nodes, dtype=bool)
        stack = [0]
        visited[0] = True
        while stack:
            u = stack.pop()
            for v in range(self.n_nodes):
                if self.adj[u, v] and not visited[v]:
                    visited[v] = True
                    stack.append(v)
        return visited.all()

    def _make_connected(self):
        # Простой метод: соединяем все узлы в цепочку
        for i in range(self.n_nodes-1):
            self.adj[i, i+1] = self.adj[i+1, i] = True

    def step(self, current_node):
        """
        Делает шаг: выбирает следующий узел, обновляет ресурсы.
        Возвращает:
            next_node: следующий узел
            took_resource: был ли взят ресурс (0/1)
        """
        # Положительная обратная связь: сила перехода пропорциональна (ресурс)^μ
        neighbors = np.where(self.adj[current_node])[0]
        if len(neighbors) == 0:
            # Если нет соседей (не должно быть), остаёмся на месте
            neighbors = [current_node]

        # Вычисляем веса переходов
        weights = []
        for v in neighbors:
            r = self.resources[v]
            # эксплуатируемость: (r)^μ
            exploit = r ** self.exploit_strength
            weights.append(exploit)

        # Добавляем шум (исследование)
        noise = np.random.uniform(0, self.noise_level, len(neighbors))
        weights += noise

        # Нормализуем
        probs = weights / weights.sum()
        next_node = np.random.choice(neighbors, p=probs)

        # Обновляем ресурсы
        # 1. Восстановление во всех узлах
        self.resources += self.resource_regen
        # 2. Если в следующем узле ресурс превышает порог, забираем его (уменьшаем на 1)
        took = 0
        if self.resources[next_node] >= self.resource_threshold:
            self.resources[next_node] -= 1.0
            took = 1
        # 3. Ограничиваем снизу нулём
        self.resources = np.maximum(self.resources, 0.0)

        return next_node, took

    def reset(self):
        self.resources = np.full(self.n_nodes, self.init_resource, dtype=float)

def generate_sequence(maze, seq_len):
    """
    Генерирует последовательность токенов без BOS.
    Каждый токен: node_id * 2 + took (если took=1, то токен = 2*node_id + 1, иначе 2*node_id).
    """
    tokens = []
    current_node = random.randint(0, maze.n_nodes-1)
    maze.reset()
    for _ in range(seq_len):
        next_node, took = maze.step(current_node)
        token = next_node * 2 + took
        tokens.append(token)
        current_node = next_node
    return torch.tensor(tokens)

def make_physarum_dataset(num_sequences, seq_len, n_nodes, edge_prob,
                          init_resource, resource_regen, resource_threshold,
                          exploit_strength, noise_level, seed, device='cpu'):
    """
    Создаёт датасет из последовательностей, сгенерированных средой PhysarumMaze.
    """
    data = []
    for i in range(num_sequences):
        maze = PhysarumMaze(
            n_nodes=n_nodes,
            edge_prob=edge_prob,
            init_resource=init_resource,
            resource_regen=resource_regen,
            resource_threshold=resource_threshold,
            exploit_strength=exploit_strength,
            noise_level=noise_level,
            seed=seed + i  # разные seed для каждой последовательности, чтобы были разные графы
        )
        seq = generate_sequence(maze, seq_len)
        data.append(seq.to(device))
    return data

# ==============================================================================
# 2. МОДЕЛЬ (без изменений)
# ==============================================================================
class HierarchicalTransformer(nn.Module):
    def __init__(self, vocab_size, n_embd=64, n_head=4, n_layer=2, block_size=128):
        super().__init__()
        self.vocab_size = vocab_size
        self.n_embd = n_embd
        self.block_size = block_size
        self.n_head = n_head
        self.n_layer = n_layer

        self.wte = nn.Embedding(vocab_size, n_embd)
        self.wpe = nn.Embedding(block_size, n_embd)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=n_embd,
            nhead=n_head,
            dim_feedforward=4*n_embd,
            dropout=0.1,
            activation='relu',
            batch_first=True,
            norm_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layer)

        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size, bias=False)

        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx):
        seq_len = idx.size(0)
        pos = torch.arange(0, seq_len, device=idx.device)

        tok_emb = self.wte(idx)               # [seq_len, n_embd]
        pos_emb = self.wpe(pos)                # [seq_len, n_embd]
        x = tok_emb + pos_emb
        x = x.unsqueeze(0)                     # [1, seq_len, n_embd]

        # Каузальная маска
        attn_mask = torch.triu(torch.ones(seq_len, seq_len, device=idx.device) * float('-inf'), diagonal=1)

        x = self.transformer_encoder(x, mask=attn_mask)
        x = x.squeeze(0)                        # [seq_len, n_embd]
        x = self.ln_f(x)
        logits = self.lm_head(x)                # [seq_len, vocab_size]
        return logits

    def generate_next_token(self, idx, temperature=1.0, gain=1.0):
        logits = self.forward(idx)
        next_logits = logits[-1] * gain / temperature
        return next_logits

# ==============================================================================
# 3. МЕТРИКИ
# ==============================================================================
def compute_entropy(probs):
    eps = 1e-12
    log_probs = torch.log(probs + eps)
    return -(probs * log_probs).sum().item()

def compute_mutual_info(sequences, vocab_size):
    joint = np.zeros((vocab_size, vocab_size))
    total = 0
    for seq in sequences:
        for i in range(len(seq)-1):
            a, b = seq[i], seq[i+1]
            joint[a, b] += 1
            total += 1
    if total == 0:
        return 0.0
    joint /= total
    marg_x = joint.sum(axis=1)
    marg_y = joint.sum(axis=0)
    mi = 0.0
    for i in range(vocab_size):
        for j in range(vocab_size):
            if joint[i,j] > 0:
                mi += joint[i,j] * math.log(joint[i,j] / (marg_x[i] * marg_y[j] + 1e-12))
    return mi

def generate_samples(model, n_samples=100, max_len=SEQ_LEN, gain=1.0, temperature=1.0,
                     vocab_size=VOCAB_SIZE, device='cpu', seed=None):
    if seed is not None:
        torch_rng = torch.get_rng_state()
        random_state = random.getstate()
        np_state = np.random.get_state()
        torch.manual_seed(seed)
        random.seed(seed)
        np.random.seed(seed)

    model.eval()
    samples = []
    with torch.no_grad():
        for _ in range(n_samples):
            tokens = [random.randint(0, vocab_size-1)]
            for pos in range(1, max_len):
                idx = torch.tensor(tokens, device=device)
                logits = model.generate_next_token(idx, temperature=temperature, gain=gain)
                probs = F.softmax(logits, dim=-1).cpu().numpy()
                next_tok = np.random.choice(vocab_size, p=probs)
                tokens.append(int(next_tok))
            samples.append(tokens)

    if seed is not None:
        torch.set_rng_state(torch_rng)
        random.setstate(random_state)
        np.random.set_state(np_state)

    return samples

# ==============================================================================
# 4. ЦИКЛ ОБУЧЕНИЯ (с сохранением истории)
# ==============================================================================
def train_model(model, train_data, val_data, gain=1.0, temperature=1.0,
                steps=5000, lr=0.001, eval_every=500, device='cpu'):
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    history = {
        'step': [],
        'train_loss': [],
        'val_loss': [],
        'perplexity': [],
        'entropy': [],
        'diversity': [],
        'mutual_info': [],
        'time': []
    }

    for step in range(steps):
        seq = random.choice(train_data).to(device)
        logits = model(seq)
        shift_logits = logits[:-1, :]
        shift_labels = seq[1:]

        shift_logits_scaled = shift_logits * gain
        shift_logits_temp = shift_logits_scaled / temperature
        loss = F.cross_entropy(shift_logits_temp, shift_labels)

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        if step % eval_every == 0 and step > 0:
            model.eval()
            with torch.no_grad():
                # Валидационный loss
                val_loss = 0.0
                val_count = 0
                for val_seq in random.sample(val_data, min(100, len(val_data))):
                    val_seq = val_seq.to(device)
                    logits_val = model(val_seq)
                    shift_logits_val = logits_val[:-1, :]
                    shift_labels_val = val_seq[1:]
                    shift_logits_val_scaled = shift_logits_val * gain
                    shift_logits_val_temp = shift_logits_val_scaled / temperature
                    val_loss += F.cross_entropy(shift_logits_val_temp, shift_labels_val, reduction='sum').item()
                    val_count += (val_seq.size(0)-1)
                val_loss /= val_count
                perplexity = math.exp(val_loss)

                # Генерация и метрики
                samples = generate_samples(model, n_samples=100, max_len=SEQ_LEN,
                                           gain=gain, temperature=temperature,
                                           vocab_size=model.vocab_size, device=device,
                                           seed=step)
                unique = len(set(tuple(s) for s in samples))
                diversity = unique / 100.0
                mi = compute_mutual_info(samples, model.vocab_size)

                # Энтропия
                probs = F.softmax(shift_logits_val_temp, dim=-1)
                H = -(probs * torch.log(probs + 1e-12)).sum(dim=-1).mean().item()

            model.train()

            history['step'].append(step)
            history['train_loss'].append(loss.item())
            history['val_loss'].append(val_loss)
            history['perplexity'].append(perplexity)
            history['entropy'].append(H)
            history['diversity'].append(diversity)
            history['mutual_info'].append(mi)
            history['time'].append(time.time())

            if step % 2000 == 0:
                print(f"Step {step}: loss={loss.item():.4f}, val_loss={val_loss:.4f}, "
                      f"ppl={perplexity:.4f}, H={H:.3f}, diversity={diversity:.3f}, mi={mi:.4f}")

    final = {k: v[-1] if v else None for k, v in history.items()}
    final['train_loss'] = history['train_loss'][-1] if history['train_loss'] else None
    final['val_loss'] = history['val_loss'][-1] if history['val_loss'] else None
    final['perplexity'] = history['perplexity'][-1] if history['perplexity'] else None
    final['entropy'] = history['entropy'][-1] if history['entropy'] else None
    final['diversity'] = history['diversity'][-1] if history['diversity'] else None
    final['mutual_info'] = history['mutual_info'][-1] if history['mutual_info'] else None
    return history, final

# ==============================================================================
# 5. GRID SEARCH (gain × temperature)
# ==============================================================================
def run_grid_search(model_sizes, gain_vals, temp_vals,
                    num_seeds, steps=10000, eval_every=1000, lr=0.001,
                    train_size=5000, val_size=1000, device='cpu'):
    results = []
    total_configs = len(model_sizes) * len(gain_vals) * len(temp_vals) * num_seeds
    config_counter = 0

    for n_embd in model_sizes:
        for gain in gain_vals:
            for temp in temp_vals:
                for seed in range(num_seeds):
                    config_counter += 1
                    print(f"\n=== [{config_counter}/{total_configs}] n_embd={n_embd}, gain={gain}, temp={temp}, seed={seed} ===")

                    random.seed(seed)
                    np.random.seed(seed)
                    torch.manual_seed(seed)

                    train_data = make_physarum_dataset(
                        num_sequences=train_size, seq_len=SEQ_LEN,
                        n_nodes=N_NODES, edge_prob=EDGE_PROB,
                        init_resource=INIT_RESOURCE, resource_regen=RESOURCE_REGEN,
                        resource_threshold=RESOURCE_THRESHOLD,
                        exploit_strength=EXPLOIT_STRENGTH,
                        noise_level=NOISE_LEVEL,
                        seed=seed, device='cpu'
                    )
                    val_data = make_physarum_dataset(
                        num_sequences=val_size, seq_len=SEQ_LEN,
                        n_nodes=N_NODES, edge_prob=EDGE_PROB,
                        init_resource=INIT_RESOURCE, resource_regen=RESOURCE_REGEN,
                        resource_threshold=RESOURCE_THRESHOLD,
                        exploit_strength=EXPLOIT_STRENGTH,
                        noise_level=NOISE_LEVEL,
                        seed=seed+1000, device='cpu'
                    )

                    model = HierarchicalTransformer(
                        vocab_size=VOCAB_SIZE, n_embd=n_embd, n_head=N_HEAD,
                        n_layer=N_LAYER, block_size=SEQ_LEN
                    ).to(device)

                    start_time = time.time()
                    _, final = train_model(
                        model, train_data, val_data,
                        gain=gain, temperature=temp,
                        steps=steps, lr=lr, eval_every=eval_every, device=device
                    )
                    elapsed = time.time() - start_time

                    result = {
                        'n_embd': n_embd,
                        'seed': seed,
                        'gain': gain,
                        'temperature': temp,
                        'final_train_loss': final['train_loss'],
                        'final_val_loss': final['val_loss'],
                        'final_perplexity': final['perplexity'],
                        'final_entropy': final['entropy'],
                        'final_diversity': final['diversity'],
                        'final_mutual_info': final['mutual_info'],
                        'steps': steps,
                        'time_sec': elapsed,
                    }
                    results.append(result)
                    save_results(results, "grid_search_tmp.csv")

    return results

def save_results(results, filename):
    if not results:
        return
    keys = results[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)

# ==============================================================================
# 6. SANITY-RUN (одна конфигурация для проверки)
# ==============================================================================
def sanity_run():
    print("Sanity run on cpu")
    print("Генерация датасета (Physarum Maze)...")
    train_data = make_physarum_dataset(
        num_sequences=TRAIN_SIZE, seq_len=SEQ_LEN,
        n_nodes=N_NODES, edge_prob=EDGE_PROB,
        init_resource=INIT_RESOURCE, resource_regen=RESOURCE_REGEN,
        resource_threshold=RESOURCE_THRESHOLD,
        exploit_strength=EXPLOIT_STRENGTH,
        noise_level=NOISE_LEVEL,
        seed=42, device='cpu'
    )
    val_data = make_physarum_dataset(
        num_sequences=VAL_SIZE, seq_len=SEQ_LEN,
        n_nodes=N_NODES, edge_prob=EDGE_PROB,
        init_resource=INIT_RESOURCE, resource_regen=RESOURCE_REGEN,
        resource_threshold=RESOURCE_THRESHOLD,
        exploit_strength=EXPLOIT_STRENGTH,
        noise_level=NOISE_LEVEL,
        seed=42+1000, device='cpu'
    )
    print(f"Датасет готов: train={len(train_data)}, val={len(val_data)}")

    model = HierarchicalTransformer(
        vocab_size=VOCAB_SIZE, n_embd=N_EMBD, n_head=N_HEAD,
        n_layer=N_LAYER, block_size=SEQ_LEN
    ).to(DEVICE)
    print(f"Модель создана. Параметры: {sum(p.numel() for p in model.parameters())}")

    print("Обучение baseline (gain=1, temp=1)...")
    history, final = train_model(
        model, train_data, val_data,
        gain=1.0, temperature=1.0,
        steps=5000, lr=LEARNING_RATE, eval_every=1000, device=DEVICE
    )

    print("\n=== РЕЗУЛЬТАТЫ SANITY-RUN ===")
    print(f"Финальный train loss: {final['train_loss']:.4f}")
    print(f"Финальный val loss:   {final['val_loss']:.4f}")
    print(f"Generalization gap:   {final['train_loss'] - final['val_loss']:.4f}")
    print(f"Perplexity:           {final['perplexity']:.4f}")
    print(f"Diversity:            {final['diversity']:.3f}")
    print(f"Mutual info:          {final['mutual_info']:.4f}")

    gap = final['train_loss'] - final['val_loss']
    if gap > 0.5:
        print("✅ Ландшафт сложный, gap достаточный.")
        return True
    else:
        print("⚠️ Gap маловат. Нужно увеличить сложность (уменьшить ресурсы, добавить шума).")
        return False

# ==============================================================================
# 7. ЗАПУСК
# ==============================================================================
if __name__ == "__main__":
    # Сначала проверяем, достаточен ли gap
    if not sanity_run():
        print("Прерывание: среда слишком простая. Измените параметры сложности.")
        exit()

    # Параметры для grid search
    gain_vals = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]
    temp_vals = [0.3, 0.5, 0.8, 1.0, 1.2, 1.5]
    model_sizes = [64]  # можно расширить

    print(f"\nUsing device: {DEVICE}")
    results = run_grid_search(
        model_sizes=model_sizes,
        gain_vals=gain_vals,
        temp_vals=temp_vals,
        num_seeds=N_SEEDS,
        steps=STEPS,
        eval_every=EVAL_EVERY,
        lr=LEARNING_RATE,
        train_size=TRAIN_SIZE,
        val_size=VAL_SIZE,
        device=DEVICE
    )
    save_results(results, "grid_search_final.csv")
    print("Готово! Результаты сохранены в grid_search_final.csv")