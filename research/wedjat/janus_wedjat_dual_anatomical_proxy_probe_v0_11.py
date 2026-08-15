import cv2, numpy as np, unicodedata, json, hashlib, statistics, platform, math
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

START, END = 0x13000, 0x1342F
CAN=128; MAXD=100
FONT='/usr/share/fonts/truetype/noto/NotoSansEgyptianHieroglyphs-Regular.ttf'
IMAGES={}
COMPONENTS=['EYEBROW_UPPER_EYE','HUMAN_EYE_CONTOUR','PUPIL','VERTICAL_FALCON_MARK','DIAGONAL_FALCON_MARK','SPIRAL_CURL']
EYE_FAMILY=[f'D00{i}' for i in range(4,9)] + ['D008A','D009','D010']
TARGET_PARTS=['D011','D012','D013','D014','D015','D016']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def seg(path):
    im=cv2.imread(path); lab=cv2.cvtColor(im,cv2.COLOR_BGR2LAB).astype(float); h,w=im.shape[:2]; b=max(5,int(min(h,w)*.06))
    bor=np.concatenate([lab[:b].reshape(-1,3),lab[-b:].reshape(-1,3),lab[:,:b].reshape(-1,3),lab[:,-b:].reshape(-1,3)])
    bg=np.median(bor,0); dist=np.linalg.norm(lab-bg,axis=2); d=np.uint8(np.clip(dist/(dist.max() or 1)*255,0,255))
    _,m=cv2.threshold(d,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8),iterations=2)
    n,l,s,_=cv2.connectedComponentsWithStats(m)
    k=1+np.argmax(s[1:,cv2.CC_STAT_AREA]); x,y,ww,hh,_=s[k]
    return im[y:y+hh,x:x+ww], (l[y:y+hh,x:x+ww]==k).astype(np.uint8)

def base_edges(crop,mask):
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY); g=cv2.GaussianBlur(gray,(3,3),0); e=cv2.Canny(g,35,105)
    dil=cv2.dilate(mask,np.ones((5,5),np.uint8)); e=((e>0)&(dil>0)).astype(np.uint8)
    contour=cv2.morphologyEx(mask,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))
    return np.logical_or(e,contour).astype(np.uint8)

def poly_mask(h,w,pts):
    m=np.zeros((h,w),np.uint8); arr=np.array([(round(x*w),round(y*h)) for x,y in pts],np.int32); cv2.fillPoly(m,[arr],1); return m

def ellipse_mask(h,w,cx,cy,rx,ry):
    m=np.zeros((h,w),np.uint8); cv2.ellipse(m,(round(cx*w),round(cy*h)),(max(1,round(rx*w)),max(1,round(ry*h))),0,0,360,1,-1); return m

def annulus_mask(h,w,cx,cy,rx,ry,th=.28):
    outer=ellipse_mask(h,w,cx,cy,rx,ry); inner=ellipse_mask(h,w,cx,cy,rx*(1-th),ry*(1-th)); return (outer & (1-inner)).astype(np.uint8)

def annotate_A(crop,mask):
    h,w=mask.shape; e=base_edges(crop,mask); out={}
    zones={
      'EYEBROW_UPPER_EYE': poly_mask(h,w,[(.06,.04),(.95,.03),(.99,.30),(.65,.38),(.20,.31),(.04,.22)]),
      'HUMAN_EYE_CONTOUR': annulus_mask(h,w,.68,.35,.30,.17,.35),
      'PUPIL': annulus_mask(h,w,.68,.36,.095,.10,.45),
      'VERTICAL_FALCON_MARK': poly_mask(h,w,[(.56,.43),(.80,.43),(.80,.98),(.54,.98)]),
      'DIAGONAL_FALCON_MARK': poly_mask(h,w,[(.08,.40),(.58,.40),(.66,.68),(.35,.86),(.03,.80)]),
      'SPIRAL_CURL': annulus_mask(h,w,.18,.78,.15,.16,.45),
    }
    for k,z in zones.items(): out[k]=(e & z & mask).astype(np.uint8)
    return out

