import math
import time
import csv
import os
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import logging
from config import VOCAB_SIZE, DEVICE, RAW_LOGS_DIR, LR_DECAY_ENABLE, HALF_LIFE_STEPS, DEBUG_MODE

logger = logging.getLogger("JANUS")
torch.backends.cudnn.benchmark = True

STEP_LOG_FILE = os.path.join(RAW_LOGS_DIR, "step_log.csv")
GRAD_LOG_FILE = os.path.join(RAW_LOGS_DIR, "grad_log.csv")

class AdaptiveTransformer(nn.Module):
    def __init__(self, n_embd, n_head, n_layer, block_size=256):
        super().__init__()
        self.block_size = block_size
        self.wte = nn.Embedding(VOCAB_SIZE, n_embd)
        self.wpe = nn.Embedding(block_size, n_embd)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=n_embd, nhead=n_head, dim_feedforward=4*n_embd,
            dropout=0.1, activation='relu', batch_first=True, norm_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layer, enable_nested_tensor=False)
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, VOCAB_SIZE, bias=False)

    def forward(self, idx):
        seq_len = min(idx.size(1), self.block_size)
        idx = idx[:, :seq_len]
        pos = torch.arange(0, seq_len, device=idx.device)
        x = self.wte(idx) + self.wpe(pos)[None, :, :]
        mask = torch.triu(torch.ones(seq_len, seq_len, device=idx.device) * float('-inf'), diagonal=1)
        x = self.transformer_encoder(x, mask=mask)
        return self.lm_head(self.ln_f(x))

