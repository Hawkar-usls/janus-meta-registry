# adaptive_quantum_benchmark.py
# Адаптивный бенчмарк для микро-сети на эмодзи-словаре.
# Для каждой комбинации gain/temperature:
#   - обучение на фиксированном датасете низкой сложности,
#   - вывод метрик на каждом eval шаге,
#   - адаптивный тест с повышением сложности до предела,
#   - фиксация максимальной преодолённой сложности.

import random
import math
import json
import time
import unicodedata
import numpy as np

# ==============================================================================
# 1. МИКРО-СЕТЬ (Value, MicroGPT, QuantumEngine) – без изменений
# ==============================================================================

class Value:
    __slots__ = ('data', 'grad', '_children', '_local_grads')
    def __init__(self, data, children=(), local_grads=()):
        self.data = data
        self.grad = 0.0
        self._children = children
        self._local_grads = local_grads

    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        return Value(self.data + other.data, (self, other), (1, 1))

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        return Value(self.data * other.data, (self, other), (other.data, self.data))

    def __pow__(self, other):
        return Value(self.data**other, (self,), (other * self.data**(other-1),))

    def log(self):
        val = self.data if self.data > 1e-15 else 1e-15
        return Value(math.log(val), (self,), (1/val,))

    def exp(self):
        return Value(math.exp(self.data), (self,), (math.exp(self.data),))

    def relu(self):
        return Value(max(0, self.data), (self,), (float(self.data > 0),))

    def __neg__(self): return self * -1
    def __radd__(self, other): return self + other
    def __sub__(self, other): return self + (-other)
    def __rsub__(self, other): return other + (-self)
    def __rmul__(self, other): return self * other
    def __truediv__(self, other): return self * other**-1

    def backward(self):
        topo = []
        visited = set()
        def build_topo(v):
            if v not in visited:
                visited.add(v)
                for child in v._children:
                    build_topo(child)
                topo.append(v)
        build_topo(self)
        self.grad = 1.0
        for v in reversed(topo):
            for child, local_grad in zip(v._children, v._local_grads):
                child.grad += local_grad * v.grad

class MicroGPT:
    def __init__(self, vocab_size, n_layer=1, n_embd=16, block_size=16, n_head=4):
        self.vocab_size = max(vocab_size, 3)
        self.n_layer = n_layer
        self.n_embd = n_embd
        self.block_size = block_size
        self.n_head = n_head
        self.head_dim = n_embd // n_head

        matrix = lambda nout, nin, std=0.08: [[Value(random.gauss(0, std)) for _ in range(nin)] for _ in range(nout)]

        self.state_dict = {
            'wte': matrix(self.vocab_size, n_embd),
            'wpe': matrix(block_size, n_embd),
            'lm_head': matrix(self.vocab_size, n_embd)
        }
        for i in range(n_layer):
            self.state_dict[f'layer{i}.attn_wq'] = matrix(n_embd, n_embd)
            self.state_dict[f'layer{i}.attn_wk'] = matrix(n_embd, n_embd)
            self.state_dict[f'layer{i}.attn_wv'] = matrix(n_embd, n_embd)
            self.state_dict[f'layer{i}.attn_wo'] = matrix(n_embd, n_embd)
            self.state_dict[f'layer{i}.mlp_fc1'] = matrix(4 * n_embd, n_embd)
            self.state_dict[f'layer{i}.mlp_fc2'] = matrix(n_embd, 4 * n_embd)

        self.params = [p for mat in self.state_dict.values() for row in mat for p in row]

    def linear(self, x, w):
        return [sum(wi * xi for wi, xi in zip(wo, x)) for wo in w]

    def softmax(self, logits):
        max_val = max(val.data if isinstance(val, Value) else val for val in logits)
        exps = [(val - max_val).exp() if isinstance(val, Value) else math.exp(val - max_val) for val in logits]
        total = sum(e.data if isinstance(e, Value) else e for e in exps)
        return [e / total for e in exps]

    def rmsnorm(self, x):
        ms = sum(xi.data * xi.data if isinstance(xi, Value) else xi * xi for xi in x) / len(x)
        return [xi * ((ms + 1e-5) ** -0.5) for xi in x]

    def forward(self, token_id, pos_id, keys, values):
        x = self.rmsnorm([t + p for t, p in zip(self.state_dict['wte'][token_id], self.state_dict['wpe'][pos_id])])
        for li in range(self.n_layer):
            x_residual = x
            x = self.rmsnorm(x)
            q = self.linear(x, self.state_dict[f'layer{li}.attn_wq'])
            k = self.linear(x, self.state_dict[f'layer{li}.attn_wk'])
            v = self.linear(x, self.state_dict[f'layer{li}.attn_wv'])
            keys[li].append(k)
            values[li].append(v)
            x_attn = []
            for h in range(self.n_head):
                hs = h * self.head_dim
                q_h = q[hs:hs+self.head_dim]
                k_h = [ki[hs:hs+self.head_dim] for ki in keys[li]]
                v_h = [vi[hs:hs+self.head_dim] for vi in values[li]]
                attn_logits = [sum(q_h[j] * k_h[t][j] for j in range(self.head_dim)) / (self.head_dim**0.5) for t in range(len(k_h))]
                attn_weights = self.softmax(attn_logits)
                x_attn.extend([sum(attn_weights[t] * v_h[t][j] for t in range(len(v_h))) for j in range(self.head_dim)])
            x = [a + b for a, b in zip(self.linear(x_attn, self.state_dict[f'layer{li}.attn_wo']), x_residual)]
            x_residual = x
            x = self.rmsnorm(x)
            x = [xi.relu() for xi in self.linear(x, self.state_dict[f'layer{li}.mlp_fc1'])]
            x = [a + b for a, b in zip(self.linear(x, self.state_dict[f'layer{li}.mlp_fc2']), x_residual)]
        return self.linear(x, self.state_dict['lm_head'])