def line_mask_from_hough(e,zone,kind):
    z=(e & zone).astype(np.uint8)*255
    lines=cv2.HoughLinesP(z,1,np.pi/180,threshold=max(10,int(min(z.shape)*.04)),minLineLength=max(8,int(min(z.shape)*.08)),maxLineGap=max(3,int(min(z.shape)*.03)))
    out=np.zeros_like(z,dtype=np.uint8)
    if lines is None: return out
    cand=[]
    for L in lines[:,0,:]:
        x1,y1,x2,y2=map(int,L); ang=abs(math.degrees(math.atan2(y2-y1,x2-x1))); ang=180-ang if ang>90 else ang; ln=math.hypot(x2-x1,y2-y1)
        ok=(kind=='vertical' and 65<=ang<=90) or (kind=='diagonal' and 18<=ang<=65) or (kind=='horizontal' and 0<=ang<=25)
        if ok: cand.append((ln,(x1,y1,x2,y2)))
    for _,(x1,y1,x2,y2) in sorted(cand,reverse=True)[:5]: cv2.line(out,(x1,y1),(x2,y2),255,2)
    return (out>0).astype(np.uint8)

def best_circle_edge(e,zone,minr,maxr):
    z=(e & zone).astype(np.uint8)*255; blur=cv2.GaussianBlur(z,(5,5),1)
    circles=cv2.HoughCircles(blur,cv2.HOUGH_GRADIENT,dp=1,minDist=max(8,min(z.shape)//8),param1=80,param2=8,minRadius=minr,maxRadius=maxr)
    out=np.zeros_like(z,dtype=np.uint8)
    if circles is None: return out
    best=None; yy,xx=np.indices(z.shape)
    for x,y,r in circles[0]:
        x=float(x);y=float(y);r=float(r); ring=np.abs(np.sqrt((xx-x)**2+(yy-y)**2)-r)<=2.0; support=(z[ring]>0).mean() if ring.any() else 0
        if best is None or support>best[0]: best=(support,x,y,r)
    if best: _,x,y,r=best; cv2.circle(out,(round(x),round(y)),round(r),255,2)
    return (out>0).astype(np.uint8)

def annotate_B(crop,mask):
    h,w=mask.shape; e=base_edges(crop,mask)
    def R(x0,y0,x1,y1): return poly_mask(h,w,[(x0,y0),(x1,y0),(x1,y1),(x0,y1)])
    out={}; upper=R(.03,.00,.99,.38); eye=R(.35,.18,.99,.58); lowerR=R(.48,.42,.86,.99); diag=R(.02,.37,.68,.91); spiral=R(.01,.56,.40,.99)
    up_lines=line_mask_from_hough(e,upper,'horizontal'); out['EYEBROW_UPPER_EYE']=((e&upper) | cv2.dilate(up_lines,np.ones((3,3),np.uint8))).astype(np.uint8)
    out['HUMAN_EYE_CONTOUR']=(e&eye).astype(np.uint8)
    p=best_circle_edge(e,eye,max(3,int(min(h,w)*.02)),max(6,int(min(h,w)*.12)))
    if p.sum()==0: p=(e & ellipse_mask(h,w,.68,.36,.13,.14)).astype(np.uint8)
    out['PUPIL']=p
    out['VERTICAL_FALCON_MARK']=line_mask_from_hough(e,lowerR,'vertical')
    if out['VERTICAL_FALCON_MARK'].sum()<5: out['VERTICAL_FALCON_MARK']=(e&lowerR).astype(np.uint8)
    out['DIAGONAL_FALCON_MARK']=line_mask_from_hough(e,diag,'diagonal')
    if out['DIAGONAL_FALCON_MARK'].sum()<5: out['DIAGONAL_FALCON_MARK']=(e&diag).astype(np.uint8)
    s=best_circle_edge(e,spiral,max(3,int(min(h,w)*.035)),max(8,int(min(h,w)*.20)))
    if s.sum()==0: s=(e&spiral).astype(np.uint8)
    out['SPIRAL_CURL']=s
    return {k:(v & mask).astype(np.uint8) for k,v in out.items()}

def norm(m):
    y,x=np.where(m>0)
    if len(x)==0:return np.zeros((CAN,CAN),np.uint8)
    m=m[y.min():y.max()+1,x.min():x.max()+1]; h,w=m.shape; sc=MAXD/max(h,w); r=cv2.resize(m,(max(1,round(w*sc)),max(1,round(h*sc))),interpolation=cv2.INTER_NEAREST)
    o=np.zeros((CAN,CAN),np.uint8); yy=(CAN-r.shape[0])//2;xx=(CAN-r.shape[1])//2;o[yy:yy+r.shape[0],xx:xx+r.shape[1]]=r;return o

def render(cp):
    f=ImageFont.truetype(FONT,180); im=Image.new('L',(256,256),255); d=ImageDraw.Draw(im); b=d.textbbox((0,0),chr(cp),font=f)
    d.text(((256-(b[2]-b[0]))//2-b[0],(256-(b[3]-b[1]))//2-b[1]),chr(cp),font=f,fill=0)
    m=(np.array(im)<128).astype(np.uint8); e=cv2.morphologyEx(m,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8)); return norm(e)

def f1tol(a,b):
    a=a>0;b=b>0; bd=cv2.dilate(b.astype(np.uint8),np.ones((7,7),np.uint8))>0; ad=cv2.dilate(a.astype(np.uint8),np.ones((7,7),np.uint8))>0
    ra=(a&bd).sum()/max(1,a.sum()); rb=(b&ad).sum()/max(1,b.sum()); return 2*ra*rb/max(1e-9,ra+rb)

def gn(cp): return unicodedata.name(chr(cp)).replace('EGYPTIAN HIEROGLYPH ','')
def rank_component(mask,glyphs,cps):
    a=norm(mask); vals=[(f1tol(a,glyphs[cp]),cp) for cp in cps]; vals.sort(reverse=True); return vals,{cp:i+1 for i,(_,cp) in enumerate(vals)}
def iou(a,b):
    a=a>0;b=b>0; u=(a|b).sum(); return float((a&b).sum()/u) if u else 0.0

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--image',action='append',required=True,help='OID=PATH; repeat'); ap.add_argument('--out'); args=ap.parse_args()
    images={};
    for item in args.image: oid,path=item.split('=',1); images[oid]=path
    glyphs={}
    for cp in range(START,END+1):
        try:n=unicodedata.name(chr(cp))
        except:continue
        if n.startswith('EGYPTIAN HIEROGLYPH'):glyphs[cp]=render(cp)
    cps=list(glyphs); target_cp={g:next(cp for cp in cps if gn(cp)==g) for g in TARGET_PARTS}; eye_cp={g:next(cp for cp in cps if gn(cp)==g) for g in EYE_FAMILY}
    per={}; ranks={ann:{c:{cp:[] for cp in cps} for c in COMPONENTS} for ann in ['A','B']}; agreements={c:[] for c in COMPONENTS}
    for oid,p in images.items():
        crop,obj=seg(p); anns={'A':annotate_A(crop,obj),'B':annotate_B(crop,obj)}; per[oid]={}
        for c in COMPONENTS:agreements[c].append(iou(anns['A'][c],anns['B'][c]))
        for an,maps in anns.items():
            per[oid][an]={}
            for c,m in maps.items():
                vals,r=rank_component(m,glyphs,cps)
                for cp in cps:ranks[an][c][cp].append(r[cp])
                per[oid][an][c]={'edge_pixels':int(m.sum()),'top10':[{'glyph':gn(cp),'score':float(s)} for s,cp in vals[:10]],'eye_family_ranks':{g:r[cp] for g,cp in eye_cp.items()},'D011_D016_ranks':{g:r[cp] for g,cp in target_cp.items()}}
    aggregate={}
    for c in COMPONENTS:
        aggregate[c]={'annotation_iou':{'values':agreements[c],'median':float(statistics.median(agreements[c]))}}
        for an in ['A','B']:
            rows=[]
            for cp in cps:
                rs=ranks[an][c][cp]; rows.append((statistics.median(rs),sum(rs)/len(rs),cp,rs))
            rows.sort(); ar={cp:i+1 for i,(_,_,cp,_) in enumerate(rows)}
            aggregate[c][an]={'top20':[{'glyph':gn(cp),'median_rank':float(med),'mean_rank':float(mean),'object_ranks':rs} for med,mean,cp,rs in rows[:20]],'eye_family':{g:{'aggregate_rank':ar[cp],'median_object_rank':float(statistics.median(ranks[an][c][cp])),'object_ranks':ranks[an][c][cp]} for g,cp in eye_cp.items()},'D011_D016':{g:{'aggregate_rank':ar[cp],'median_object_rank':float(statistics.median(ranks[an][c][cp])),'object_ranks':ranks[an][c][cp]} for g,cp in target_cp.items()},'eye_family_hits_top25':sum(cp in eye_cp.values() for _,_,cp,_ in rows[:25]),'fraction_part_hits_top25':sum(cp in target_cp.values() for _,_,cp,_ in rows[:25])}
        topA=[x['glyph'] for x in aggregate[c]['A']['top20'][:10]]; topB=[x['glyph'] for x in aggregate[c]['B']['top20'][:10]]; aggregate[c]['top10_overlap_A_B']=sorted(set(topA)&set(topB))
    out={'artifact_uuid':'JANUS-WEDJAT-DUAL-ANATOMICAL-ANNOTATION-PILOT-2026-08-15-v0.11','version':'v0.11','status':'DUAL_ALGORITHMIC_ANATOMICAL_PROXY_PILOT_COMPLETED_HUMAN_INDEPENDENT_ANNOTATOR_GATE_OPEN','scope':'FIVE_LOCAL_MUSEUM_IMAGES_TWO_INDEPENDENT_COMPUTATIONAL_RULESETS_NOT_TWO_HUMAN_ANNOTATORS','images':{oid:{'path_basename':Path(p).name,'sha256':sha(p)} for oid,p in images.items()},'anatomical_components':COMPONENTS,'blindness':'Both annotation rule sets are frozen in code and executed before any glyph-rank inspection. They do not use glyph IDs, fraction values, or fit scores to place masks.','annotators':{'A':'geometric anatomical mask template intersected with object edge map','B':'edge/Hough-driven detector within broad anatomical search zones','independence_limit':'A and B are separate deterministic computational procedures authored in one research workflow. They are not independent human annotators and cannot satisfy the preregistered human-annotation gate.'},'per_object':per,'aggregate':aggregate,'source_grounding':{'MET_547767':'Met explicitly describes human eye, horizontal cosmetic line, vertical falcon marking, and diagonal line ending in spiral.','MET_551474':'Met explicitly states New Kingdom spiral directly under cosmetic line and later examples lower.','MET_555588':'Met identifies Wedjat as combination of human and falcon eye.'},'claim_firewall':['TWO_ALGORITHMS_ARE_NOT_TWO_INDEPENDENT_HUMAN_ANNOTATORS','PROXY_MASKS_ARE_NOT_ANATOMICAL_GROUND_TRUTH','MODERN_GLYPH_SIMILARITY_IS_NOT_ANCIENT_TEXT','NO_READING_ORDER','NO_FRACTION_OR_BINARY_PROMOTION_FROM_THIS_PILOT'],'provenance':{'font_family':'Noto Sans Egyptian Hieroglyphs','font_sha256':sha(FONT),'python':platform.python_version(),'opencv':cv2.__version__,'numpy':np.__version__}}
    text=json.dumps(out,ensure_ascii=False,indent=2)
    if args.out:Path(args.out).write_text(text+'\n',encoding='utf-8')
    print(text)
if __name__=='__main__':main()
