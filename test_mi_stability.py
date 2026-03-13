# test_mi_stability_fixed.py
# Скрипт для проверки численной стабильности функции mutual_info
# на большом словаре (VOCAB_SIZE = 1000) с разными параметрами генерации.

import numpy as np
import random
import math

# Параметры
VOCAB_SIZE = 1000
N_SAMPLES = 100      # количество генерируемых последовательностей
MAX_LEN = 256        # длина каждой последовательности
SEED = 42            # для воспроизводимости
SMOOTHING_ALPHA = 1e-6  # сглаживание для избежания нулевых вероятностей

# ----------------------------------------------------------------------
# Копия функции compute_diversity_and_mi из v5 (с отладочным выводом и сглаживанием)
# ----------------------------------------------------------------------
def compute_diversity_and_mi_debug(samples, vocab_size, verbose=True, smoothing=True):
    """
    samples: список списков токенов (int)
    Возвращает diversity, mutual_info, а также печатает отладочную информацию.
    Если smoothing=True, применяется сглаживание (add-alpha) к совместным частотам.
    """
    if not samples:
        if verbose: print("⚠️ Пустой список samples")
        return 0.0, 0.0

    joint = np.zeros((vocab_size, vocab_size))
    total = 0
    for seq in samples:
        for i in range(len(seq)-1):
            a, b = seq[i], seq[i+1]
            if 0 <= a < vocab_size and 0 <= b < vocab_size:
                joint[a, b] += 1
                total += 1
    if verbose:
        print(f"🔢 Всего пар токенов: {total}")
        if total == 0:
            print("⚠️ Нет ни одной пары (total=0) – MI будет 0")
            return 0.0, 0.0

    unique = len(set(tuple(s) for s in samples))
    diversity = unique / len(samples)
    if verbose:
        print(f"📊 Diversity: {diversity:.4f}")

    # Сглаживание
    if smoothing:
        alpha = SMOOTHING_ALPHA
        joint = (joint + alpha) / (total + alpha * vocab_size**2)
        marg_x = joint.sum(axis=1)
        marg_y = joint.sum(axis=0)
    else:
        joint = joint / total
        marg_x = joint.sum(axis=1)
        marg_y = joint.sum(axis=0)

    mi = 0.0
    inf_count = 0
    nan_count = 0
    for i in range(vocab_size):
        for j in range(vocab_size):
            p = joint[i, j]
            if p > 0:
                q = marg_x[i] * marg_y[j]
                # При сглаживании q никогда не будет нулевым, но оставим защиту
                if q > 0:
                    val = p * np.log(p / q)
                else:
                    # Этот случай теперь не должен возникать при сглаживании
                    val = p * 30.0
                    if verbose:
                        print(f"   ⚠️ p>0, q=0 при i={i},j={j} -> val={val:.4f} (без сглаживания)")
                if not np.isfinite(val):
                    if np.isinf(val):
                        inf_count += 1
                    if np.isnan(val):
                        nan_count += 1
                    val = p * 30.0  # замена
                mi += val

    if verbose:
        print(f"🔄 Заменено inf: {inf_count}, nan: {nan_count}")
        print(f"🧮 MI = {mi:.6f}")

    # Финальная защита
    if not np.isfinite(mi):
        print("❌ MI всё ещё не finite после замен! Принудительно 0.")
        return diversity, 0.0
    return diversity, mi

# ----------------------------------------------------------------------
# Генерация случайных последовательностей (без модели)
# ----------------------------------------------------------------------
def generate_random_samples(n_samples, max_len, vocab_size, seed=None):
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
    samples = []
    for _ in range(n_samples):
        seq = [random.randint(0, vocab_size-1) for _ in range(max_len)]
        samples.append(seq)
    return samples

# ----------------------------------------------------------------------
# Тест 1: полностью случайные последовательности (нет структуры)
# ----------------------------------------------------------------------
print("="*60)
print("ТЕСТ 1: Полностью случайные последовательности")
print("="*60)
samples_rand = generate_random_samples(N_SAMPLES, MAX_LEN, VOCAB_SIZE, seed=SEED)
div, mi = compute_diversity_and_mi_debug(samples_rand, VOCAB_SIZE, verbose=True, smoothing=True)
print(f"Итог: diversity={div:.4f}, MI={mi:.6f}\n")

# ----------------------------------------------------------------------
# Тест 2: последовательности с повторами (первые 50 токенов одинаковы)
# ----------------------------------------------------------------------
print("="*60)
print("ТЕСТ 2: Последовательности с повторами (первые 50 токенов одинаковы)")
print("="*60)
samples_rep = []
for _ in range(N_SAMPLES):
    # Первые 50 токенов все одинаковые (0)
    seq = [0] * 50 + [random.randint(0, VOCAB_SIZE-1) for _ in range(MAX_LEN-50)]
    samples_rep.append(seq)
div, mi = compute_diversity_and_mi_debug(samples_rep, VOCAB_SIZE, verbose=True, smoothing=True)
print(f"Итог: diversity={div:.4f}, MI={mi:.6f}\n")

# ----------------------------------------------------------------------
# Тест 3: очень короткие последовательности (может быть total=0)
# ----------------------------------------------------------------------
print("="*60)
print("ТЕСТ 3: Очень короткие последовательности (длина 1)")
print("="*60)
samples_short = [[random.randint(0, VOCAB_SIZE-1)] for _ in range(N_SAMPLES)]
div, mi = compute_diversity_and_mi_debug(samples_short, VOCAB_SIZE, verbose=True, smoothing=True)
print(f"Итог: diversity={div:.4f}, MI={mi:.6f}\n")

# ----------------------------------------------------------------------
# Тест 4: одна последовательность (total = MAX_LEN-1)
# ----------------------------------------------------------------------
print("="*60)
print("ТЕСТ 4: Одна последовательность")
print("="*60)
samples_one = [generate_random_samples(1, MAX_LEN, VOCAB_SIZE, seed=SEED)[0]]
div, mi = compute_diversity_and_mi_debug(samples_one, VOCAB_SIZE, verbose=True, smoothing=True)
print(f"Итог: diversity={div:.4f}, MI={mi:.6f}\n")