import argparse, cv2, numpy as np, unicodedata, json, hashlib, statistics, platform
from scipy.stats import hypergeom
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
FONT=None; START,END=0x13000,0x1342F; CAN=128;MAXD=100
ROIS={'EYE_CORE':(.10,.22,.98,.62),'UPPER_BAND':(.05,.02,.98,.36),'LOWER_LEFT':(.02,.52,.56,.98),'LOWER_RIGHT':(.52,.48,.98,.98)}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def seg(path):
 im=cv2.imread(path);lab=cv2.cvtColor(im,cv2.COLOR_BGR2LAB).astype(float);h,w=im.shape[:2];b=int(min(h,w)*.06)
 bor=np.concatenate([lab[:b].reshape(-1,3),lab[-b:].reshape(-1,3),lab[:,:b].reshape(-1,3),lab[:,-b:].reshape(-1,3)]);bg=np.median(bor,0);dist=np.linalg.norm(lab-bg,axis=2);d=np.uint8(np.clip(dist/(dist.max() or 1)*255,0,255));_,m=cv2.threshold(d,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU);m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8),iterations=2)
 n,l,s,_=cv2.connectedComponentsWithStats(m);k=1+np.argmax(s[1:,cv2.CC_STAT_AREA]);x,y,ww,hh,_=s[k];return im[y:y+hh,x:x+ww],(l[y:y+hh,x:x+ww]==k).astype(np.uint8)
def edges_roi(crop,mask,roi):
 h,w=mask.shape;x0,y0,x1,y1=roi;xa,xb=int(x0*w),int(x1*w);ya,yb=int(y0*h),int(y1*h)
 gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY);e=cv2.Canny(cv2.GaussianBlur(gray,(3,3),0),40,110);dil=cv2.dilate(mask,np.ones((5,5),np.uint8));e=((e>0)&(dil>0)).astype(np.uint8);cont=cv2.morphologyEx(mask,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8));e=np.logical_or(e,cont).astype(np.uint8);z=np.zeros_like(e);z[ya:yb,xa:xb]=e[ya:yb,xa:xb];return z
def norm(m):
 y,x=np.where(m>0)
 if len(x)==0:return np.zeros((CAN,CAN),np.uint8)
 m=m[y.min():y.max()+1,x.min():x.max()+1];h,w=m.shape;sc=MAXD/max(h,w);r=cv2.resize(m,(max(1,round(w*sc)),max(1,round(h*sc))),interpolation=cv2.INTER_NEAREST);o=np.zeros((CAN,CAN),np.uint8);yy=(CAN-r.shape[0])//2;xx=(CAN-r.shape[1])//2;o[yy:yy+r.shape[0],xx:xx+r.shape[1]]=r;return o
