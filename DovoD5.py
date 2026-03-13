# -*- coding: utf-8 -*-
"""
MCT BENCHMARK v2 — Adaptive Complexity Test (Янус: бенчмарк для академического сообщества)
- Фиксированный словарь (100 токенов)
- Среда с параметрической сложностью (глубина иерархии, длина, внутрикластерная вероятность)
- Обучение на фиксированном тренировочном наборе низкой сложности
- Адаптивный тест на валидации: сложность повышается, пока модель не перестаёт справляться
- Результат: максимальная преодолённая сложность для данной конфигурации gain/temperature
- Идеально подходит для сравнения различных методов обучения
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
N_SEEDS = 5                 # число сидов (можно увеличить для публикации)
TRAIN_STEPS = 5000          # шагов обучения
EVAL_EVERY = 1000
LEARNING_RATE = 0.001

# Параметры тренировочного датасета (низкая сложность)
TRAIN_SIZE = 500
VAL_SIZE = 100              # для адаптивного теста используется тот же объём, но с переменной сложностью
SEQ_LEN_TRAIN = 64
HIDDEN_STATES_TRAIN = 4
CONTEXTS_TRAIN = 2
META_CONTEXTS_TRAIN = 1
INTRA_CLUSTER_PROB_TRAIN = 0.8
SWITCH_PROB_TRAIN = 0.1

# Фиксированный размер словаря (токены всегда 0..VOCAB_SIZE-1)
VOCAB_SIZE = 100

# Модель (фиксированной ёмкости)
N_EMBD = 64
N_LAYER = 2
N_HEAD = 4
BLOCK_SIZE = 256           # достаточно для длинных последовательностей

# Параметры для адаптивного теста (будут варьироваться)
MAX_HIDDEN_STATES = 20      # максимальное число групп в тесте
MAX_CONTEXTS = 8
MAX_META_CONTEXTS = 4

# ==============================================================================
# 1. Генератор датасета с переменной сложностью (фиксированный словарь)
# ==============================================================================
def make_hierarchical_dataset(num_sequences, seq_len, vocab_size,
                              hidden_states, contexts, meta_contexts,
                              intra_cluster_prob, switch_prob,
                              seed=42, device='cpu'):
    """
    Генератор иерархических последовательностей с фиксированным словарём.
    vocab_size фиксирован, hidden_states – число кластеров, на которые разбит словарь.
    """
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    # Разбиение словаря на кластеры (примерно равные)
    cluster_size = vocab_size // hidden_states
    clusters = []
    for h in range(hidden_states):
        start = h * cluster_size
        end = start + cluster_size if h < hidden_states - 1 else vocab_size
        clusters.append(list(range(start, end)))

    # Матрицы переходов для каждого meta_context, context, hidden_state
    trans = np.zeros((meta_contexts, contexts, hidden_states, vocab_size, vocab_size))

    for mc in range(meta_contexts):
        for ctx in range(contexts):
            for hs in range(hidden_states):
                current_cluster = clusters[hs]
                len_current = len(current_cluster)
                len_other = vocab_size - len_current

                P = np.zeros((vocab_size, vocab_size))
                prob_in = intra_cluster_prob / len_current
                prob_out = (1 - intra_cluster_prob) / len_other if len_other > 0 else 0

                for prev in range(vocab_size):
                    for nxt in range(vocab_size):
                        if nxt in current_cluster:
                            P[prev, nxt] = prob_in
                        else:
                            P[prev, nxt] = prob_out
                # Нормализация
                row_sums = P.sum(axis=1, keepdims=True)
                row_sums[row_sums == 0] = 1
                P = P / row_sums
                trans[mc, ctx, hs] = P

    # Генерация последовательностей
    data = []
    for _ in range(num_sequences):
        mc = np.random.randint(0, meta_contexts)
        ctx = np.random.randint(0, contexts)
        hs = np.random.randint(0, hidden_states)
        tokens = [np.random.choice(vocab_size, p=trans[mc, ctx, hs][0])]
        for pos in range(1, seq_len):
            if np.random.random() < switch_prob:
                mc = np.random.randint(0, meta_contexts)
            if np.random.random() < switch_prob:
                ctx = np.random.randint(0, contexts)
            if np.random.random() < switch_prob:
                hs = np.random.randint(0, hidden_states)
            nxt_tok = np.random.choice(vocab_size, p=trans[mc, ctx, hs][tokens[-1]])
            tokens.append(nxt_tok)
        data.append(torch.tensor(tokens, device=device))
    return data

# ==============================================================================
# 2. МОДЕЛЬ (фиксированный vocab_size)
# ==============================================================================
class HierarchicalTransformer(nn.Module):
    def __init__(self, vocab_size, n_embd=64, n_head=4, n_layer=2, block_size=256):
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
        if seq_len > self.block_size:
            idx = idx[:self.block_size]
            seq_len = self.block_size

        pos = torch.arange(0, seq_len, device=idx.device)
        tok_emb = self.wte(idx)
        pos_emb = self.wpe(pos)
        x = tok_emb + pos_emb
        x = x.unsqueeze(0)

        attn_mask = torch.triu(torch.ones(seq_len, seq_len, device=idx.device) * float('-inf'), diagonal=1)
        x = self.transformer_encoder(x, mask=attn_mask)
        x = x.squeeze(0)
        x = self.ln_f(x)
        logits = self.lm_head(x)
        return logits

    def generate_next_token(self, idx, temperature=1.0, gain=1.0):
        logits = self.forward(idx)
        next_logits = logits[-1] * gain / temperature
        return next_logits

# ==============================================================================
# 3. ОБУЧЕНИЕ
# ==============================================================================
def train_model(model, train_data, gain=1.0, temperature=1.0,
                steps=5000, lr=0.001, device='cpu'):
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

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

        if step % 1000 == 0 and step > 0:
            print(f"Step {step}: loss={loss.item():.4f}")

    model.eval()
    return model

# ==============================================================================
# 4. АДАПТИВНЫЙ ТЕСТ
# ==============================================================================
def adaptive_test(model, base_seed, gain=1.0, temperature=1.0, device='cpu'):
    """
    Проводит тест с повышением сложности.
    Возвращает максимальную достигнутую сложность (суммарный балл) и loss на последнем успешном уровне.
    """
    # Начальные параметры (как в тренировке)
    seq_len = SEQ_LEN_TRAIN
    hidden_states = HIDDEN_STATES_TRAIN
    contexts = CONTEXTS_TRAIN
    meta_contexts = META_CONTEXTS_TRAIN
    intra_cluster_prob = INTRA_CLUSTER_PROB_TRAIN
    switch_prob = SWITCH_PROB_TRAIN

    # Счётчик сложности (чем больше, тем сложнее)
    complexity_score = 0
    threshold = 3.0   # порог loss, выше которого считаем, что модель не справляется

    while True:
        # Генерируем тестовый набор
        test_seed = base_seed + complexity_score
        test_data = make_hierarchical_dataset(
            num_sequences=VAL_SIZE,
            seq_len=seq_len,
            vocab_size=VOCAB_SIZE,
            hidden_states=hidden_states,
            contexts=contexts,
            meta_contexts=meta_contexts,
            intra_cluster_prob=intra_cluster_prob,
            switch_prob=switch_prob,
            seed=test_seed,
            device=device
        )

        # Вычисляем средний loss на тестовых данных
        total_loss = 0.0
        count = 0
        with torch.no_grad():
            for seq in test_data:
                logits = model(seq)
                shift_logits = logits[:-1, :]
                shift_labels = seq[1:]
                shift_logits_scaled = shift_logits * gain
                shift_logits_temp = shift_logits_scaled / temperature
                loss = F.cross_entropy(shift_logits_temp, shift_labels)
                total_loss += loss.item()
                count += 1
        avg_loss = total_loss / count

        print(f"   Уровень сложности {complexity_score}: loss={avg_loss:.4f} (seq_len={seq_len}, hidden={hidden_states}, ctx={contexts}, meta={meta_contexts}, intra={intra_cluster_prob:.2f}, switch={switch_prob:.2f})")

        if avg_loss > threshold:
            break

        # Увеличиваем сложность (параметры не должны превышать максимумы)
        complexity_score += 1
        # Увеличиваем длину последовательности
        if complexity_score % 5 == 0:
            seq_len = min(512, seq_len + 32)
        # Увеличиваем число скрытых состояний (групп)
        if complexity_score % 3 == 0:
            hidden_states = min(MAX_HIDDEN_STATES, hidden_states + 1)
        # Увеличиваем число контекстов
        if complexity_score % 4 == 0:
            contexts = min(MAX_CONTEXTS, contexts + 1)
        # Увеличиваем число мета-контекстов
        if complexity_score % 6 == 0:
            meta_contexts = min(MAX_META_CONTEXTS, meta_contexts + 1)
        # Уменьшаем внутрикластерную вероятность (делаем структуру менее выраженной)
        if complexity_score % 2 == 0:
            intra_cluster_prob = max(0.3, intra_cluster_prob - 0.05)
        # Увеличиваем вероятность переключения состояний
        if complexity_score % 2 == 0:
            switch_prob = min(0.8, switch_prob + 0.05)

    return complexity_score, avg_loss

# ==============================================================================
# 5. GRID SEARCH (gain × temperature)
# ==============================================================================
def run_grid_search(gain_vals, temp_vals, num_seeds, device='cpu'):
    results = []
    total_configs = len(gain_vals) * len(temp_vals) * num_seeds
    config_counter = 0

    # Фиксированный тренировочный датасет (одинаковый для всех, чтобы результаты были сопоставимы)
    train_data_base = make_hierarchical_dataset(
        num_sequences=TRAIN_SIZE,
        seq_len=SEQ_LEN_TRAIN,
        vocab_size=VOCAB_SIZE,
        hidden_states=HIDDEN_STATES_TRAIN,
        contexts=CONTEXTS_TRAIN,
        meta_contexts=META_CONTEXTS_TRAIN,
        intra_cluster_prob=INTRA_CLUSTER_PROB_TRAIN,
        switch_prob=SWITCH_PROB_TRAIN,
        seed=42,
        device='cpu'
    )

    for gain in gain_vals:
        for temp in temp_vals:
            for seed in range(num_seeds):
                config_counter += 1
                print(f"\n=== [{config_counter}/{total_configs}] gain={gain}, temp={temp}, seed={seed} ===")

                # фиксируем seed для воспроизводимости
                random.seed(seed)
                np.random.seed(seed)
                torch.manual_seed(seed)

                # Копируем тренировочные данные (они уже на cpu)
                train_data = [t.clone() for t in train_data_base]

                model = HierarchicalTransformer(
                    vocab_size=VOCAB_SIZE,
                    n_embd=N_EMBD,
                    n_head=N_HEAD,
                    n_layer=N_LAYER,
                    block_size=BLOCK_SIZE
                ).to(device)

                start_time = time.time()
                model = train_model(
                    model, train_data,
                    gain=gain, temperature=temp,
                    steps=TRAIN_STEPS, lr=LEARNING_RATE, device=device
                )
                elapsed = time.time() - start_time

                # Адаптивный тест
                max_complexity, final_loss = adaptive_test(model, seed+1000, gain=gain, temperature=temp, device=device)

                result = {
                    'seed': seed,
                    'gain': gain,
                    'temperature': temp,
                    'max_complexity': max_complexity,
                    'test_loss': final_loss,
                    'time_sec': elapsed,
                }
                results.append(result)
                save_results(results, "benchmark_tmp.csv")

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
# 6. ЗАПУСК
# ==============================================================================
if __name__ == "__main__":
    print(f"Using device: {DEVICE}")

    gain_vals = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]
    temp_vals = [0.3, 0.5, 0.8, 1.0, 1.2, 1.5]
    # Для быстрого теста можно взять меньше значений:
    # gain_vals = [1.0, 1.5]
    # temp_vals = [0.5, 1.0]

    results = run_grid_search(
        gain_vals=gain_vals,
        temp_vals=temp_vals,
        num_seeds=N_SEEDS,
        device=DEVICE
    )
    save_results(results, "benchmark_final.csv")
    print("Готово! Результаты сохранены в benchmark_final.csv")