class QuantumEngine:
    def __init__(self):
        self.model = None
        self.vocab = []
        self.vocab_size = 0

    def _sync_hallucinate(self, entropy=50, max_len=11):
        if not self.model:
            return json.dumps({"cipher": "\u274C", "semantics": ["error"]}, ensure_ascii=True)
        keys = [[] for _ in range(self.model.n_layer)]
        values = [[] for _ in range(self.model.n_layer)]
        start_id = random.randint(0, self.vocab_size - 1)
        sample_ids = [start_id]
        for pos in range(1, max_len):
            logits = self.model.forward(sample_ids[-1], pos % self.model.block_size, keys, values)
            temp = max(0.1, (entropy / 100.0) * 2.0)
            raw_logits = [l.data / temp for l in logits]
            max_val = max(raw_logits)
            exps = [math.exp(v - max_val) for v in raw_logits]
            probs = [e / sum(exps) for e in exps]
            next_id = random.choices(range(self.vocab_size), weights=probs)[0]
            sample_ids.append(next_id)
        quanta = [self.vocab[i] for i in sample_ids]
        result = {
            "cipher": "".join(quanta),
            "semantics": ["unknown"]*len(quanta),
            "entropy_state": entropy
        }
        return json.dumps(result, ensure_ascii=True)

# ==============================================================================
# 2. СЛОВАРЬ (наскальный язык) – 10 эмодзи (нормализованные)
# ==============================================================================
SEMANTIC_DICT = {
    "analyze": "\U0001F50D",   # 🔍
    "protect": "\U0001F6E1",   # 🛡️
    "evolve": "\U0001F9EC",    # 🧬
    "danger": "\u26A0\uFE0F",  # ⚠️
    "system": "\U0001F916",    # 🤖
    "memory": "\U0001F4BE",    # 💾
    "idea": "\U0001F4A1",      # 💡
    "connect": "\U0001F517",   # 🔗
    "delete": "\u274C",        # ❌
    "approve": "\u2705"        # ✅
}
VOCAB = list(SEMANTIC_DICT.values())
VOCAB_NORM = [unicodedata.normalize('NFC', s) for s in VOCAB]

# ==============================================================================
# 3. ДАТАСЕТ С ПЕРЕМЕННОЙ СЛОЖНОСТЬЮ (как в DovoD5)
# ==============================================================================
def make_hierarchical_dataset(num_sequences, seq_len, hidden_states, contexts, meta_contexts,
                              intra_cluster_prob, switch_prob, seed=42):
    """Генерирует иерархический датасет с фиксированным словарём VOCAB (10 эмодзи)."""
    random.seed(seed)
    np.random.seed(seed)
    vocab_size = len(VOCAB)

    # Разбиваем словарь на кластеры (hidden_states групп)
    cluster_size = vocab_size // hidden_states
    clusters = []
    for h in range(hidden_states):
        start = h * cluster_size
        end = start + cluster_size if h < hidden_states - 1 else vocab_size
        clusters.append(list(range(start, end)))

    # Матрицы переходов
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
                row_sums = P.sum(axis=1, keepdims=True)
                row_sums[row_sums == 0] = 1
                P = P / row_sums
                trans[mc, ctx, hs] = P

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
        # преобразуем индексы в символы словаря
        seq_str = ''.join(VOCAB[i] for i in tokens)
        data.append(seq_str)
    return data

# ==============================================================================
# 4. МЕТРИКИ
# ==============================================================================
def compute_entropy(probs):
    eps = 1e-12
    return -sum(p * math.log(p+eps) for p in probs)

