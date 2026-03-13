# janus_bayesian_optimizer.py
# Интеллектуальный взломщик сейфа для Януса (байесовская оптимизация)
# Версия 2.0 – Взломщик.

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

# Попытка импорта для байесовской оптимизации
try:
    from skopt import Optimizer as SkoptOptimizer
    from skopt.space import Real
    SKOPT_AVAILABLE = True
except ImportError:
    SKOPT_AVAILABLE = False
    print("\u26A0\uFE0F scikit-optimize не установлен. Байесовская оптимизация отключена.")

# ==============================================================================
# 1. ЮНИКОД-СЛОВАРЬ
# ==============================================================================
UNICODE_VOCAB = [chr(i) for i in range(0x0000, 0x03E8)]  # 1000 символов
VOCAB_SIZE = len(UNICODE_VOCAB)
print(f"Словарь создан: {VOCAB_SIZE} символов. Пример: '{UNICODE_VOCAB[0]}' -> '{UNICODE_VOCAB[10]}'")

# ==============================================================================
# 2. МИКРО-МОДЕЛЬ (та же)
# ==============================================================================
class MicroTransformer(nn.Module):
    def __init__(self, vocab_size, n_embd=32, n_head=2, n_layer=1, block_size=256):
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
# 3. ДАТАСЕТ (экстремальный)
# ==============================================================================
def make_extreme_dataset(num_sequences, seq_len=256, order=4, rare_prob=0.01, seed=42):
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    vocab_size = VOCAB_SIZE
    n_clusters = 10
    cluster_size = vocab_size // n_clusters
    clusters = []
    for c in range(n_clusters):
        start = c * cluster_size
        end = start + cluster_size if c < n_clusters - 1 else vocab_size
        clusters.append(list(range(start, end)))

    data = []
    for _ in range(num_sequences):
        tokens = [random.randint(0, vocab_size-1) for _ in range(order)]
        for pos in range(order, seq_len):
            if random.random() < rare_prob:
                nxt = random.randint(0, vocab_size-1)
            else:
                clusters_hist = [t // cluster_size for t in tokens[-order:]]
                if len(set(clusters_hist)) == 1:
                    cluster = clusters_hist[0]
                    nxt = random.choice(clusters[cluster])
                else:
                    nxt = random.randint(0, vocab_size-1)
            tokens.append(nxt)
        data.append(torch.tensor(tokens[-seq_len:]))
    return data

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

def generate_samples(model, n_samples=100, max_len=256, gain=1.0, temperature=1.0,
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
# 5. ОБУЧЕНИЕ КОНФИГУРАЦИИ (без изменений)
# ==============================================================================
def train_and_test(gain, temperature, train_data, val_data, n_seeds=3, steps=5000, lr=0.001, device='cpu'):
    all_results = []
    for seed in range(n_seeds):
        torch.manual_seed(seed)
        random.seed(seed)
        np.random.seed(seed)

        model = MicroTransformer(vocab_size=VOCAB_SIZE, n_embd=32, n_head=2, n_layer=1, block_size=256).to(device)
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

            samples = generate_samples(model, n_samples=100, max_len=256,
                                       gain=gain, temperature=temperature,
                                       vocab_size=VOCAB_SIZE, device=device)
            div, mi = compute_diversity_and_mi(samples, VOCAB_SIZE)

        all_results.append({'val_loss': val_loss, 'perplexity': perplexity, 'diversity': div, 'mutual_info': mi})

    avg_val_loss = np.mean([r['val_loss'] for r in all_results])
    avg_perplexity = np.mean([r['perplexity'] for r in all_results])
    avg_diversity = np.mean([r['diversity'] for r in all_results])
    avg_mi = np.mean([r['mutual_info'] for r in all_results])
    std_val_loss = np.std([r['val_loss'] for r in all_results])

    return {
        'gain': gain,
        'temperature': temperature,
        'val_loss': avg_val_loss,
        'std_val_loss': std_val_loss,
        'perplexity': avg_perplexity,
        'diversity': avg_diversity,
        'mutual_info': avg_mi,
        'seeds': n_seeds
    }

# ==============================================================================
# 6. ФИКСИРОВАННЫЙ ТРЕНИРОВОЧНЫЙ ДАТАСЕТ
# ==============================================================================
def make_base_training_set(seed=42, train_size=5000, val_size=1000):
    train_data = make_extreme_dataset(num_sequences=train_size, seq_len=256, order=4, rare_prob=0.01, seed=seed)
    val_data = make_extreme_dataset(num_sequences=val_size, seq_len=256, order=4, rare_prob=0.01, seed=seed+1000)
    return train_data, val_data

# ==============================================================================
# 7. БАЙЕСОВСКИЙ ОПТИМИЗАТОР (ВЗЛОМЩИК)
# ==============================================================================
class BayesianOptimizer:
    def __init__(self, log_file='bayes_log.json', csv_file='bayes_log.csv'):
        self.log_file = log_file
        self.csv_file = csv_file
        self.history = self.load_history()
        self.gain_range = (0.3, 2.5)
        self.temp_range = (0.3, 2.0)
        self.best_config = self.get_best_config()

        if SKOPT_AVAILABLE:
            self.space = [Real(self.gain_range[0], self.gain_range[1], name='gain'),
                          Real(self.temp_range[0], self.temp_range[1], name='temperature')]
            self.skopt = SkoptOptimizer(
                dimensions=self.space,
                base_estimator='GP',
                n_initial_points=5,
                acq_func='EI'
            )
            # Если есть история, передаём её в оптимизатор
            if self.history:
                X = [[r['gain'], r['temperature']] for r in self.history]
                y = [r['val_loss'] for r in self.history]  # минимизируем val_loss
                self.skopt.tell(X, y)
        else:
            self.skopt = None

    def load_history(self):
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def save_history(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)
        if self.history:
            keys = self.history[0].keys()
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(self.history)

    def get_best_config(self):
        if not self.history:
            return None
        best = min(self.history, key=lambda x: x.get('val_loss', float('inf')))
        return best

    def propose_new_config(self):
        if self.skopt is not None:
            x_next = self.skopt.ask()
            gain, temp = x_next[0], x_next[1]
        else:
            # Fallback на случайный поиск
            gain = random.uniform(*self.gain_range)
            temp = random.uniform(*self.temp_range)
        return round(gain, 3), round(temp, 3)

    def print_parameter_info(self, gain, temp):
        print("\n" + "="*60)
        print("🔍 ПАРАМЕТРЫ ТЕКУЩЕЙ КОНФИГУРАЦИИ")
        print("="*60)
        print(f"🔹 gain = {gain:.3f}")
        print("   Что это: множитель логитов перед softmax (усиление сигнала).")
        if gain < 0.8:
            print("   Эффект: gain < 1 заглушает сигнал, генерация более случайная, MI ниже.")
        elif gain > 1.2:
            print("   Эффект: gain > 1 усиливает предсказуемые паттерны, MI выше, но может привести к переобучению.")
        else:
            print("   Эффект: нейтральное усиление, баланс между случайностью и детерминизмом.")
        print(f"🔹 temperature = {temp:.3f}")
        print("   Что это: температура softmax при сэмплировании.")
        if temp < 0.8:
            print("   Эффект: низкая температура делает генерацию более уверенной, diversity падает, MI растёт.")
        elif temp > 1.2:
            print("   Эффект: высокая температура увеличивает случайность, diversity растёт, MI падает.")
        else:
            print("   Эффект: стандартная температура, нейтральный уровень случайности.")
        print("="*60)

    def print_metrics_info(self, result):
        print("\n📊 ПОЛУЧЕННЫЕ МЕТРИКИ")
        print("="*60)
        print(f"🔹 val_loss = {result['val_loss']:.4f} ± {result['std_val_loss']:.4f}")
        print("   Кросс-энтропия на валидации. Чем ниже, тем лучше модель предсказывает.")
        if result['val_loss'] < 4.0:
            print("   Модель справляется хорошо.")
        elif result['val_loss'] < 5.0:
            print("   Средний результат.")
        else:
            print("   Модель плохо справляется, возможно, среда слишком сложная.")
        print(f"🔹 perplexity = {result['perplexity']:.2f}")
        print("   exp(val_loss). Показывает, насколько модель «удивлена» данными.")
        print(f"🔹 diversity = {result['diversity']:.3f}")
        print("   Доля уникальных сгенерированных последовательностей. Близость к 1 означает, что модель не зацикливается.")
        if result['diversity'] > 0.95:
            print("   Разнообразие отличное, модель генерирует разные последовательности.")
        elif result['diversity'] > 0.8:
            print("   Хорошее разнообразие.")
        else:
            print("   Низкое разнообразие, возможно, модель застревает.")
        print(f"🔹 mutual_info = {result['mutual_info']:.4f}")
        print("   Взаимная информация между соседними токенами. Чем выше, тем сильнее структура.")
        if result['mutual_info'] > 0.5:
            print("   Сильные зависимости, модель улавливает структуру.")
        elif result['mutual_info'] > 0.2:
            print("   Умеренные зависимости.")
        else:
            print("   Слабые зависимости, генерация близка к случайной.")
        print("="*60)

    def run_cycle(self, train_data, val_data, device='cpu', steps=5000, n_seeds=3):
        gain, temp = self.propose_new_config()
        self.print_parameter_info(gain, temp)
        print(f"\n⚙️ Запуск эксперимента с gain={gain}, temp={temp}, seeds={n_seeds}...")

        result = train_and_test(gain, temp, train_data, val_data,
                                n_seeds=n_seeds, steps=steps, device=device)
        result['timestamp'] = datetime.now().isoformat()

        self.history.append(result)
        self.save_history()

        # Обновляем байесовский оптимизатор
        if self.skopt is not None:
            self.skopt.tell([[gain, temp]], [result['val_loss']])

        self.print_metrics_info(result)

        if self.best_config is None or result['val_loss'] < self.best_config['val_loss']:
            self.best_config = result
            print("\n✨ НОВЫЙ ЛУЧШИЙ РЕЗУЛЬТАТ! ✨")
        else:
            print(f"\n📉 Текущий результат хуже лучшего (лучший val_loss = {self.best_config['val_loss']:.4f})")

        return result

# ==============================================================================
# 8. ОСНОВНОЙ ЦИКЛ
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Байесовский взломщик сейфа для Януса")
    parser.add_argument('--steps', type=int, default=5000, help='Количество шагов обучения')
    parser.add_argument('--seeds', type=int, default=3, help='Число сидов для усреднения')
    parser.add_argument('--sleep', type=int, default=5, help='Пауза между циклами (сек)')
    parser.add_argument('--train_size', type=int, default=5000, help='Размер тренировочного набора')
    parser.add_argument('--val_size', type=int, default=1000, help='Размер валидационного набора')
    args = parser.parse_args()

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Используется устройство: {device}")

    print("Генерация экстремального датасета...")
    train_data, val_data = make_base_training_set(seed=42, train_size=args.train_size, val_size=args.val_size)
    print(f"Датасет готов: train={len(train_data)} последовательностей, val={len(val_data)}")

    optimizer = BayesianOptimizer(log_file='bayes_log.json', csv_file='bayes_log.csv')

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