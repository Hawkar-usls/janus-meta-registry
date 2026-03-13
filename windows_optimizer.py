# windows_optimizer.py
# Адаптивный оптимизатор для Windows (мощный ПК)
# Бесконечно ищет лучшие gain/temperature, сохраняет историю в JSON и CSV.

import os
import math
import random
import json
import time
import csv
import argparse
from datetime import datetime
from collections import defaultdict

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

# ==============================================================================
# 1. ЮНИКОД-СЛОВАРЬ (первые 1000 символов Unicode)
# ==============================================================================
UNICODE_VOCAB = [chr(i) for i in range(0x0000, 0x03E8)]  # 1000 символов
VOCAB_SIZE = len(UNICODE_VOCAB)
print(f"Словарь создан: {VOCAB_SIZE} символов. Пример: '{UNICODE_VOCAB[0]}' -> '{UNICODE_VOCAB[10]}'")

# ==============================================================================
# 2. МИКРО-МОДЕЛЬ (можно увеличить для ПК)
# ==============================================================================
class MicroTransformer(nn.Module):
    def __init__(self, vocab_size, n_embd=64, n_head=4, n_layer=2, block_size=32):
        super().__init__()
        self.vocab_size = vocab_size
        self.n_embd = n_embd
        self.block_size = block_size
        self.n_head = n_head
        self.n_layer = n_layer
        self.head_dim = n_embd // n_head
        assert self.head_dim * n_head == n_embd

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
# 3. ДАТАСЕТ (фиксированный, можно сделать побольше)
# ==============================================================================
def make_fixed_dataset(seed=42, train_size=2000, val_size=500):
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    # Создаём случайную матрицу переходов для пар токенов
    trans = np.random.dirichlet(np.ones(VOCAB_SIZE), size=(VOCAB_SIZE, VOCAB_SIZE))
    trans = torch.tensor(trans, dtype=torch.float32)

    train_data = []
    for _ in range(train_size):
        tokens = [random.randint(0, VOCAB_SIZE-1), random.randint(0, VOCAB_SIZE-1)]
        for _ in range(30):  # seq_len 32
            prev2 = tokens[-2]
            prev1 = tokens[-1]
            probs = trans[prev2, prev1]
            next_tok = torch.multinomial(probs, 1).item()
            tokens.append(next_tok)
        train_data.append(torch.tensor(tokens))

    val_data = []
    for _ in range(val_size):
        tokens = [random.randint(0, VOCAB_SIZE-1), random.randint(0, VOCAB_SIZE-1)]
        for _ in range(30):
            prev2 = tokens[-2]
            prev1 = tokens[-1]
            probs = trans[prev2, prev1]
            next_tok = torch.multinomial(probs, 1).item()
            tokens.append(next_tok)
        val_data.append(torch.tensor(tokens))

    return train_data, val_data

# ==============================================================================
# 4. МЕТРИКИ
# ==============================================================================
def compute_perplexity(loss):
    return math.exp(loss)

def compute_diversity_and_mi(samples, vocab_size):
    joint = np.zeros((vocab_size, vocab_size))
    total = 0
    for seq in samples:
        for i in range(len(seq)-1):
            a, b = seq[i], seq[i+1]
            joint[a, b] += 1
            total += 1
    if total == 0:
        return 0.0, 0.0

    unique = len(set(tuple(s) for s in samples))
    diversity = unique / len(samples)

    joint /= total
    marg_x = joint.sum(axis=1)
    marg_y = joint.sum(axis=0)
    mi = 0.0
    for i in range(vocab_size):
        for j in range(vocab_size):
            if joint[i, j] > 0:
                mi += joint[i, j] * math.log(joint[i, j] / (marg_x[i] * marg_y[j] + 1e-12))
    return diversity, mi

def generate_samples(model, n_samples=100, max_len=32, gain=1.0, temperature=1.0,
                     vocab_size=VOCAB_SIZE, device='cpu', seed=None):
    if seed is not None:
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
    return samples

# ==============================================================================
# 5. ОБУЧЕНИЕ ОДНОЙ КОНФИГУРАЦИИ (среднее по нескольким seed)
# ==============================================================================
def train_config(gain, temperature, train_data, val_data, steps=5000, lr=0.001,
                 n_seeds=3, device='cpu'):
    """
    Обучает модель с фиксированными gain/temperature на n_seeds разных инициализациях,
    возвращает усреднённые метрики.
    """
    all_results = []
    for seed in range(n_seeds):
        torch.manual_seed(seed)
        random.seed(seed)
        np.random.seed(seed)

        model = MicroTransformer(vocab_size=VOCAB_SIZE, n_embd=64, n_head=4, n_layer=2, block_size=32).to(device)
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

        # финальная оценка
        model.eval()
        with torch.no_grad():
            val_loss = 0.0
            val_count = 0
            for val_seq in random.sample(val_data, min(200, len(val_data))):
                val_seq = val_seq.to(device)
                logits_val = model(val_seq)
                shift_logits_val = logits_val[:-1, :]
                shift_labels_val = val_seq[1:]
                shift_logits_val_scaled = shift_logits_val * gain
                shift_logits_val_temp = shift_logits_val_scaled / temperature
                val_loss += F.cross_entropy(shift_logits_val_temp, shift_labels_val, reduction='sum').item()
                val_count += (val_seq.size(0)-1)
            val_loss /= val_count
            perplexity = compute_perplexity(val_loss)

            samples = generate_samples(model, n_samples=100, max_len=32,
                                       gain=gain, temperature=temperature,
                                       vocab_size=VOCAB_SIZE, device=device)
            div, mi = compute_diversity_and_mi(samples, VOCAB_SIZE)

        all_results.append({
            'val_loss': val_loss,
            'perplexity': perplexity,
            'diversity': div,
            'mutual_info': mi
        })

    # усредняем
    avg_val_loss = np.mean([r['val_loss'] for r in all_results])
    avg_perplexity = np.mean([r['perplexity'] for r in all_results])
    avg_diversity = np.mean([r['diversity'] for r in all_results])
    avg_mi = np.mean([r['mutual_info'] for r in all_results])

    return {
        'gain': gain,
        'temperature': temperature,
        'val_loss': avg_val_loss,
        'perplexity': avg_perplexity,
        'diversity': avg_diversity,
        'mutual_info': avg_mi,
        'seeds': n_seeds
    }

