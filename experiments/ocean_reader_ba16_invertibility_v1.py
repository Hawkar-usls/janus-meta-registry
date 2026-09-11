#!/usr/bin/env python3
"""
JANUS Ocean Reader / BA16 Invertibility v1

Open-reference simulation derived from the parameter structure of:
  https://github.com/uwa-channels/python/blob/main/tests/test_replay.py
  blob cded574e0ad62c6e87f29c0b86b51b89991eba16

IMPORTANT:
- This script does NOT load the raw field-derived UWA MAT files.
- It is an underwater-acoustic-inspired open-reference simulation.
- The BA16 quotient is a toy identifiability control: middle provenance bits j
  are deliberately erased before the channel.
"""

import json
import platform
import sys
import numpy as np
from scipy.signal import fftconvolve
from scipy.stats import binomtest
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

C = 1500.0
FS = 10_000
FC = 12_000
TMP = 15e-3
COEFF = 1.5
D = 0.5
SPS = 12
BASE_DELAYS_MS = np.array([0, 2, 6, 8, 10, 11, 12, 13], dtype=float)
MISMATCH_DELAYS_MS = np.array([0, 1, 3, 6, 10, 12, 13, 14], dtype=float)

def bits6(v):
    return np.array([(v >> b) & 1 for b in range(5, -1, -1)], dtype=int)

def j_of(v):
    return (v >> 2) & 0b11

def cls_ik(v):
    b = bits6(v)
    return int("".join(map(str, np.r_[b[:2], b[4:]])), 2)

def waveform(v, erase_j=False):
    b = bits6(v).copy()
    if erase_j:
        b[2:4] = 0
    return np.repeat((2 * b - 1).astype(float), SPS)

def make_h(receiver_index=0, delays_ms=BASE_DELAYS_MS, common_reference=False):
    delays_s = delays_ms / 1000 + receiver_index * D / C
    if not common_reference:
        delays_s -= delays_s.min()
    gains = np.exp(-delays_s * COEFF / TMP) * np.exp(-1j * 2 * np.pi * FC * delays_s)
    idx = np.round(delays_s * FS).astype(int)
    h = np.zeros(idx.max() + 1, dtype=complex)
    for ii, gain in zip(idx, gains):
        h[ii] += gain
    if not common_reference:
        h /= np.linalg.norm(h)
    return h

def build_templates(M=1, erase_j=False, delays_ms=BASE_DELAYS_MS, array_mode=False):
    hs = [make_h(m, delays_ms, common_reference=array_mode) for m in range(M)]
    rows = []
    max_len = 0
    per_value = []
    for v in range(64):
        x = waveform(v, erase_j=erase_j)
        ys = [fftconvolve(x, h) for h in hs]
        max_len = max(max_len, *(len(y) for y in ys))
        per_value.append(ys)
    for ys in per_value:
        rows.append(np.concatenate([np.pad(y, (0, max_len - len(y))) for y in ys]))
    return np.array(rows)

def normalize_rows(A):
    return A / np.linalg.norm(A, axis=1, keepdims=True)

def pad_cols(A, L):
    if A.shape[1] < L:
        return np.pad(A, ((0, 0), (0, L - A.shape[1])))
    return A[:, :L]

def nearest_decode(Y, template_norm):
    Yn = normalize_rows(Y)
    scores = np.real(Yn @ template_norm.conj().T)
    return scores.argmax(axis=1)

def noisy_trials(T, snr_db, reps, rng):
    truth = np.repeat(np.arange(64), reps)
    Y = T[truth].copy()
    p = np.mean(np.abs(Y) ** 2, axis=1, keepdims=True)
    snr = 10 ** (snr_db / 10)
    sigma = np.sqrt(p / snr / 2)
    noise = sigma * (rng.standard_normal(Y.shape) + 1j * rng.standard_normal(Y.shape))
    return truth, Y + noise

CANONICAL = [i * 16 + k for i in range(4) for k in range(4)]

def experiment_e1():
    Tf = build_templates(1, False)
    Tq = build_templates(1, True)
    Tfn = normalize_rows(Tf)
    Tq16n = normalize_rows(Tq[CANONICAL])
    out = []
    rng = np.random.default_rng(20260911)
    for snr in [-30, -25, -20, -15, -10]:
        truth, Y = noisy_trials(Tf, snr, 40, rng)
        full = float(np.mean(nearest_decode(Y, Tfn) == truth))
        qtruth, Yq = noisy_trials(Tq, snr, 40, rng)
        truecls = np.array([cls_ik(v) for v in qtruth])
        qacc = float(np.mean(nearest_decode(Yq, Tq16n) == truecls))
        out.append({"snr_db": snr, "full_source_accuracy": full, "quotient_class_accuracy": qacc})
    return out