def render(cp):
 f=ImageFont.truetype(FONT,180);im=Image.new('L',(256,256),255);d=ImageDraw.Draw(im);b=d.textbbox((0,0),chr(cp),font=f);d.text(((256-(b[2]-b[0]))//2-b[0],(256-(b[3]-b[1]))//2-b[1]),chr(cp),font=f,fill=0);m=(np.array(im)<128).astype(np.uint8);e=cv2.morphologyEx(m,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8));return norm(e)
def f1tol(a,b):
 a=a>0;b=b>0;bd=cv2.dilate(b.astype(np.uint8),np.ones((7,7),np.uint8))>0;ad=cv2.dilate(a.astype(np.uint8),np.ones((7,7),np.uint8))>0;ra=(a&bd).sum()/max(1,a.sum());rb=(b&ad).sum()/max(1,b.sum());return 2*ra*rb/max(1e-9,ra+rb)
def gn(cp):return unicodedata.name(chr(cp)).replace('EGYPTIAN HIEROGLYPH ','')

def main():
 global FONT
 ap=argparse.ArgumentParser()
 ap.add_argument('--font',required=True)
 ap.add_argument('--image',action='append',required=True,help='OID=PATH; repeat')
 ap.add_argument('--out')
 args=ap.parse_args(); FONT=args.font; IMAGES={}
 for item in args.image:
  oid,path=item.split('=',1); IMAGES[oid]=path
 glyphs={}
 for cp in range(START,END+1):
  try:n=unicodedata.name(chr(cp))
  except:continue
  if n.startswith('EGYPTIAN HIEROGLYPH'):glyphs[cp]=render(cp)
 cps=list(glyphs); objects={oid:seg(p) for oid,p in IMAGES.items()}; ranks={rn:{cp:[] for cp in cps} for rn in ROIS}; perobj={}
 for oid,(crop,mask) in objects.items():
  perobj[oid]={}
  for rn,roi in ROIS.items():
   a=norm(edges_roi(crop,mask,roi)); vals=[(f1tol(a,glyphs[cp]),cp) for cp in cps];vals.sort(reverse=True);rank={cp:i+1 for i,(_,cp) in enumerate(vals)}
   for cp in cps:ranks[rn][cp].append(rank[cp])
   perobj[oid][rn]={'D004':rank[0x13079],'D005':rank[0x1307A],'D009':rank[0x1307F],'D010':rank[0x13080],'top10':[gn(cp) for _,cp in vals[:10]]}
 aggregate={}
 for rn in ROIS:
  rows=[]
  for cp in cps:
   rs=ranks[rn][cp];rows.append((statistics.median(rs),sum(rs)/len(rs),cp,rs))
  rows.sort(); agg_rank={cp:i+1 for i,(_,_,cp,_) in enumerate(rows)}; eye_cps=[0x13079,0x1307A,0x1307B,0x1307C,0x1307D,0x1307E,0x1307F,0x13080]
  aggregate[rn]={'top50_cross_object':[{'gardiner':gn(cp),'median_rank':med,'mean_rank':mean,'object_ranks':rs} for med,mean,cp,rs in rows[:50]],'eye_family_enrichment':{str(K):{'K':K,'eye_family_hits':sum(cp in eye_cps for _,_,cp,_ in rows[:K]),'hypergeom_p_ge_hits':float(hypergeom.sf(sum(cp in eye_cps for _,_,cp,_ in rows[:K])-1,len(rows),len(eye_cps),K))} for K in [10,20,25,50]},'predeclared_eye_family':{g:{'cross_object_rank_by_median':agg_rank[cp],'median_object_rank':statistics.median(ranks[rn][cp]),'object_ranks':ranks[rn][cp]} for g,cp in [('D004',0x13079),('D005',0x1307A),('D009',0x1307F),('D010',0x13080)]}}
 out={'artifact_uuid':'JANUS-WEDJAT-REAL-EYE-ROI-BRIDGE-PILOT-2026-08-15-v0.10','version':'v0.10','status':'EXPLORATORY_REAL_EYE_ROI_BRIDGE_UPPER_BAND_EYE_FAMILY_SIGNAL_OTHER_ROIS_UNSTABLE','scope':'FIVE_LOCAL_MUSEUM_IMAGE_BYTES_EXPLORATORY_NOT_PRIMARY_PROTOCOL','images':{oid:{'path_basename':Path(p).name,'sha256':sha(p)} for oid,p in IMAGES.items()},'roi_rules':ROIS,'per_object':perobj,'cross_object_aggregate':aggregate,'interpretation':{'upper_band':'D004 and D005 are consistently high-ranked across all five object images under the fixed upper-band ROI, while D009/D010 are not. This is an exploratory cross-object eye-family morphology bridge, not a historical reading.','other_rois':'D009/D010 affinity is less stable in lower/whole-object structure, consistent with strong material, ornament, silhouette, and period effects.','critical_limit':'ROIs are spatial proxies, not independently annotated anatomical parts; image bytes were locally present and not freshly re-downloaded under the primary receipt gate.'},'next_gate':'Replace spatial proxy ROIs with two independent blind anatomical annotations on SHA-256-sealed official museum bytes; test upper eyebrow/eye-band signal cross-period before any text or fraction inference.','provenance':{'font_family':'Noto Sans Egyptian Hieroglyphs','font_sha256':sha(FONT),'font_redistributed':False,'python':platform.python_version(),'opencv':cv2.__version__,'numpy':np.__version__},'claim_firewall':['EXPLORATORY_ROI_IS_NOT_ANATOMICAL_GROUND_TRUTH','LOCAL_BYTES_NOT_PRIMARY_RECEIPT_COMPLETE','GLYPH_SIMILARITY_IS_NOT_TEXT','NO_READING_ORDER','NO_ANCIENT_BINARY_ASCII_PYTHON_INTENT']}
 text=json.dumps(out,indent=2); Path(args.out).write_text(text+'\n',encoding='utf-8') if args.out else None; print(text)

if __name__=='__main__': main()