# ==============================================================================
# 6. АДАПТИВНЫЙ ОПТИМИЗАТОР
# ==============================================================================
class EvolutionOptimizer:
    def __init__(self, log_file='evolution_log.json', csv_file='evolution_log.csv'):
        self.log_file = log_file
        self.csv_file = csv_file
        self.history = self.load_history()
        self.best_config = self.get_best_config()
        self.gain_range = (0.3, 2.5)
        self.temp_range = (0.3, 2.0)

    def load_history(self):
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def save_history(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)
        # также сохраняем в CSV для удобного анализа
        if self.history:
            keys = self.history[0].keys()
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(self.history)

    def get_best_config(self):
        if not self.history:
            return None
        # сортируем по val_loss (меньше лучше)
        best = min(self.history, key=lambda x: x.get('val_loss', float('inf')))
        return best

    def propose_new_config(self):
        # Простая стратегия: случайный поиск с окрестностью лучшего
        if self.best_config and random.random() < 0.5:
            # локальный поиск
            gain = self.best_config['gain'] + random.uniform(-0.2, 0.2)
            temp = self.best_config['temperature'] + random.uniform(-0.2, 0.2)
            gain = max(self.gain_range[0], min(self.gain_range[1], gain))
            temp = max(self.temp_range[0], min(self.temp_range[1], temp))
        else:
            # чистый random
            gain = random.uniform(*self.gain_range)
            temp = random.uniform(*self.temp_range)
        return round(gain, 3), round(temp, 3)

    def run_cycle(self, train_data, val_data, device='cpu', steps=5000, n_seeds=3):
        gain, temp = self.propose_new_config()
        print(f"\n=== Новая попытка: gain={gain}, temp={temp} ===")
        result = train_config(gain, temp, train_data, val_data,
                              steps=steps, n_seeds=n_seeds, device=device)
        result['timestamp'] = datetime.now().isoformat()

        self.history.append(result)
        self.save_history()

        if self.best_config is None or result['val_loss'] < self.best_config['val_loss']:
            self.best_config = result
            print(f"🎉 НОВЫЙ ЛУЧШИЙ! val_loss={result['val_loss']:.4f}, gain={gain}, temp={temp}")
        else:
            print(f"Текущий результат: val_loss={result['val_loss']:.4f} (лучший={self.best_config['val_loss']:.4f})")

        return result

# ==============================================================================
# 7. ОСНОВНОЙ ЦИКЛ (бесконечный) с возможностью остановки и продолжения
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Адаптивный оптимизатор для Windows")
    parser.add_argument('--steps', type=int, default=5000, help='Количество шагов обучения')
    parser.add_argument('--seeds', type=int, default=3, help='Число сидов для усреднения')
    parser.add_argument('--sleep', type=int, default=5, help='Пауза между циклами (сек)')
    parser.add_argument('--train_size', type=int, default=2000, help='Размер тренировочного набора')
    parser.add_argument('--val_size', type=int, default=500, help='Размер валидационного набора')
    parser.add_argument('--n_embd', type=int, default=64, help='Размер эмбеддинга')
    parser.add_argument('--n_layer', type=int, default=2, help='Число слоёв')
    args = parser.parse_args()

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Используется устройство: {device}")

    # Генерируем фиксированный датасет один раз
    print("Генерация датасета...")
    train_data, val_data = make_fixed_dataset(seed=42, train_size=args.train_size, val_size=args.val_size)
    print(f"Датасет готов: train={len(train_data)}, val={len(val_data)}")

    optimizer = EvolutionOptimizer()

    if not optimizer.history:
        print("Начинаем новую эволюцию. Первые результаты могут быть случайными.")
    else:
        best = optimizer.best_config
        print(f"Загружено {len(optimizer.history)} экспериментов. Лучший: gain={best['gain']}, temp={best['temperature']}, val_loss={best['val_loss']:.4f}")

    try:
        while True:
            optimizer.run_cycle(train_data, val_data, device=device,
                                steps=args.steps, n_seeds=args.seeds)
            print(f"Пауза {args.sleep} секунд...")
            time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\nЭволюция остановлена пользователем. Результаты сохранены.")
        optimizer.save_history()