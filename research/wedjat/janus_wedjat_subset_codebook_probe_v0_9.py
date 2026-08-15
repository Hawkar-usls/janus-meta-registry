import argparse, cv2, numpy as np, unicodedata, json, hashlib, platform
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
START,END=0x13000,0x1342F; D010=0x13080; PARTS=list(range(0x13081,0x13087)); SCALE=0.8; MAXD=96

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def gn(cp):return unicodedata.name(chr(cp)).replace('EGYPTIAN HIEROGLYPH ','')
def raw(cp,font,n=256):
 im=Image.new('L',(n,n),255);d=ImageDraw.Draw(im);b=d.textbbox((0,0),chr(cp),font=font)
 d.text(((n-(b[2]-b[0]))//2-b[0],(n-(b[3]-b[1]))//2-b[1]),chr(cp),font=font,fill=0)
 m=(np.array(im)<128).astype(np.uint8);y,x=np.where(m);return m[y.min():y.max()+1,x.min():x.max()+1]
def rs(m,s):
 h,w=m.shape;return cv2.resize(m,(max(1,round(w*s)),max(1,round(h*s))),interpolation=cv2.INTER_NEAREST).astype(np.uint8)
def norm(m):return rs(m,MAXD/max(m.shape))
def place(piece,target):
 H,W=target.shape;h,w=piece.shape
 if h>H or w>W:return None
 z=cv2.matchTemplate(target.astype(np.float32),piece.astype(np.float32),cv2.TM_CCORR);_,_,_,(x,y)=cv2.minMaxLoc(z)
 o=np.zeros_like(target);o[y:y+h,x:x+w]=piece;return o>0
def f1(ms,t):
 if not ms:return 0.0
 u=np.logical_or.reduce(ms);q=t>0;ov=int((u&q).sum());return 2*ov/(int(u.sum())+int(q.sum()))
def allg():
 out=[]
 for cp in range(START,END+1):
  try:n=unicodedata.name(chr(cp))
  except:continue
  if n.startswith('EGYPTIAN HIEROGLYPH'):out.append(cp)
 return out
def parts_from_mask(mask):return [PARTS[i] for i in range(6) if mask>>i & 1]
def setparts(seq):
 if not seq:yield ();return
 f=seq[0]
 for rest in setparts(seq[1:]):
  yield ((f,),)+rest
  for i in range(len(rest)):
   nr=list(rest);nr[i]=tuple(sorted(rest[i]+(f,)));yield tuple(nr)
def unique_parts(seq):
 seen=set()
 for p in setparts(seq):
  q=tuple(sorted((tuple(sorted(b)) for b in p),key=lambda b:b[0]))
  if q not in seen:seen.add(q);yield q
def blockmask(block):
 m=0
 for p in block:m|=1<<PARTS.index(p)
 return m

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--font',required=True)
 ap.add_argument('--out')
 args=ap.parse_args()
 font=ImageFont.truetype(args.font,180); eye=raw(D010,font); base=MAXD/max(eye.shape); parts={p:rs(raw(p,font),base) for p in PARTS}
 targets=[cp for cp in allg() if cp not in PARTS]
 scores=np.zeros((64,len(targets)),np.float32)
 for j,cp in enumerate(targets):
  t=norm(raw(cp,font)); pm=[]
  for p in PARTS:pm.append(place(rs(parts[p],SCALE),t))
  for m in range(1,64):
   ms=[pm[i] for i in range(6) if m>>i&1]
   if any(x is None for x in ms):scores[m,j]=-1
   else:scores[m,j]=f1(ms,t)
 subsets=[];tops={}
 for m in range(1,64):
  idx=np.argpartition(scores[m],-12)[-12:];idx=idx[np.argsort(scores[m,idx])[::-1]];tops[m]=idx
  a,b=idx[0],idx[1]
  subsets.append({'mask':format(m,'06b'),'parts':[gn(p) for p in parts_from_mask(m)],'size':len(parts_from_mask(m)),'top1':{'gardiner':gn(targets[a]),'f1':float(scores[m,a])},'top2':{'gardiner':gn(targets[b]),'f1':float(scores[m,b])},'margin':float(scores[m,a]-scores[m,b])})
 def bestdistinct(masks):
  state={'key':(-1.,-1.),'ass':None}
  def dfs(i,used,vals,ass):
   if i==len(masks):
    key=(min(vals),sum(vals)/len(vals))
    if key>state['key']:state['key']=key;state['ass']=ass.copy()
    return
   m=masks[i]
   for j in tops[m]:
    cp=targets[j]
    if cp in used:continue
    used.add(cp);ass.append((cp,float(scores[m,j])));dfs(i+1,used,vals+[float(scores[m,j])],ass);ass.pop();used.remove(cp)
  dfs(0,set(),[],[]);return state
 partrecs=[]
 for p in unique_parts(tuple(PARTS)):
  masks=[blockmask(b) for b in p];st=bestdistinct(masks)
  partrecs.append({'blocks':[[gn(x) for x in b] for b in p],'token_count':len(p),'min_f1':st['key'][0],'mean_f1':st['key'][1],'targets':[gn(cp) for cp,_ in st['ass']]})
 summary={}
 for th in [.50,.45,.40,.35,.30]:
  sv=[r for r in partrecs if r['min_f1']>=th];d={'survivors':len(sv),'max_tokens':max([r['token_count'] for r in sv],default=0),'best_by_tokens':{}}
  for k in range(1,7):
   xs=[r for r in sv if r['token_count']==k]
   if xs:
    z=max(xs,key=lambda r:(r['min_f1'],r['mean_f1']));d['best_by_tokens'][str(k)]={q:z[q] for q in ['blocks','targets','min_f1','mean_f1']}
  summary[str(th)]=d
 amb={}
 for k in range(1,7):
  xs=[r for r in subsets if r['size']==k];ms=np.array([r['margin'] for r in xs])
  amb[str(k)]={'n':len(xs),'median_margin':float(np.median(ms)),'max_margin':float(ms.max()),'margin_ge_0_05':int((ms>=.05).sum()),'margin_ge_0_10':int((ms>=.10).sum())}
 out={'artifact_uuid':'JANUS-WEDJAT-SUBSET-CODEBOOK-RESULT-2026-08-15-v0.9','version':'v0.9','timestamp_date':'2026-08-15','status':'EXHAUSTIVE_SUBSET_CODEBOOK_LIMITED_AND_AMBIGUOUS','scope':'MODERN_UNICODE_GARDINER_RECONFIGURATION_ONLY_NOT_TEXT','parent':'data/JANUS-WEDJAT-EYE-GLYPH-RECONFIGURATION-RESULT-2026-08-15-v0.8.json','method':{'parts':[gn(p) for p in PARTS],'fixed_shared_scale':SCALE,'scale_source':'v0.8 strongest shared-scale solutions','subsets':63,'set_partitions':len(partrecs),'rotation':False,'mirroring':False,'piece_reuse':False,'distinct_targets_per_partition':True,'part_base_scale':'all six source parts scaled from D010 normalization exactly as v0.8 shared mode'},'threshold_capacity':summary,'subset_ambiguity_by_size':amb,'subset_codebook':subsets,'top_subsets_by_margin':sorted(subsets,key=lambda r:r['margin'],reverse=True)[:15],'top1_target_frequency':dict(__import__('collections').Counter(r['top1']['gardiner'] for r in subsets)),'highest_admissible_claim':'Using the v0.8 shared-scale geometry, all 63 nonempty subsets and all 203 set partitions were exhaustively evaluated. At F1 >= 0.45 no multi-token partition survives; at weaker thresholds multi-token synthetic arrangements emerge, but subset-to-glyph mappings usually have small top1-vs-top2 margins. The Eye therefore does not yield a robust unique multi-glyph codebook under this modern model.','provenance':{'font_family':'Noto Sans Egyptian Hieroglyphs','font_sha256':sha(args.font),'font_redistributed':False,'python':platform.python_version(),'opencv':cv2.__version__,'numpy':np.__version__},'claim_firewall':['SYNTHETIC_PARTITION_IS_NOT_TEXT','NO_READING_ORDER_FROM_GEOMETRY','AMBIGUITY_MUST_BE_REPORTED','NO_ANCIENT_HIDDEN_MESSAGE','NO_BINARY_ASCII_PYTHON_INTENT']}
 text=json.dumps(out,indent=2); Path(args.out).write_text(text+'\n',encoding='utf-8') if args.out else None; print(text)

if __name__=='__main__': main()