def compute_mutual_info(samples, vocab):
    vocab_norm = [unicodedata.normalize('NFC', s) for s in vocab]
    samples_norm = [unicodedata.normalize('NFC', s) for s in samples]
    n = len(vocab_norm)
    joint = np.zeros((n, n))
    for s in samples_norm:
        for i in range(len(s)-1):
            try:
                a = vocab_norm.index(s[i])
                b = vocab_norm.index(s[i+1])
                joint[a, b] += 1
            except ValueError:
                continue
    total = joint.sum()
    if total == 0:
        return 0.0
    joint /= total
    marg_x = joint.sum(axis=1)
    marg_y = joint.sum(axis=0)
    mi = 0.0
    for i in range(n):
        for j in range(n):
            if joint[i,j] > 0:
                mi += joint[i,j] * math.log(joint[i,j] / (marg_x[i] * marg_y[j] + 1e-12))
    return mi

def compute_diversity(samples):
    unique = len(set(samples))
    return unique / len(samples)

def compute_perplexity(loss):
    return math.exp(loss)

# ==============================================================================
# 5. ОБУЧЕНИЕ МОДЕЛИ С ВЫВОДОМ МЕТРИК
# ==============================================================================
def train_model(engine, train_data, val_data, gain, temperature, steps=5000, eval_every=1000, lr=0.01):
    engine.model = MicroGPT(vocab_size=engine.vocab_size, n_layer=1, n_embd=16, block_size=16, n_head=2)
    history = {'step': [], 'train_loss': [], 'val_loss': [], 'perplexity': [], 'entropy': [], 'diversity': [], 'mutual_info': []}

    for step in range(steps):
        doc = random.choice(train_data)
        ids = [engine.vocab.index(ch) for ch in doc if ch in engine.vocab]
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
            logits_scaled = [l * gain for l in logits]
            logits_temp = [l / temperature for l in logits_scaled]
            probs = engine.model.softmax(logits_temp)
            loss_t = -probs[target_id].log()
            losses.append(loss_t)
        if not losses:
            continue
        loss = (1.0 / n) * sum(losses, Value(0.0))
        if math.isnan(loss.data) or math.isinf(loss.data):
            print(f"step {step} NaN loss, skipping")
            continue
        loss.backward()
        for p in engine.model.params:
            if p.grad is not None:
                p.grad = max(-1.0, min(1.0, p.grad))
                p.data -= lr * p.grad
                p.grad = 0

        if step % eval_every == 0 and step > 0:
            # вычисляем val_loss
            val_loss = 0.0
            val_count = 0
            for doc_val in random.sample(val_data, min(50, len(val_data))):
                ids_val = [engine.vocab.index(ch) for ch in doc_val if ch in engine.vocab]
                if len(ids_val) < 2: continue
                n_val = min(engine.model.block_size, len(ids_val)-1)
                keys_val = [[] for _ in range(engine.model.n_layer)]
                values_val = [[] for _ in range(engine.model.n_layer)]
                for pos in range(n_val):
                    token_id = ids_val[pos]
                    target_id = ids_val[pos+1]
                    logits = engine.model.forward(token_id, pos, keys_val, values_val)
                    logits_scaled = [l * gain for l in logits]
                    logits_temp = [l / temperature for l in logits_scaled]
                    probs = engine.model.softmax(logits_temp)
                    loss_t = -probs[target_id].log()
                    val_loss += loss_t.data
                    val_count += 1
            if val_count > 0:
                val_loss /= val_count
            else:
                val_loss = loss.data

            # генерируем сэмплы для метрик
            samples = []
            for _ in range(50):
                js = engine._sync_hallucinate(entropy=50, max_len=11)
                data = json.loads(js)
                samples.append(data['cipher'])
            div = compute_diversity(samples)
            mi = compute_mutual_info(samples, engine.vocab)
            probs_vals = [0.0]  # упрощённо
            ent = 0.0
            history['step'].append(step)
            history['train_loss'].append(loss.data)
            history['val_loss'].append(val_loss)
            history['perplexity'].append(compute_perplexity(val_loss))
            history['entropy'].append(ent)
            history['diversity'].append(div)
            history['mutual_info'].append(mi)
            print(f"Step {step}: loss={loss.data:.4f}, val_loss={val_loss:.4f}, "
                  f"ppl={history['perplexity'][-1]:.4f}, H={ent:.3f}, diversity={div:.3f}, mi={mi:.4f}")

    # финальные метрики
    final = {k: v[-1] if v else None for k, v in history.items()}
    return history, final