def _train_worker(seed, config, train_t, val_t, steps, batch_size=None, device=DEVICE):
    torch.manual_seed(seed)
    model = AdaptiveTransformer(config['n_embd'], config['n_head'], config['n_layer']).to(device)
    base_lr = config['lr']
    optimizer = torch.optim.Adam(model.parameters(), lr=base_lr)
    scaler = torch.amp.GradScaler('cuda', enabled=(device.type == 'cuda'))
    
    if batch_size is None:
        batch_size = config.get('batch_size', 256)
    
    train_losses = []
    grad_norms = []
    
    if device.type == 'cuda':
        torch.cuda.reset_peak_memory_stats()
        
    start_time = time.time()
    model.train()
    
    aborted = False
    decay_enabled = config.get('lr_decay_enable', LR_DECAY_ENABLE)
    half_life = config.get('half_life_steps', HALF_LIFE_STEPS)
    lambda_decay = math.log(2) / half_life if decay_enabled else 0.0
    
    for step in range(steps):
        if lambda_decay > 0:
            current_lr = base_lr * math.exp(-lambda_decay * step)
            for param_group in optimizer.param_groups:
                param_group['lr'] = current_lr

        idx = torch.randint(0, train_t.size(0), (batch_size,), device=device)
        batch = train_t[idx]
        x, y = batch[:, :-1], batch[:, 1:]
        
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast('cuda', enabled=(device.type == 'cuda')):
            logits = model(x)
            loss = F.cross_entropy(logits.reshape(-1, VOCAB_SIZE), y.reshape(-1))
            
        if step % 100 == 0:
            train_losses.append(loss.item())

        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        gn_val = grad_norm.item()
        
        if math.isnan(gn_val) or gn_val > 20.0 or math.isinf(gn_val):
            aborted = True
            break
            
        grad_norms.append(gn_val)
        scaler.step(optimizer)
        scaler.update()

    if aborted:
        if device.type == 'cuda':
            torch.cuda.empty_cache()
        return (None,) * 11  

    train_loss_avg = np.mean(train_losses) if train_losses else float('inf')
    gn_min = float(np.min(grad_norms)) if grad_norms else 0.0
    gn_max = float(np.max(grad_norms)) if grad_norms else 0.0
    gn_mean = float(np.mean(grad_norms)) if grad_norms else 0.0
    weight_norm = sum(p.norm().item() for p in model.parameters() if p.requires_grad)
    vram_mb = torch.cuda.max_memory_allocated() / (1024**2) if device.type == 'cuda' else 0
    actual_steps = len(grad_norms) if grad_norms else 1
    step_time_ms = ((time.time() - start_time) / actual_steps) * 1000

    model.eval()
    with torch.no_grad():
        val_idx = torch.randint(0, val_t.size(0), (min(500, val_t.size(0)),), device=device)
        val_batch = val_t[val_idx]
        val_x, val_y = val_batch[:, :-1], val_batch[:, 1:]
        
        with torch.amp.autocast('cuda', enabled=(device.type == 'cuda')):
            logits_val = model(val_x)
            val_loss = F.cross_entropy(logits_val.reshape(-1, VOCAB_SIZE), val_y.reshape(-1)).item()
            
        num_samples, gen_len = 100, 100
        tokens = torch.randint(0, VOCAB_SIZE, (num_samples, 1), device=device)
        for _ in range(1, gen_len):
            with torch.amp.autocast('cuda', enabled=(device.type == 'cuda')):
                logts = model(tokens)[:, -1, :] * config.get('gain', 1.0) / config.get('temperature', 1.0)
            probs = F.softmax(logts, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
            tokens = torch.cat((tokens, next_token), dim=1)
            
        samples = tokens.cpu().numpy().tolist()
        joint = np.zeros((VOCAB_SIZE, VOCAB_SIZE), dtype=np.float64)
        for seq in samples:
            for i in range(len(seq)-1):
                joint[seq[i], seq[i+1]] += 1
                
        div = len(set(tuple(s) for s in samples)) / len(samples)
        mi_unbiased = 0.0
        if joint.sum() > 0:
            p_xy = joint[joint > 0] / joint.sum()
            cx, cy = joint.sum(axis=1), joint.sum(axis=0)
            rows, cols = np.nonzero(joint > 0)
            px = np.array([cx[r] / joint.sum() for r in rows])
            py = np.array([cy[c] / joint.sum() for c in cols])
            mi_naive = np.sum(p_xy * np.log(p_xy / (px * py + 1e-12)))
            bias = ((np.sum(cx>0)-1)*(np.sum(cy>0)-1)) / (2.0 * joint.sum())
            mi_unbiased = max(0.0, mi_naive - bias)

    if device.type == 'cuda':
        torch.cuda.empty_cache()
        
    return val_loss, div, mi_unbiased, train_loss_avg, gn_min, gn_max, gn_mean, weight_norm, vram_mb, step_time_ms, {k: v.cpu().clone() for k, v in model.state_dict().items()}

def run_training_cluster(config, train_t, val_t, seeds, steps, batch_size=None, device=DEVICE):
    results = []
    best_state, best_loss = None, float('inf')
    
    for s in range(seeds):
        res = _train_worker(s, config, train_t, val_t, steps, batch_size=batch_size, device=device)
        if res[0] is not None:
            results.append(res)
            if res[0] < best_loss:
                best_loss = res[0]
                best_state = res[10]
                
    success_count = len(results)
    
    if success_count == 0:
        return 0, None, None, None, None, None, None, None, None, None, None, None, None
        
    avg_vl = float(np.mean([r[0] for r in results]))
    avg_div = float(np.mean([r[1] for r in results]))
    avg_mi = float(np.mean([r[2] for r in results]))
    avg_train = float(np.mean([r[3] for r in results]))
    avg_gn_min = float(np.mean([r[4] for r in results]))
    avg_gn_max = float(np.mean([r[5] for r in results]))
    avg_gn_mean = float(np.mean([r[6] for r in results]))
    avg_wnorm = float(np.mean([r[7] for r in results]))
    avg_vram = float(np.mean([r[8] for r in results]))
    avg_step_t = float(np.mean([r[9] for r in results]))
    
    gap = avg_train - avg_vl
    score = -avg_vl - 0.5*gap + 1.0*avg_mi + 0.8*avg_div
    
    return success_count, score, avg_vl, avg_div, avg_mi, avg_train, avg_gn_min, avg_gn_max, avg_gn_mean, avg_wnorm, avg_vram, avg_step_t, best_state