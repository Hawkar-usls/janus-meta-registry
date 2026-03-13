# -*- coding: utf-8 -*-
"""
MCT Grid Search v3 — DovoD v69.1 (Янус: назад, сейчас, вперед)
- трёхуровневая иерархия: meta_context → context → hidden_state
- длина последовательности 128, vocab_size = 50
- каузальное внимание (ручная маска через torch.triu)
- автоматический контроль generalization gap
- метрики: loss, perplexity, entropy, diversity, mutual_info
- grid search по gain, temperature и complexity_level
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
TRAIN_SIZE = 8000
VAL_SIZE = 2000

# Параметры среды (могут варьироваться в grid search)
VOCAB_SIZE = 50
SEQ_LEN = 128
HIDDEN_STATES = 8          # количество hidden_state (нижний уровень)
CONTEXTS = 6               # количество контекстов (средний уровень)
META_CONTEXTS = 4          # количество мета-контекстов (верхний уровень)

# Вероятности переключений (можно менять для изменения сложности)
META_SWITCH_PROB = 0.1
CONTEXT_SWITCH_PROB = 0.5
STATE_SWITCH_PROB = 0.5
INTRA_CLUSTER_PROB = 0.1
INTER_CLUSTER_PROB = 1.1

# Модель
N_EMBD = 64
N_LAYER = 2
N_HEAD = 4

# ==============================================================================
# 1. ДАТАСЕТ — трёхуровневая иерархия (meta_context, context, hidden_state)
# ==============================================================================
def make_hierarchical_dataset(num_sequences, seq_len, vocab_size,
                              meta_contexts, contexts, hidden_states,
                              meta_switch_prob=0.01,
                              context_switch_prob=0.05,
                              state_switch_prob=0.1,
                              intra_cluster_prob=0.1,
                              inter_cluster_prob=0.3,
                              seed=42, device='cpu'):
    """
    Генератор последовательностей с тремя уровнями скрытых переменных.
    - meta_context: самый медленный уровень (меняется редко)
    - context: средний уровень (меняется умеренно)
    - hidden_state: быстрый уровень (меняется часто), отвечает за генерацию токенов.

    Возвращает список тензоров длины seq_len.
    """
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    # Разбиение словаря на кластеры для hidden_state (каждый hidden_state владеет кластером)
    cluster_size = vocab_size // hidden_states
    clusters = []
    for h in range(hidden_states):
        start = h * cluster_size
        end = start + cluster_size if h < hidden_states - 1 else vocab_size
        clusters.append(list(range(start, end)))

    # Матрицы переходов для hidden_state (зависят от context и meta_context)
    # Размер: [meta_contexts, contexts, hidden_states, vocab_size, vocab_size]
    trans = np.zeros((meta_contexts, contexts, hidden_states, vocab_size, vocab_size))

    for mc in range(meta_contexts):
        for ctx in range(contexts):
            for hs in range(hidden_states):
                current_cluster = clusters[hs]
                len_current = len(current_cluster)
                len_other = vocab_size - len_current

                # Внутри кластера один "любимый" токен (усиливает структуру)
                favorite = random.choice(current_cluster)

                P = np.zeros((vocab_size, vocab_size))
                for prev in range(vocab_size):
                    # Для простоты распределение не зависит от prev (можно добавить слабую зависимость)
                    for nxt in range(vocab_size):
                        if nxt in current_cluster:
                            if nxt == favorite:
                                # Любимый получает половину внутрикластерной вероятности
                                P[prev, nxt] = intra_cluster_prob * 0.5
                            else:
                                P[prev, nxt] = intra_cluster_prob * 0.5 / (len_current - 1) if len_current > 1 else 0
                        else:
                            P[prev, nxt] = inter_cluster_prob / len_other if len_other > 0 else 0
                # Нормализация
                P = P / P.sum(axis=1, keepdims=True)
                trans[mc, ctx, hs] = P

    # Генерация последовательностей
    data = []
    for _ in range(num_sequences):
        # Начальные уровни
        mc = np.random.randint(0, meta_contexts)
        ctx = np.random.randint(0, contexts)
        hs = np.random.randint(0, hidden_states)

        tokens = [np.random.choice(vocab_size, p=trans[mc, ctx, hs][0])]

        for pos in range(1, seq_len):
            # Обновляем уровни
            if np.random.random() < meta_switch_prob:
                mc = np.random.randint(0, meta_contexts)
            if np.random.random() < context_switch_prob:
                ctx = np.random.randint(0, contexts)
            if np.random.random() < state_switch_prob:
                hs = np.random.randint(0, hidden_states)

            nxt_tok = np.random.choice(vocab_size, p=trans[mc, ctx, hs][tokens[-1]])
            tokens.append(nxt_tok)

        data.append(torch.tensor(tokens, device=device))

    return data

# ==============================================================================
# 2. МОДЕЛЬ С КАУЗАЛЬНОЙ МАСКОЙ (ручная маска)
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

        # Каузальная маска: будущие токены получают -inf
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
# 3. МЕТРИКИ (расширенные)
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
# 5. GRID SEARCH (gain × temperature × complexity)
# ==============================================================================
def run_grid_search(model_sizes, gain_vals, temp_vals, complexity_levels,
                    num_seeds, steps=10000, eval_every=1000, lr=0.001,
                    train_size=8000, val_size=2000, device='cpu'):
    """
    complexity_level — список кортежей (meta_switch, context_switch, state_switch, intra, inter)
    """
    results = []
    total_configs = (len(model_sizes) * len(gain_vals) * len(temp_vals) *
                     len(complexity_levels) * num_seeds)
    config_counter = 0

    for n_embd in model_sizes:
        for gain in gain_vals:
            for temp in temp_vals:
                for comp in complexity_levels:
                    (meta_sw, ctx_sw, st_sw, intra, inter) = comp
                    for seed in range(num_seeds):
                        config_counter += 1
                        print(f"\n=== [{config_counter}/{total_configs}] n_embd={n_embd}, gain={gain}, temp={temp}, "
                              f"comp={comp}, seed={seed} ===")

                        random.seed(seed)
                        np.random.seed(seed)
                        torch.manual_seed(seed)

                        train_data = make_hierarchical_dataset(
                            num_sequences=train_size, seq_len=SEQ_LEN,
                            vocab_size=VOCAB_SIZE,
                            meta_contexts=META_CONTEXTS,
                            contexts=CONTEXTS,
                            hidden_states=HIDDEN_STATES,
                            meta_switch_prob=meta_sw,
                            context_switch_prob=ctx_sw,
                            state_switch_prob=st_sw,
                            intra_cluster_prob=intra,
                            inter_cluster_prob=inter,
                            seed=seed, device='cpu'
                        )
                        val_data = make_hierarchical_dataset(
                            num_sequences=val_size, seq_len=SEQ_LEN,
                            vocab_size=VOCAB_SIZE,
                            meta_contexts=META_CONTEXTS,
                            contexts=CONTEXTS,
                            hidden_states=HIDDEN_STATES,
                            meta_switch_prob=meta_sw,
                            context_switch_prob=ctx_sw,
                            state_switch_prob=st_sw,
                            intra_cluster_prob=intra,
                            inter_cluster_prob=inter,
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
                            'meta_switch': meta_sw,
                            'ctx_switch': ctx_sw,
                            'state_switch': st_sw,
                            'intra_prob': intra,
                            'inter_prob': inter,
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
# 6. SANITY-RUN с автоматическим контролем gap
# ==============================================================================
def sanity_run():
    print("Sanity run on cpu")
    print("Генерация датасета (средняя сложность)...")
    train_data = make_hierarchical_dataset(
        num_sequences=TRAIN_SIZE, seq_len=SEQ_LEN,
        vocab_size=VOCAB_SIZE,
        meta_contexts=META_CONTEXTS,
        contexts=CONTEXTS,
        hidden_states=HIDDEN_STATES,
        meta_switch_prob=META_SWITCH_PROB,
        context_switch_prob=CONTEXT_SWITCH_PROB,
        state_switch_prob=STATE_SWITCH_PROB,
        intra_cluster_prob=INTRA_CLUSTER_PROB,
        inter_cluster_prob=INTER_CLUSTER_PROB,
        seed=42, device='cpu'
    )
    val_data = make_hierarchical_dataset(
        num_sequences=VAL_SIZE, seq_len=SEQ_LEN,
        vocab_size=VOCAB_SIZE,
        meta_contexts=META_CONTEXTS,
        contexts=CONTEXTS,
        hidden_states=HIDDEN_STATES,
        meta_switch_prob=META_SWITCH_PROB,
        context_switch_prob=CONTEXT_SWITCH_PROB,
        state_switch_prob=STATE_SWITCH_PROB,
        intra_cluster_prob=INTRA_CLUSTER_PROB,
        inter_cluster_prob=INTER_CLUSTER_PROB,
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
    if gap > 0.1:
        print("✅ Ландшафт сложный, gap достаточный. Можно запускать grid search.")
        return True
    else:
        print("⚠️ Gap маловат. Рекомендуется увеличить сложность среды "
              "(уменьшить intra_cluster_prob, увеличить переключения).")
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

    # Уровни сложности среды (пара кортежей)
    complexity_levels = [
        (0.01, 0.05, 0.1, 0.7, 0.3),    # средняя сложность (как в sanity)
        (0.02, 0.1, 0.2, 0.5, 0.5),     # более хаотичная
        (0.005, 0.02, 0.05, 0.9, 0.1),  # более структурированная
    ]

    print(f"\nUsing device: {DEVICE}")
    results = run_grid_search(
        model_sizes=model_sizes,
        gain_vals=gain_vals,
        temp_vals=temp_vals,
        complexity_levels=complexity_levels,
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