def experiment_e2():
    vals = [34, 38, 42, 46]
    return {
        "collision_class": vals,
        "source_binary": {str(v): format(v, "06b") for v in vals},
        "quotient_binary": {str(v): format(v & 0b110011, "06b") for v in vals},
        "uniform_exact_member_ceiling": 0.25,
        "conditional_entropy_bits": 2,
    }

def experiment_e3():
    Tf = build_templates(1, False)
    Tq = build_templates(1, True)
    rows = []
    pooled_success = 0
    pooled_n = 0
    for ix, snr in enumerate([-15, -10, -5]):
        row = {"snr_db": snr}
        for label, T, off in [("full", Tf, 0), ("quotient", Tq, 100)]:
            rng = np.random.default_rng(424242 + ix + off)
            truth, Y = noisy_trials(T, snr, 30, rng)
            X = np.hstack([Y.real, Y.imag])
            y = np.array([j_of(v) for v in truth])
            Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=17, stratify=y)
            clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
            clf.fit(Xtr, ytr)
            pred = clf.predict(Xte)
            acc = float(np.mean(pred == yte))
            row[f"{label}_j_accuracy"] = acc
            if label == "quotient":
                successes = int(np.sum(pred == yte))
                n = len(yte)
                p = float(binomtest(successes, n, 0.25, alternative="greater").pvalue)
                row["quotient_one_sided_binomial_p"] = p
                pooled_success += successes
                pooled_n += n
        rows.append(row)
    pooled_p = float(binomtest(pooled_success, pooled_n, 0.25, alternative="greater").pvalue)
    return {"rows": rows, "pooled": {"successes": pooled_success, "n": pooled_n, "accuracy": pooled_success / pooled_n, "one_sided_binomial_p": pooled_p}}

def experiment_e4():
    Ttrue = build_templates(1, False, BASE_DELAYS_MS)
    Twrong = build_templates(1, False, MISMATCH_DELAYS_MS)
    L = max(Ttrue.shape[1], Twrong.shape[1])
    Ttrue = pad_cols(Ttrue, L)
    Twrong = pad_cols(Twrong, L)
    Tmatchn = normalize_rows(Ttrue)
    Twrongn = normalize_rows(Twrong)
    out = []
    for ix, snr in enumerate([-25, -20, -15, -10, -5, 0]):
        rng = np.random.default_rng(909090 + ix)
        truth, Y = noisy_trials(Ttrue, snr, 40, rng)
        out.append({"snr_db": snr, "matched_accuracy": float(np.mean(nearest_decode(Y, Tmatchn) == truth)), "mismatched_accuracy": float(np.mean(nearest_decode(Y, Twrongn) == truth))})
    return out

def experiment_e5():
    out = []
    for s_idx, snr in enumerate([-30, -25, -20, -15]):
        for M in [1, 2, 3]:
            rng = np.random.default_rng(13579 + s_idx * 10 + M)
            Tf = build_templates(M, False, array_mode=True)
            Tq = build_templates(M, True, array_mode=True)
            truth, Y = noisy_trials(Tf, snr, 30, rng)
            qtruth, Yq = noisy_trials(Tq, snr, 30, rng)
            out.append({"snr_db": snr, "receivers": M, "full_source_accuracy": float(np.mean(nearest_decode(Y, normalize_rows(Tf)) == truth)), "quotient_class_accuracy": float(np.mean(nearest_decode(Yq, normalize_rows(Tq[CANONICAL])) == np.array([cls_ik(v) for v in qtruth])))})
    return out

def experiment_e6():
    snr = -20
    reps = 150
    rng = np.random.default_rng(424200 + snr)
    Tf = build_templates(1, False)
    truth, Y = noisy_trials(Tf, snr, reps, rng)
    pred = nearest_decode(Y, normalize_rows(Tf))
    per = []
    for v in range(64):
        mask = truth == v
        per.append(float(np.mean(pred[mask] == v)))
    return {"snr_db": snr, "repetitions_per_source": reps, "mean_accuracy": float(np.mean(per)), "std_accuracy": float(np.std(per)), "min_accuracy": float(np.min(per)), "max_accuracy": float(np.max(per)), "packet_42_accuracy": per[42], "packet_42_rank_ascending_of_64": int(np.argsort(per).tolist().index(42) + 1)}

def main():
    result = {
        "model_class": "OPEN_REFERENCE_FIXTURE_SIMULATION__NOT_RAW_FIELD_MAT_REPLAY",
        "source_fixture": {"repository": "uwa-channels/python", "path": "tests/test_replay.py", "blob_sha": "cded574e0ad62c6e87f29c0b86b51b89991eba16"},
        "E1": experiment_e1(),
        "E2": experiment_e2(),
        "E3": experiment_e3(),
        "E4": experiment_e4(),
        "E5": experiment_e5(),
        "E6": experiment_e6(),
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform()},
    }
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
