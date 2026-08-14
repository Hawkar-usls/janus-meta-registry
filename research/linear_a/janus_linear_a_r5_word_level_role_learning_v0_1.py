#!/usr/bin/env python3
"""JANUS Linear A R5-0 word-level self-supervised role learning.

Exact source pieces are mechanically grouped by source word_index. Lexical word
identities are SHA-256 opaque during learning/scoring. Numeric-only words are
retained only as typed magnitude contexts. No translation or semantic labels
are used as supervision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import janus_linear_a_full_corpus as base
import janus_linear_a_token_typing_policy_v0_6_2 as typing_policy

FROZEN_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
FOLD_NAMESPACE = "JANUS-LINA-R5-0-CV-v0.1"
DIRECTIONS = ((-2, "L2"), (-1, "L1"), (1, "R1"), (2, "R2"))
MODELS = ("B0_WORD_UNIGRAM", "B1_DIRECTIONAL_WORD_CONTEXT_COUNT", "M1_WORD_PPMI_SVD")


def opaque_word(pieces: list[str]) -> str:
    raw = "\x1f".join(pieces)
    return hashlib.sha256(("R5WORD|" + raw).encode("utf-8")).hexdigest()[:20]


def fold_of(doc_id: str) -> int:
    return int(hashlib.sha256(f"{FOLD_NAMESPACE}|{doc_id}".encode("utf-8")).hexdigest()[:8], 16) % 5


def exact_numeric_value(piece: str):
    return typing_policy.parse_exact_numeric_literal(piece)


def numeric_word_bucket(pieces: list[str]) -> str | None:
    if not pieces:
        return None
    vals = []
    for p in pieces:
        v = exact_numeric_value(p)
        if v is None:
            if typing_policy.is_numeric_like_literal(p):
                return "N:UNCERTAIN" if all(typing_policy.is_numeric_like_literal(x) for x in pieces) else None
            return None
        vals.append(float(v))
    if not vals:
        return None
    return "N:" + base.bucket(sum(vals))


def parse_document(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = base.READING_SPEC_RE.search(text)
    if not m:
        return None
    body = base.TAG_RE.sub("", m.group(1))
    words = {}
    order = []
    for serial, raw_line in enumerate(body.splitlines()):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        rm = base.ROW_RE.match(raw_line)
        if not rm:
            continue
        row_i, line_i, word_i, raw_piece, status = rm.groups()
        piece = raw_piece.strip()
        wi = int(word_i)
        if wi not in words:
            words[wi] = {"pieces": [], "statuses": [], "first_serial": serial, "rows": set(), "lines": set()}
            order.append(wi)
        w = words[wi]
        w["pieces"].append(piece)
        w["statuses"].append(status.lower())
        w["rows"].add(int(row_i)); w["lines"].add(int(line_i))
    seq = []
    reveal = {}
    for wi in sorted(order, key=lambda k: words[k]["first_serial"]):
        w = words[wi]
        pieces = w["pieces"]
        nb = numeric_word_bucket(pieces)
        all_certain = bool(pieces) and all(s == "certain" for s in w["statuses"])
        if nb is not None:
            seq.append({"kind": "N", "context": nb, "certain": all_certain, "word_index": wi})
        else:
            oid = opaque_word(pieces)
            label = "-".join(pieces)
            if oid in reveal and reveal[oid] != label:
                raise RuntimeError("OPAQUE_WORD_HASH_COLLISION")
            reveal[oid] = label
            seq.append({"kind": "W", "context": oid, "word": oid, "certain": all_certain, "word_index": wi})
    if not seq:
        return None
    return {"doc": path.stem, "fold": fold_of(path.stem), "sequence": seq, "reveal": reveal}


def load_corpus(root: Path):
    docs, reveal, failures = [], {}, 0
    for p in sorted((root / "items").glob("*.html")):
        try:
            d = parse_document(p)
        except Exception:
            d = None
        if d is None:
            failures += 1
            continue
        docs.append(d)
        for k, v in d["reveal"].items():
            if k in reveal and reveal[k] != v:
                raise RuntimeError("GLOBAL_OPAQUE_WORD_HASH_COLLISION")
            reveal[k] = v
    if len(docs) < 300:
        raise SystemExit("R5_FULL_CORPUS_GATE_FAIL")
    return docs, reveal, failures


def iter_word_positions(docs, certain_only=False):
    for d in docs:
        seq = d["sequence"]
        for i, item in enumerate(seq):
            if item["kind"] != "W":
                continue
            if certain_only and not item["certain"]:
                continue
            yield d, seq, i, item


def context_features(seq, i):
    out = []
    for delta, label in DIRECTIONS:
        j = i + delta
        if j < 0:
            ctx = "BOS"
        elif j >= len(seq):
            ctx = "EOS"
        else:
            ctx = seq[j]["context"]
        out.append(f"{label}|{ctx}")
    return out


def build_model(train_docs, min_freq=4, rank=32):
    freq = Counter(item["word"] for _, _, _, item in iter_word_positions(train_docs, certain_only=False))
    docsets = defaultdict(set)
    for d, _, _, item in iter_word_positions(train_docs, certain_only=False):
        docsets[item["word"]].add(d["doc"])
    vocab = sorted(w for w, n in freq.items() if n >= min_freq)
    vidx = {w:i for i,w in enumerate(vocab)}
    pair_counts, feature_counts, target_ctx_totals = Counter(), Counter(), Counter()
    for _, seq, i, item in iter_word_positions(train_docs, certain_only=False):
        w = item["word"]
        if w not in vidx:
            continue
        for c in context_features(seq, i):
            pair_counts[(w,c)] += 1; feature_counts[c] += 1; target_ctx_totals[w] += 1
    features = sorted(feature_counts); cidx={c:i for i,c in enumerate(features)}
    counts=np.zeros((len(vocab),len(features)),dtype=np.float64)
    for (w,c),n in pair_counts.items(): counts[vidx[w],cidx[c]]=float(n)
    total=float(counts.sum()); ppmi=np.zeros_like(counts)
    rs=counts.sum(axis=1); cs=counts.sum(axis=0); ii,jj=np.nonzero(counts)
    if total>0 and len(ii):
        vals=np.log((counts[ii,jj]*total)/(rs[ii]*cs[jj])); ppmi[ii,jj]=np.maximum(vals,0.0)
    if min(ppmi.shape,default=0)>=2 and np.any(ppmi):
        u,s,vt=np.linalg.svd(ppmi,full_matrices=False); k=max(1,min(rank,len(s))); latent=u[:,:k]*s[:k]; recon=latent@vt[:k,:]
    else:
        k=0; latent=np.zeros((len(vocab),1)); recon=np.zeros_like(ppmi)
    return {"freq":freq,"docsets":docsets,"vocab":vocab,"vidx":vidx,"features":features,"cidx":cidx,"counts":counts,"target_ctx_totals":target_ctx_totals,"latent":latent,"recon":recon,"rank":k,"train_total":sum(freq[w] for w in vocab)}


def ordered(scores,vocab): return sorted(range(len(vocab)),key=lambda i:(-float(scores[i]),vocab[i]))


def evaluate(test_docs, model):
    vocab=model["vocab"]; vidx=model["vidx"]; cidx=model["cidx"]; V=len(vocab)
    unigram=sorted(range(V),key=lambda i:(-model["freq"][vocab[i]],vocab[i])); urank={x:i+1 for i,x in enumerate(unigram)}
    alpha=1.0; N=max(1,model["train_total"]); C=max(1,len(model["features"]))
    prior=np.array([math.log((model["freq"][w]+alpha)/(N+alpha*V)) for w in vocab])
    den=np.array([model["target_ctx_totals"].get(w,0)+alpha*C for w in vocab])
    stats={m:{"n":0,"top1":0,"top5":0,"rr":0.0} for m in MODELS}; total=0;oov=0;noctx=0
    for _,seq,i,item in iter_word_positions(test_docs,certain_only=True):
        total+=1; w=item["word"]
        if w not in vidx: oov+=1; continue
        fi=[cidx[c] for c in context_features(seq,i) if c in cidx]
        if not fi: noctx+=1; continue
        truth=vidx[w]; ranks={"B0_WORD_UNIGRAM":urank[truth]}
        sc=prior.copy()
        for cj in fi: sc += np.log((model["counts"][:,cj]+alpha)/den)
        ranks["B1_DIRECTIONAL_WORD_CONTEXT_COUNT"]=ordered(sc,vocab).index(truth)+1
        sv=model["recon"][:,fi].mean(axis=1); ranks["M1_WORD_PPMI_SVD"]=ordered(sv,vocab).index(truth)+1
        for name,r in ranks.items():
            s=stats[name];s["n"]+=1;s["top1"]+=int(r==1);s["top5"]+=int(r<=5);s["rr"]+=1/r
    metrics={}
    for name,s in stats.items():
        n=s["n"];metrics[name]={"evaluable_masks":n,"top1_accuracy":s["top1"]/n if n else None,"top5_accuracy":s["top5"]/n if n else None,"mean_reciprocal_rank":s["rr"]/n if n else None}
    return {"total_certain_lexical_test_words":total,"oov":oov,"no_known_context":noctx,"evaluable_masks":stats["M1_WORD_PPMI_SVD"]["n"],"metrics":metrics}


def sparse_cosine(a:Counter,b:Counter):
    if not a or not b:return 0.0
    dot=sum(v*b.get(k,0) for k,v in a.items());na=math.sqrt(sum(v*v for v in a.values()));nb=math.sqrt(sum(v*v for v in b.values()));return dot/(na*nb) if na and nb else 0.0


def analogy_probe(train_docs,test_docs,model,topn=50):
    vocab=model["vocab"];latent=model["latent"];norm=np.linalg.norm(latent,axis=1)
    eligible=[i for i,w in enumerate(vocab) if model["freq"][w]>=6 and len(model["docsets"][w])>=3 and norm[i]>0]
    pairs=[]
    for x in range(len(eligible)):
        i=eligible[x]
        for y in range(x+1,len(eligible)):
            j=eligible[y];sim=float(np.dot(latent[i],latent[j])/(norm[i]*norm[j]));pairs.append((sim,vocab[i],vocab[j]))
    pairs.sort(key=lambda z:(-z[0],z[1],z[2])); selected=pairs[:topn]
    ctx=defaultdict(Counter);occ=Counter()
    for _,seq,i,item in iter_word_positions(test_docs,certain_only=True):
        w=item["word"];occ[w]+=1
        for c in context_features(seq,i):ctx[w][c]+=1
    out=[]
    for sim,a,b in selected:
        eligible_test=occ[a]>=2 and occ[b]>=2;tc=sparse_cosine(ctx[a],ctx[b]) if eligible_test else None;rep=bool(eligible_test and tc>=0.20)
        out.append({"token_a":a,"token_b":b,"train_cosine":sim,"a_test_occurrences":occ[a],"b_test_occurrences":occ[b],"test_context_cosine":tc,"test_eligible":eligible_test,"replicated":rep})
    return out


def weighted_aggregate(folds):
    out={}
    for m in MODELS:
        n=sum(f["evaluation"]["metrics"][m]["evaluable_masks"] for f in folds)
        def wa(k):return sum(f["evaluation"]["metrics"][m][k]*f["evaluation"]["metrics"][m]["evaluable_masks"] for f in folds)/n if n else None
        out[m]={"evaluable_masks":n,"top1_accuracy":wa("top1_accuracy"),"top5_accuracy":wa("top5_accuracy"),"mean_reciprocal_rank":wa("mean_reciprocal_rank")}
    return out


def role_descriptors(docs, words):
    desc={w:{"numeric_left":set(),"numeric_right":set(),"regions":set(),"documents":set()} for w in words}
    for d in docs:
        seq=d["sequence"]
        for i,item in enumerate(seq):
            if item.get("kind")!='W' or item.get("word") not in desc or not item.get("certain"):continue
            w=item["word"];q=desc[w];q["documents"].add(d["doc"]);q["regions"].add(base.region_of(d["doc"]))
            if i>0 and seq[i-1]["kind"]=='N':q["numeric_left"].add(seq[i-1]["context"])
            if i+1<len(seq) and seq[i+1]["kind"]=='N':q["numeric_right"].add(seq[i+1]["context"])
    return {w:{"numeric_left_bucket_set":sorted(q["numeric_left"]),"numeric_right_bucket_set":sorted(q["numeric_right"]),"region_set":sorted(q["regions"]),"document_count":len(q["documents"])} for w,q in desc.items()}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--corpus',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    spec=json.load(open(args.spec,encoding='utf-8'));assert spec['source']['frozen_commit']==FROZEN_COMMIT;assert spec['certainty']['none_reinterpreted_as_certain'] is False
    docs,reveal,failures=load_corpus(Path(args.corpus)); fold_counts={str(k):sum(d['fold']==k for d in docs) for k in range(5)}; fold_rows=[]; hist=defaultdict(lambda:{"selected":[],"replicated":[],"eligible":[],"train_cos":[],"test_cos":[]})
    for fold in range(5):
        train=[d for d in docs if d['fold']!=fold];test=[d for d in docs if d['fold']==fold];model=build_model(train,4,32);ev=evaluate(test,model);pairs=analogy_probe(train,test,model,50)
        for p in pairs:
            h=hist[(p['token_a'],p['token_b'])];h['selected'].append(fold);h['train_cos'].append(p['train_cosine']);
            if p['test_eligible']:h['eligible'].append(fold)
            if p['test_context_cosine'] is not None:h['test_cos'].append(p['test_context_cosine'])
            if p['replicated']:h['replicated'].append(fold)
        b0=ev['metrics']['B0_WORD_UNIGRAM'];b1=ev['metrics']['B1_DIRECTIONAL_WORD_CONTEXT_COUNT'];m1=ev['metrics']['M1_WORD_PPMI_SVD'];both=bool(b0['mean_reciprocal_rank'] is not None and b1['mean_reciprocal_rank']>b0['mean_reciprocal_rank'] and m1['mean_reciprocal_rank']>b0['mean_reciprocal_rank'])
        fold_rows.append({'fold':fold,'train_documents':len(train),'heldout_documents':len(test),'vocab_size':len(model['vocab']),'svd_rank_used':model['rank'],'evaluation':ev,'both_context_models_beat_unigram_MRR':both})
    agg=weighted_aggregate(fold_rows);b0=agg['B0_WORD_UNIGRAM'];b1=agg['B1_DIRECTIONAL_WORD_CONTEXT_COUNT'];m1=agg['M1_WORD_PPMI_SVD'];fold_robust=sum(f['both_context_models_beat_unigram_MRR'] for f in fold_rows);enough=m1['evaluable_masks']>=200;beats=bool(enough and b1['mean_reciprocal_rank']>b0['mean_reciprocal_rank'] and b1['top5_accuracy']>b0['top5_accuracy'] and m1['mean_reciprocal_rank']>b0['mean_reciprocal_rank'] and m1['top5_accuracy']>b0['top5_accuracy']);admitted=bool(enough and beats and fold_robust>=4)
    pair_rows=[]
    for (a,b),h in hist.items():
        cvrole=len(h['selected'])>=3 and len(h['replicated'])>=2
        pair_rows.append({'token_a':a,'token_b':b,'folds_selected':h['selected'],'folds_test_eligible':h['eligible'],'folds_replicated':h['replicated'],'selected_fold_count':len(h['selected']),'replicated_fold_count':len(h['replicated']),'mean_train_cosine':statistics.fmean(h['train_cos']) if h['train_cos'] else None,'mean_test_cosine':statistics.fmean(h['test_cos']) if h['test_cos'] else None,'CV_ROLE_ANALOGY':cvrole})
    pair_rows.sort(key=lambda r:(-int(r['CV_ROLE_ANALOGY']),-r['replicated_fold_count'],-r['selected_fold_count'],-(r['mean_train_cosine'] or 0),r['token_a'],r['token_b']));rep=[r for r in pair_rows if r['CV_ROLE_ANALOGY']]; words={x for r in rep for x in (r['token_a'],r['token_b'])}; descriptors=role_descriptors(docs,words)
    for r in pair_rows:r['source_word_a_after_all_scoring']=reveal.get(r['token_a']);r['source_word_b_after_all_scoring']=reveal.get(r['token_b'])
    for r in rep:r['word_a_role_descriptor']=descriptors.get(r['token_a']);r['word_b_role_descriptor']=descriptors.get(r['token_b'])
    status='WORD_LEVEL_CROSS_VALIDATED_ROLE_STRUCTURE_SIGNAL_PRESENT' if admitted else 'WORD_LEVEL_CROSS_VALIDATED_ROLE_STRUCTURE_SIGNAL_NOT_ADMITTED'
    result={'artifact_uuid':'JANUS-LINEAR-A-R5-0-WORD-LEVEL-SELF-SUPERVISED-ROLE-LEARNING-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'word_level_cross_validated_self_supervised_role_learning_result','status':status,'source':{'repository':'Hawkar-usls/lineara.xyz','frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},'fold_counts':fold_counts,'fold_results':fold_rows,'aggregate_masked_word_prediction':agg,'admission':{'minimum_evaluable_masks':200,'actual_evaluable_masks':m1['evaluable_masks'],'enough_evidence':enough,'both_context_models_beat_unigram_aggregate_MRR_and_top5':beats,'folds_where_both_context_models_beat_unigram_MRR':fold_robust,'minimum_required_folds':4,'word_level_role_structure_admitted':admitted},'cross_fold_word_role_analogy':{'unique_train_selected_pairs':len(pair_rows),'CV_role_analogy_count':len(rep),'CV_role_analogies':rep,'all_train_selected_pairs_after_scoring':pair_rows,'semantic_equivalence_claimed':False},'leakage_firewall':{'word_labels_visible_during_training':False,'none_reinterpreted_as_certain':False,'doubtful_reinterpreted_as_certain':False,'translations_used':False,'external_language_dictionary_used':False,'Notti_readings_used':False,'Linear_B_semantic_supervision_used':False,'R3B_blind_eligibility_affected':False},'epistemic_gate':{'word_level_functional_role_structure_learned':admitted,'word_meanings_established':False,'semantic_equivalence_established':False,'grammatical_label_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'claim_ceiling':spec['claim_ceiling']}
    Path(args.out).parent.mkdir(parents=True,exist_ok=True);Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps({'status':status,'documents':len(docs),'evaluable_masks':m1['evaluable_masks'],'aggregate':agg,'fold_robustness':fold_robust,'CV_role_analogy_count':len(rep),'decipherment_established':False},ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