# ==============================================================================
# 6. АДАПТИВНЫЙ ТЕСТ (как в DovoD5)
# ==============================================================================
def adaptive_test(engine, base_seed, gain, temperature, threshold=5.0):
    """Повышает сложность, пока val_loss < threshold. Возвращает максимальную сложность и последний loss."""
    # начальные параметры
    seq_len = 64
    hidden_states = 4
    contexts = 2
    meta_contexts = 1
    intra_cluster_prob = 0.8
    switch_prob = 0.1

    max_hidden = 20
    max_contexts = 8
    max_meta = 4

    complexity = 0
    while True:
        # генерируем тестовый набор
        test_data = make_hierarchical_dataset(
            num_sequences=50,
            seq_len=seq_len,
            hidden_states=hidden_states,
            contexts=contexts,
            meta_contexts=meta_contexts,
            intra_cluster_prob=intra_cluster_prob,
            switch_prob=switch_prob,
            seed=base_seed + complexity
        )
        # вычисляем val_loss
        total_loss = 0.0
        count = 0
        for doc in test_data:
            ids = [engine.vocab.index(ch) for ch in doc if ch in engine.vocab]
            if len(ids) < 2: continue
            n = min(engine.model.block_size, len(ids)-1)
            keys = [[] for _ in range(engine.model.n_layer)]
            values = [[] for _ in range(engine.model.n_layer)]
            for pos in range(n):
                token_id = ids[pos]
                target_id = ids[pos+1]
                logits = engine.model.forward(token_id, pos, keys, values)
                logits_scaled = [l * gain for l in logits]
                logits_temp = [l / temperature for l in logits_scaled]
                probs = engine.model.softmax(logits_temp)
                loss_t = -probs[target_id].log()
                total_loss += loss_t.data
                count += 1
        avg_loss = total_loss / count if count > 0 else 1e6
        print(f"   Уровень сложности {complexity}: loss={avg_loss:.4f} (seq_len={seq_len}, hidden={hidden_states}, ctx={contexts}, meta={meta_contexts}, intra={intra_cluster_prob:.2f}, switch={switch_prob:.2f})")
        if avg_loss > threshold:
            break

        complexity += 1
        if complexity % 5 == 0:
            seq_len = min(256, seq_len + 16)
        if complexity % 3 == 0:
            hidden_states = min(max_hidden, hidden_states + 1)
        if complexity % 4 == 0:
            contexts = min(max_contexts, contexts + 1)
        if complexity % 6 == 0:
            meta_contexts = min(max_meta, meta_contexts + 1)
        if complexity % 2 == 0:
            intra_cluster_prob = max(0.3, intra_cluster_prob - 0.05)
        if complexity % 2 == 0:
            switch_prob = min(0.8, switch_prob + 0.05)

    return complexity, avg_loss

# ==============================================================================
# 7. ОСНОВНОЙ ЦИКЛ
# ==============================================================================
def run_benchmark():
    vocab = VOCAB
    print("Словарь (эмодзи):", vocab)

    # фиксированный тренировочный датасет (низкая сложность)
    train_base = make_hierarchical_dataset(
        num_sequences=300,
        seq_len=64,
        hidden_states=4,
        contexts=2,
        meta_contexts=1,
        intra_cluster_prob=0.8,
        switch_prob=0.1,
        seed=42
    )
    val_base = make_hierarchical_dataset(
        num_sequences=100,
        seq_len=64,
        hidden_states=4,
        contexts=2,
        meta_contexts=1,
        intra_cluster_prob=0.8,
        switch_prob=0.1,
        seed=43
    )

    gain_vals = [0.5, 1.0, 1.5, 2.0]
    temp_vals = [0.5, 1.0, 1.5]
    all_results = []

    for gain in gain_vals:
        for temp in temp_vals:
            print(f"\n=== Тест gain={gain}, temp={temp} ===")
            engine = QuantumEngine()
            engine.vocab = vocab
            engine.vocab_size = len(vocab)

            # обучение
            history, final = train_model(engine, train_base, val_base, gain, temp,
                                         steps=2000, eval_every=500, lr=0.01)

            # адаптивный тест
            max_complexity, test_loss = adaptive_test(engine, 1000, gain, temp)

            all_results.append({
                'gain': gain,
                'temp': temp,
                'final_train_loss': final['train_loss'],
                'final_val_loss': final['val_loss'],
                'final_perplexity': final['perplexity'],
                'final_diversity': final['diversity'],
                'final_mutual_info': final['mutual_info'],
                'max_complexity': max_complexity,
                'test_loss': test_loss
            })

    print("\n=== ИТОГОВЫЕ РЕЗУЛЬТАТЫ ===")
    for r in all_results:
        print(f"gain={r['gain']:.1f}, temp={r['temp']:.1f}: "
              f"train_loss={r['final_train_loss']:.4f}, val_loss={r['final_val_loss']:.4f}, "
              f"ppl={r['final_perplexity']:.4f}, div={r['final_diversity']:.3f}, "
              f"mi={r['final_mutual_info']:.4f}, max_complexity={r['max_complexity']}")

if __name__ == "__main__":
    run_benchmark()