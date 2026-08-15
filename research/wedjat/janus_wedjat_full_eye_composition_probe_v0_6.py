#!/usr/bin/env python3
"""Modern D010 <- D011..D016 composition control. Not ancient paleography."""
import argparse, hashlib, json, platform, random, unicodedata
from pathlib import Path
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
D010=0x13080; PARTS=list(range(0x13081,0x13087)); START=0x13000; END=0x1342F
SCALES=np.linspace(.30,1.05,9); SEED=20260815

def sha(p):
 h=hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
def render(cp,font,n=256):
 im=Image.new('L',(n,n),255); d=ImageDraw.Draw(im); c=chr(cp); b=d.textbbox((0,0),c,font=font)
 d.text(((n-(b[2]-b[0]))//2-b[0],(n-(b[3]-b[1]))//2-b[1]),c,font=font,fill=0)
 m=(np.array(im)<128).astype(np.uint8); y,x=np.where(m); return m[y.min():y.max()+1,x.min():x.max()+1]
def align(c,t):
 H,W=t.shape; ta=float(t.sum()); best=None
 for s in SCALES:
  w=max(1,round(c.shape[1]*float(s))); h=max(1,round(c.shape[0]*float(s)))
  if w>W or h>H: continue
  r=cv2.resize(c,(w,h),interpolation=cv2.INTER_NEAREST).astype(np.uint8)
  z=cv2.matchTemplate(t.astype(np.float32),r.astype(np.float32),cv2.TM_CCORR); _,ov,_,(x,y)=cv2.minMaxLoc(z)
  f=2*float(ov)/(ta+float(r.sum()))
  if best is None or f>best['f1']:
   m=np.zeros_like(t); m[y:y+h,x:x+w]=r; best={'f1':f,'scale':float(s),'mask':m}
 return best
def metrics(cps,A,t):
 u=np.logical_or.reduce([A[c]['mask']>0 for c in cps]); q=t>0; ov=int((u&q).sum()); ua=int(u.sum()); ta=int(q.sum())
 return {'f1':2*ov/(ua+ta),'recall_target_coverage':ov/ta,'precision_union_inside_target':ov/ua,'overlap_pixels':ov,'union_pixels':ua,'target_pixels':ta}
def mc(pool,n,A,t):
 rng=random.Random(SEED); obs=metrics(PARTS,A,t)['f1']; ex=0; vals=[]; mx=(-1,None)
 for _ in range(n):
  s=rng.sample(pool,6); v=metrics(s,A,t)['f1']; vals.append(v); ex+=v>=obs-1e-15
  if v>mx[0]: mx=(v,s)
 a=np.array(vals)
 return {'draws':n,'seed':SEED,'exceedances_ge_target':ex,'plus_one_empirical_p':(ex+1)/(n+1),'median_f1':float(np.median(a)),'p95_f1':float(np.percentile(a,95)),'p99_f1':float(np.percentile(a,99)),'p999_f1':float(np.percentile(a,99.9)),'max_f1':mx[0],'max_set':[unicodedata.name(chr(c)).split()[-1] for c in mx[1]]}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--font',required=True); ap.add_argument('--draws',type=int,default=100000); ap.add_argument('--out'); a=ap.parse_args()
 font=ImageFont.truetype(a.font,180); t=render(D010,font); cps=[]; dc=[]
 for cp in range(START,END+1):
  try:n=unicodedata.name(chr(cp))
  except ValueError:continue
  if n.startswith('EGYPTIAN HIEROGLYPH'):
   cps.append(cp); dc += [cp] if n.startswith('EGYPTIAN HIEROGLYPH D') else []
 A={cp:align(render(cp,font),t) for cp in cps if cp!=D010}; obs=metrics(PARTS,A,t); masks={c:A[c]['mask']>0 for c in PARTS}; q=t>0; pp=[]
 for c in PARTS:
  o=np.logical_or.reduce([m for k,m in masks.items() if k!=c]); m=masks[c]; loo=metrics([k for k in PARTS if k!=c],A,t)
  pp.append({'gardiner':unicodedata.name(chr(c)).split()[-1],'single_best_f1':A[c]['f1'],'best_scale':A[c]['scale'],'unique_target_pixels_not_covered_by_other_five':int((m&q&~o).sum()),'extra_pixels_outside_target':int((m&~q).sum()),'leave_one_out_union_f1':loo['f1'],'leave_one_out_delta_vs_full':loo['f1']-obs['f1']})
 fb=[c for c in cps if c!=D010 and c not in PARTS]; dp=[c for c in dc if c!=D010 and c not in PARTS]
 out={'status':'MODERN_FULL_EYE_COMPOSITION_SIGNAL_WITH_NONEXACT_TILING','scope':'MODERN_UNICODE_GARDINER_FONT_CONTROL_ONLY','target_set_result':obs,'full_block_control':mc(fb,a.draws,A,t),'gardiner_D_class_control':mc(dp,a.draws,A,t),'per_part_diagnostics':pp,'method':{'parts':['D011','D012','D013','D014','D015','D016'],'target':'D010','scale_grid':[float(x) for x in SCALES],'rotation_allowed':False,'same_alignment_search_for_controls':True},'provenance':{'font_family':'Noto Sans Egyptian Hieroglyphs','font_sha256':sha(a.font),'font_file_redistributed':False,'unicode_glyphs':len(cps),'D_class_glyphs':len(dc),'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__},'claim_firewall':['MODERN_SIGN_FAMILY_COHERENCE_IS_NOT_ANCIENT_GENEALOGY','RECONSTRUCTION_SIGNAL_IS_NOT_DYADIC_SIZE_ENCODING','NO_ANCIENT_BINARY_ASCII_OR_PYTHON_INTENT','ANCIENT_CSM_COMPOSITION_REQUIRES_DATED_PRIMARY_SIGN_IMAGES_AND_SAME_DOCUMENT_CONTROLS']}
 s=json.dumps(out,indent=2,ensure_ascii=False); Path(a.out).write_text(s+'\n') if a.out else None; print(s)
if __name__=='__main__':main()
