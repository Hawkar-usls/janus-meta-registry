# quick_test_v2.py
# Быстрый тест влияния gain/temperature на квантовой микро-сети
# Использует quantum_core.py (v2.0) и словарь из 10 эмодзи.
# Запуск: python quick_test_v2.py

import random
import json
import math
import numpy as np
from quantum_core import QuantumEngine, SEMANTIC_DICT, Value, MicroGPT

# ------------------------------------------------------------------------------
# 1. Простой датасет (марковская цепь 1-го порядка)
# ------------------------------------------------------------------------------
def make_simple_dataset(vocab, num_seq=300, seq_len=20, seed=42):
    random.seed(seed)
    np.random.seed(seed)
    n = len(vocab)
    # матрица переходов: диагональ 0.5, остальные равномерно
    trans = np.full((n, n), 0.5 / (n-1))
    for i in range(n):
        trans[i, i] = 0.5
    trans = trans / trans.sum(axis=1, keepdims=True)
    data = []
    for _ in range(num_seq):
        seq = [random.randint(0, n-1)]
        for _ in range(seq_len-1):
            seq.append(np.random.choice(n, p=trans[seq[-1]]))
        data.append(''.join(vocab[i] for i in seq))
    return data

def compute_diversity_and_mi(samples, vocab):
    n = len(vocab)
    unique = len(set(samples))
    diversity = unique / len(samples)
    joint = np.zeros((n, n))
    for s in samples:
        for i in range(len(s)-1):
            a = vocab.index(s[i])
            b = vocab.index(s[i+1])
            joint[a, b] += 1
    total = joint.sum()
    if total == 0:
        return diversity, 0.0
    joint /= total
    marg_x = joint.sum(axis=1)
    marg_y = joint.sum(axis=0)
    mi = 0.0
    for i in range(n):
        for j in range(n):
            if joint[i, j] > 0:
                mi += joint[i, j] * np.log(joint[i, j] / (marg_x[i] * marg_y[j] + 1e-12))
    return diversity, mi

# ------------------------------------------------------------------------------
# 2. Основной тест
# ------------------------------------------------------------------------------
def test_gain_temp():
    vocab = list(SEMANTIC_DICT.values())
    print("Словарь (эмодзи):", vocab)
    train_data = make_simple_dataset(vocab, num_seq=300, seq_len=20)
    val_data = make_simple_dataset(vocab, num_seq=100, seq_len=20)

    gain_vals = [0.5, 1.0, 1.5, 2.0]
    temp_vals = [0.5, 1.0, 1.5]
    results = []

    for gain in gain_vals:
        for temp in temp_vals:
            print(f"\n--- Тест gain={gain}, temp={temp} ---")
            # Новый движок с чистыми весами
            engine = QuantumEngine()
            engine.vocab = vocab
            engine.vocab_size = len(vocab)
            engine.model = MicroGPT(vocab_size=engine.vocab_size,
                                     n_layer=1, n_embd=16, block_size=16, n_head=2)

            steps = 500  # достаточно для демонстрации
            for step in range(steps):
                doc = random.choice(train_data)
                ids = [vocab.index(ch) for ch in doc if ch in vocab]
                if len(ids) < 2:
                    continue
                n = min(engine.model.block_size, len(ids)-1)
                keys = [[] for _ in range(engine.model.n_layer)]
                values = [[] for _ in range(engine.model.n_layer)]
                losses = []
                for pos in range(n):
                    token_id = ids[pos]
                    target_id = ids[pos+1]
                    logits = engine.model.forward(token_id, pos, keys, values)
                    # применяем gain и temperature
                    logits_scaled = [l * gain for l in logits]
                    logits_temp = [l / temp for l in logits_scaled]
                    probs = engine.model.softmax(logits_temp)
                    loss_t = -probs[target_id].log()
                    losses.append(loss_t)
                if not losses:
                    continue
                loss = (1.0 / n) * sum(losses, Value(0.0))
                if math.isnan(loss.data):
                    continue
                loss.backward()
                for p in engine.model.params:
                    if p.grad is not None:
                        p.grad = max(-1.0, min(1.0, p.grad))
                        p.data -= 0.01 * p.grad
                        p.grad = 0
                if step % 100 == 0:
                    print(f"step {step}, loss {loss.data:.4f}")

            # Генерация и оценка
            samples = []
            for _ in range(100):
                js = engine._sync_hallucinate(entropy=50, max_len=11)
                data = json.loads(js)
                samples.append(data['cipher'])
            div, mi = compute_diversity_and_mi(samples, vocab)
            print(f"diversity={div:.3f}, mutual_info={mi:.3f}")
            results.append((gain, temp, div, mi))

    print("\n=== ИТОГОВАЯ ТАБЛИЦА ===")
    print("gain\ttemp\tdiv\tmi")
    for gain, temp, div, mi in results:
        print(f"{gain:.1f}\t{temp:.1f}\t{div:.3f}\t{mi:.3f}")

if __name__ == "__main__":
    test_gain_temp()