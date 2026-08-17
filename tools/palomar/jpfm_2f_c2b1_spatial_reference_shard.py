#!/usr/bin/env python3
"""JPFM-2F-C2B1 shard: same-plate expanding, duplicate-safe strict reference support.

Engineering-only replay on the frozen 128-source holdout. No morphology association
inference and no external temporal/human/environment labels are permitted here.
"""
from __future__ import annotations
import argparse, concurrent.futures as cf, gzip, hashlib, io, json, math, sys
from pathlib import Path

import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata.utils import overlap_slices
from astropy.wcs import WCS
import astropy.units as u
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jpfm_2f_b2_tile_lineage_replay as b2
import jpfm_2f_b3_shape_compat_replay as b3

POSS_COMMIT="4005e200541b321ead3d6608f0162a14430ef1c2"
HOLDOUT_CSV_SHA="bc30aab00bb79d5414cd4f2c4b7490c49f3e05058270286fb1c1aeb40cf8d871"
HOLDOUT_GZ_SHA="0a6311472ce9f88baa42f7cb4c7765b8757c83792ba6526c15f9f93680d28d9a"
HOLDOUT_CANON="50c79682c53cb718067229f832587e0d5ccd5ce338b49b140a7f7d3d32187db8"
ADMISSION_CANON="27373cc8f40fe8a368d42e05c6541bc77a1c5f95eb589f1bc0ec9b8ceaafd751"
DEDUP_CANON="16a93c7b515fb55685307dd3d808561882887f58e08b21d95474d6659a4da9f2"
EXPECTED_ROWS=128
EXPECTED_TILES=110
EXPECTED_PLATES=90
SHARD_COUNT=10
GRID=7
SIZE_ARCMIN=60.0
REF_MIN=20
REF_CLASS_STAR_MIN=0.8
REF_SNR_MIN=20.0
DUP_ARCSEC=2.0
FSSPEC_BLOCK_SIZE=1024*1024
DETECTION_WORKERS=4
PRIMARY=["FWHM_IMAGE","ELONGATION","SPREAD_MODEL"]

def sha(b): return hashlib.sha256(b).hexdigest()
def canon(o): return sha(json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())
def stable_sha(xs): return sha(("\n".join(map(str,xs))+"\n").encode())

def load_holdout(path: Path):
    gz=path.read_bytes()
    if sha(gz)!=HOLDOUT_GZ_SHA: raise RuntimeError("C2B1 holdout gzip hash mismatch")
    raw=gzip.decompress(gz)
    if sha(raw)!=HOLDOUT_CSV_SHA: raise RuntimeError("C2B1 holdout csv hash mismatch")
    d=pd.read_csv(io.BytesIO(raw)); d["src_id"]=d.src_id.astype(str); d["tile_id"]=d.tile_id.astype(str); d["plate_id"]=d.plate_id.astype(str)
    if len(d)!=EXPECTED_ROWS or d.src_id.nunique()!=EXPECTED_ROWS or d.tile_id.nunique()!=EXPECTED_TILES or d.plate_id.nunique()!=EXPECTED_PLATES:
        raise RuntimeError("C2B1 holdout invariant failed")
    return d

def verify_json(path: Path, expected: str):
    d=json.loads(path.read_text()); p=dict(d); integ=p.pop("integrity",None)
    if not integ or canon(p)!=integ.get("canonical_payload_sha256_without_integrity") or integ["canonical_payload_sha256_without_integrity"]!=expected:
        raise RuntimeError(f"canonical mismatch {path.name}")
    return d

def plate_grid(hdu, upstream_root: Path, plate: str):
    sys.path.insert(0,str(upstream_root))
    from vasco.utils.tile_id import format_tile_id
    ph=hdu.header; pw=WCS(ph); ny,nx=hdu.shape
    scale=float(ph["XPIXELSZ"])/1000.0*float(ph["PLTSCALE"])
    tile_px=SIZE_ARCMIN*60.0/scale; tw=th=int(round(tile_px))
    def centres(span):
        lo,hi=tile_px/2.0, span-tile_px/2.0
        return np.linspace(lo,hi,GRID) if hi>lo else np.full(GRID,span/2.0)
    cx,cy=centres(nx),centres(ny)
    cells=[]
    for iy,py in enumerate(cy):
        for ix,px in enumerate(cx):
            ra,dec=[float(v) for v in pw.pixel_to_world_values(px,py)]
            tid=format_tile_id(ra%360.0,dec)
            sl,_=overlap_slices((ny,nx),(th,tw),(py,px),mode="trim")
            cells.append({"tile_id":tid,"ix":ix,"iy":iy,"cx":float(px),"cy":float(py),"ra":ra%360.0,"dec":dec,
                          "sl_y":sl[0],"sl_x":sl[1]})
    if len(cells)!=49 or len({x['tile_id'] for x in cells})!=49:
        raise RuntimeError(f"{plate}: invalid 7x7 grid")
    return pw,ph,cells

def get_crpix(upstream_root: Path):
    c=pd.read_csv(upstream_root/"data"/"plate_crpix_table.csv").rename(columns={"plate":"plate_id"})
    return {str(r.plate_id):r for r in c.itertuples(index=False)}

def reconstruct_cell(hdu,pw,ph,cell,crow,tiles_root:Path,plate:str):
    tid=cell["tile_id"]; sy,sx=cell["sl_y"],cell["sl_x"]
    arr=np.asarray(hdu.section[sy,sx])
    if arr.size==0: return {"plate_id":plate,"tile_id":tid,"tile_identity":"EMPTY_SECTION"}
    hdr,rmed,rmax=b2.clean_tan_header_from_full(pw,ph,sy,sx,float(crow.delta_x_px),float(crow.delta_y_px))
    tdir=tiles_root/tid; raw=tdir/"raw"; raw.mkdir(parents=True,exist_ok=True)
    name=f"dss1-red_{cell['ra']:.3f}_{cell['dec']:.3f}_{SIZE_ARCMIN:.0f}arcmin.fits"
    out=raw/name
    fits.PrimaryHDU(arr.astype(np.int16),header=hdr).writeto(out,overwrite=True)
    return {"plate_id":plate,"tile_id":tid,"tile_identity":"RECONSTRUCTED","tile_fits":str(out),
            "shape_y":int(arr.shape[0]),"shape_x":int(arr.shape[1]),"section_x_start":int(sx.start),"section_y_start":int(sy.start),
            "tan_refit_median_arcsec":rmed,"tan_refit_max_arcsec":rmax,"crpix_dx":float(crow.delta_x_px),"crpix_dy":float(crow.delta_y_px)}

def ring_cells(target, cells, ring):
    if ring==3: return {c["tile_id"] for c in cells}
    return {c["tile_id"] for c in cells if max(abs(c["ix"]-target["ix"]),abs(c["iy"]-target["iy"]))<=ring}

def strict_reference_detections(processed_meta, cells_by_tid, tiles_root: Path):
    centres=np.array([[c["cx"],c["cy"]] for c in cells_by_tid.values()],float)
    tids=list(cells_by_tid)
    rows=[]
    for tid,meta in processed_meta.items():
        p=tiles_root/tid/"catalogs"/"sextractor_pass2.csv"
        if not p.exists(): continue
        cat=pd.read_csv(p)
        req=["NUMBER","FLAGS","CLASS_STAR","SNR_WIN","FWHM_IMAGE","ELONGATION","SPREAD_MODEL","XWIN_IMAGE","YWIN_IMAGE"]
        if any(x not in cat.columns for x in req): continue
        for x in req: cat[x]=pd.to_numeric(cat[x],errors="coerce")
        finite=np.isfinite(cat[["FWHM_IMAGE","ELONGATION","SPREAD_MODEL","XWIN_IMAGE","YWIN_IMAGE"]].to_numpy(float)).all(axis=1)
        q=cat[(cat.FLAGS==0)&(cat.CLASS_STAR>=REF_CLASS_STAR_MIN)&(cat.SNR_WIN>=REF_SNR_MIN)&finite].copy()
        if q.empty: continue
        rac="ALPHAWIN_J2000" if "ALPHAWIN_J2000" in q.columns else "ALPHA_J2000"
        dec="DELTAWIN_J2000" if "DELTAWIN_J2000" in q.columns else "DELTA_J2000"
        if rac not in q.columns or dec not in q.columns: continue
        q[rac]=pd.to_numeric(q[rac],errors="coerce"); q[dec]=pd.to_numeric(q[dec],errors="coerce")
        q=q[np.isfinite(q[[rac,dec]].to_numpy(float)).all(axis=1)]
        for r in q.itertuples(index=False):
            fx=float(getattr(r,"XWIN_IMAGE"))-1.0+float(meta["section_x_start"])
            fy=float(getattr(r,"YWIN_IMAGE"))-1.0+float(meta["section_y_start"])
            dist=(centres[:,0]-fx)**2+(centres[:,1]-fy)**2
            md=float(np.min(dist)); candidates=[i for i,v in enumerate(dist) if abs(float(v)-md)<=1e-9]
            ni=min(candidates,key=lambda i:tids[i]); nat=tids[ni]; nc=cells_by_tid[nat]
            rows.append({"source_tile_id":tid,"natural_tile_id":nat,"natural_ix":int(nc["ix"]),"natural_iy":int(nc["iy"]),
                         "NUMBER":int(getattr(r,"NUMBER")),"SNR_WIN":float(getattr(r,"SNR_WIN")),"ra":float(getattr(r,rac)),"dec":float(getattr(r,dec)),
                         "FWHM_IMAGE":float(getattr(r,"FWHM_IMAGE")),"ELONGATION":float(getattr(r,"ELONGATION")),"SPREAD_MODEL":float(getattr(r,"SPREAD_MODEL")),
                         "full_x0":fx,"full_y0":fy})
    return pd.DataFrame(rows)

def dedup_reference_components(det: pd.DataFrame):
    if det.empty: return det.copy()
    reps=[]
    chord=2.0*math.sin(math.radians(DUP_ARCSEC/3600.0)/2.0)
    for nat,g in det.groupby("natural_tile_id",sort=True):
        g=g.reset_index(drop=True)
        ra=np.deg2rad(g.ra.to_numpy(float)); de=np.deg2rad(g.dec.to_numpy(float))
        xyz=np.column_stack([np.cos(de)*np.cos(ra),np.cos(de)*np.sin(ra),np.sin(de)])
        pairs=cKDTree(xyz).query_pairs(chord)
        parent=list(range(len(g)))
        def find(x):
            while parent[x]!=x:
                parent[x]=parent[parent[x]]; x=parent[x]
            return x
        def union(a,b):
            a,b=find(a),find(b)
            if a!=b: parent[max(a,b)]=min(a,b)
        for a,b in pairs: union(a,b)
        comps={}
        for i in range(len(g)): comps.setdefault(find(i),[]).append(i)
        for inds in comps.values():
            cand=g.iloc[inds].copy()
            cand["_same"]=(cand.source_tile_id.astype(str)==str(nat)).astype(int)
            cand["_snr_sort"]=-pd.to_numeric(cand.SNR_WIN,errors="coerce").fillna(-np.inf)
            cand=cand.sort_values(["_same","_snr_sort","source_tile_id","NUMBER"],ascending=[False,True,True,True],kind="stable")
            r=cand.iloc[0].to_dict(); r["component_size"]=len(inds); reps.append(r)
    return pd.DataFrame(reps)

def target_pass2_row(target, tiles_root:Path):
    p=tiles_root/str(target.tile_id)/"catalogs"/"sextractor_pass2.csv"
    if not p.exists(): return None
    cat=pd.read_csv(p); num=pd.to_numeric(cat.get("NUMBER"),errors="coerce")
    hit=cat[num==int(target.object_id)]
    if len(hit)!=1: return None
    q=hit.iloc[0]
    rac="ALPHAWIN_J2000" if "ALPHAWIN_J2000" in q.index else "ALPHA_J2000"
    dec="DELTAWIN_J2000" if "DELTAWIN_J2000" in q.index else "DELTA_J2000"
    out={"target_ra":float(q[rac]),"target_dec":float(q[dec])}
    for f in PRIMARY: out[f]=float(q[f])
    return out

def bank_for_target(bank,target_cell,target_row,ring):
    if bank.empty: return bank.copy()
    if ring==3: q=bank.copy()
    else:
        q=bank[np.maximum((bank.natural_ix-int(target_cell["ix"])).abs(),(bank.natural_iy-int(target_cell["iy"])).abs())<=ring].copy()
    if q.empty:return q
    t=SkyCoord(float(target_row["target_ra"])*u.deg,float(target_row["target_dec"])*u.deg)
    s=SkyCoord(q.ra.to_numpy(float)*u.deg,q.dec.to_numpy(float)*u.deg)
    sep=s.separation(t).arcsec
    return q[sep>DUP_ARCSEC].copy()

def normalize(target_row,bank):
    out={"reference_count":int(len(bank))}
    if len(bank)<REF_MIN:
        out["normalization_status"]="INSUFFICIENT_REFERENCE_COUNT"; return out
    ok=True
    for f in PRIMARY:
        a=pd.to_numeric(bank[f],errors="coerce").to_numpy(float); a=a[np.isfinite(a)]
        if len(a)<REF_MIN:
            ok=False; out[f"local_{f}_status"]="INSUFFICIENT_FINITE"; continue
        med=float(np.median(a)); mad=float(np.median(np.abs(a-med))); sig=1.4826*mad; x=float(target_row[f])
        out[f"local_{f}_median"]=med; out[f"local_{f}_robust_sigma"]=sig
        out[f"local_{f}_percentile"]=float((np.sum(a<x)+0.5*np.sum(a==x))/len(a))
        if not math.isfinite(sig) or sig<=0:
            ok=False; out[f"local_{f}_status"]="NONPOSITIVE_ROBUST_SIGMA"
        else:
            out[f"local_{f}_z"]=(x-med)/sig; out[f"local_{f}_status"]="PASS"
    out["local_sharpness_z"]=-out.get("local_FWHM_IMAGE_z",float("nan"))
    out["normalization_status"]="PASS" if ok else "FAIL_ROBUST_SCALE"
    return out

def process_plate(plate_sample:pd.DataFrame,upstream_root:Path,plate_root:Path,crpix_lookup):
    plate=str(plate_sample.plate_id.iloc[0]); tiles_root=plate_root/"tiles"
    url=b2.IRSA_FMT.format(plate=plate)
    if plate not in crpix_lookup or str(crpix_lookup[plate].status)!="ok":
        return pd.DataFrame(),{"plate_id":plate,"plate_status":"FAIL_CRPIX"}
    crow=crpix_lookup[plate]
    processed={}; det_status={}; target_state={}
    with fits.open(url,use_fsspec=True,lazy_load_hdus=True,fsspec_kwargs={"block_size":FSSPEC_BLOCK_SIZE,"cache_type":"readahead"}) as hdul:
        hdu=hdul[0]; pw,ph,cells=plate_grid(hdu,upstream_root,plate); bytid={c["tile_id"]:c for c in cells}
        missing=set(plate_sample.tile_id)-set(bytid)
        if missing: return pd.DataFrame(),{"plate_id":plate,"plate_status":"FAIL_TARGET_TILE_NOT_IN_GRID","missing":sorted(missing)}
        for r in plate_sample.itertuples(index=False): target_state[str(r.src_id)]={"selected_ring":None,"target_tile":str(r.tile_id)}
        for ring in range(4):
            unresolved=[r for r in plate_sample.itertuples(index=False) if target_state[str(r.src_id)]["selected_ring"] is None]
            if not unresolved: break
            needed=set()
            for r in unresolved: needed |= ring_cells(bytid[str(r.tile_id)],cells,ring)
            new=sorted(needed-set(processed))
            for tid in new:
                rec=reconstruct_cell(hdu,pw,ph,bytid[tid],crow,tiles_root,plate); processed[tid]=rec
            if new:
                with cf.ThreadPoolExecutor(max_workers=DETECTION_WORKERS) as ex:
                    futs={ex.submit(b2.run_detection_one,processed[tid],upstream_root,tiles_root):tid for tid in new}
                    for fut in cf.as_completed(futs):
                        rr=fut.result(); det_status[str(rr["tile_id"])]=str(rr["detection_status"])
            det=strict_reference_detections({k:v for k,v in processed.items() if det_status.get(k)=="PASS"},bytid,tiles_root)
            bank=dedup_reference_components(det)
            for r in unresolved:
                tr=target_pass2_row(r,tiles_root)
                if tr is None: continue
                q=bank_for_target(bank,bytid[str(r.tile_id)],tr,ring)
                target_state[str(r.src_id)][f"ring{ring}_reference_count_interim"]=int(len(q))
                if len(q)>=REF_MIN: target_state[str(r.src_id)]["selected_ring"]=ring
    # final bank after all adaptive work
    det=strict_reference_detections({k:v for k,v in processed.items() if det_status.get(k)=="PASS"},bytid,tiles_root)
    bank=dedup_reference_components(det)
    rows=[]
    for r in plate_sample.itertuples(index=False):
        rec={"src_id":str(r.src_id),"plate_id":plate,"tile_id":str(r.tile_id),"object_id":int(r.object_id),
             "structural_cluster":int(r.structural_cluster),"sample_role":str(r.sample_role),"anomaly_score":float(r.anomaly_score)}
        tr=target_pass2_row(r,tiles_root)
        if tr is None:
            rec["exact_object_status"]="TARGET_NUMBER_NOT_RECOVERED"; rows.append(rec); continue
        rec.update(tr); rec["exact_object_status"]="EXACT_NUMBER_RECOVERED"
        rec["pass2_to_s0_sep_arcsec"]=float(SkyCoord(tr["target_ra"]*u.deg,tr["target_dec"]*u.deg).separation(SkyCoord(float(r.ra)*u.deg,float(r.dec)*u.deg)).arcsec)
        final_counts={}
        selected=None
        for ring in range(4):
            q=bank_for_target(bank,bytid[str(r.tile_id)],tr,ring); final_counts[ring]=int(len(q))
            if selected is None and len(q)>=REF_MIN: selected=ring
        for ring,n in final_counts.items(): rec[f"ring{ring}_reference_count"]=n
        rec["selected_reference_ring"]=selected if selected is not None else np.nan
        if selected is None:
            rec["reference_support_status"]="INSUFFICIENT_AFTER_FULL_PLATE"; rec["reference_count"]=final_counts[3]
        else:
            q=bank_for_target(bank,bytid[str(r.tile_id)],tr,selected); norm=normalize(tr,q); rec.update(norm)
            rec["reference_support_status"]="PASS" if norm.get("normalization_status")=="PASS" else str(norm.get("normalization_status"))
        rows.append(rec)
    plate_receipt={"plate_id":plate,"plate_status":"PASS","targets":int(len(plate_sample)),"grid_cells_processed":int(len(processed)),
                   "detection_pass_cells":int(sum(v=="PASS" for v in det_status.values())),"dedup_strict_reference_components":int(len(bank)),
                   "full_grid_cells":49,"full_remote_plate_array_accessed":False}
    return pd.DataFrame(rows),plate_receipt

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--holdout",required=True,type=Path); ap.add_argument("--admission",required=True,type=Path); ap.add_argument("--dedup-addendum",required=True,type=Path)
    ap.add_argument("--upstream-root",required=True,type=Path); ap.add_argument("--work-dir",required=True,type=Path); ap.add_argument("--out-dir",required=True,type=Path)
    ap.add_argument("--shard-index",required=True,type=int); ap.add_argument("--shard-count",default=SHARD_COUNT,type=int)
    a=ap.parse_args(); a.work_dir.mkdir(parents=True,exist_ok=True); a.out_dir.mkdir(parents=True,exist_ok=True)
    if a.shard_count!=SHARD_COUNT or not 0<=a.shard_index<SHARD_COUNT: raise RuntimeError("C2B1 shard contract")
    adm=verify_json(a.admission,ADMISSION_CANON); ded=verify_json(a.dedup_addendum,DEDUP_CANON)
    if adm["reference_star_contract"]["minimum_reference_stars"]!=20 or adm["inference_boundary"]["C2B1_morphology_association_test_authorized"] is not False: raise RuntimeError("C2B1 admission drift")
    if ded["dedup_contract"]["duplicate_link_radius_arcsec"]!=2.0: raise RuntimeError("C2B1 dedup drift")
    hold=load_holdout(a.holdout)
    plates=sorted(hold.plate_id.unique()); assignment={p:i%SHARD_COUNT for i,p in enumerate(plates)}; assigned=[p for p in plates if assignment[p]==a.shard_index]
    sample=hold[hold.plate_id.isin(assigned)].copy()
    print(f"[C2B1 shard {a.shard_index}] rows={len(sample)} plates={len(assigned)} target_tiles={sample.tile_id.nunique()}",flush=True)
    crpix=get_crpix(a.upstream_root); frames=[]; plate_receipts=[]
    for i,p in enumerate(assigned,1):
        print(f"[C2B1 shard {a.shard_index}] plate {i}/{len(assigned)} {p}",flush=True)
        df,pr=process_plate(sample[sample.plate_id==p].copy(),a.upstream_root,a.work_dir/f"plate-{p}",crpix)
        frames.append(df); plate_receipts.append(pr)
    full=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    # Shape/profile is target-tile only, after adaptive detection path.
    patch=b3.patch_shape_compat(a.upstream_root)
    # Build a consolidated tiles-root by symlinking/copying target tile directories into one view.
    merged=a.work_dir/"merged-target-tiles"; merged.mkdir(exist_ok=True)
    for p in assigned:
        root=a.work_dir/f"plate-{p}"/"tiles"
        if not root.exists(): continue
        for tdir in root.iterdir():
            dst=merged/tdir.name
            if not dst.exists(): dst.symlink_to(tdir.resolve(),target_is_directory=True)
    shape,shape_exec=b2.run_upstream_shape(sample,a.upstream_root,a.work_dir/"shape",merged)
    if len(shape):
        shape["src_id"]=shape.src_id.astype(str)
        keep=[c for c in shape.columns if c in {"src_id","profile_diff","circularity","area","shape_defect","circle_deviation","shape_confidence","elongation","stars_used","shape_failed","failure_reason","reject_flag","reject_reason"}]
        full=full.merge(shape[keep],on="src_id",how="left",validate="one_to_one")
    else:
        full["shape_failed"]=1; full["failure_reason"]="SHAPE_STAGE_OUTPUT_MISSING"
    full["c2b1_shard_index"]=a.shard_index; full["c2b1_shard_count"]=SHARD_COUNT
    full=full.sort_values(["structural_cluster","sample_role","src_id"],kind="stable").reset_index(drop=True)
    raw=full.to_csv(index=False,lineterminator="\n",float_format="%.12g").encode(); csvsha=sha(raw)
    side=f"JANUS-PALOMAR-JPFM-2F-C2B1-SHARD-{a.shard_index:02d}-SIDECAR-RUN-001.csv.gz"; sp=a.out_dir/side
    with sp.open("wb") as f:
        with gzip.GzipFile(filename="",mode="wb",fileobj=f,mtime=0) as z:z.write(raw)
    gzsha=sha(sp.read_bytes())
    exact=full.exact_object_status.astype(str).eq("EXACT_NUMBER_RECOVERED") if len(full) else pd.Series(dtype=bool)
    sep=pd.to_numeric(full.get("pass2_to_s0_sep_arcsec"),errors="coerce")
    norm=full.reference_support_status.astype(str).eq("PASS") if "reference_support_status" in full else pd.Series(False,index=full.index)
    shape_failed=pd.to_numeric(full.get("shape_failed"),errors="coerce").fillna(1).astype(int) if len(full) else pd.Series(dtype=int)
    receipt={
      "artifact_id":f"JANUS-PALOMAR-JPFM-2F-C2B1-SHARD-{a.shard_index:02d}-RECEIPT-RUN-001","experiment_id":"JPFM-2F-C2B1","schema_version":"1.0",
      "date":pd.Timestamp.utcnow().date().isoformat(),"status":"EXECUTED_SHARD_RECEIPT__NO_GLOBAL_OUTCOME_OR_MORPHOLOGY_INFERENCE",
      "claim_ceiling":"C2B1_ENGINEERING_SHARD_ONLY__NO_GLOBAL_OUTCOME__NO_MORPHOLOGY_ASSOCIATION_INFERENCE__EXTERNAL_LABELS_SEALED",
      "bindings":{"admission_canonical_sha256":ADMISSION_CANON,"dedup_addendum_canonical_sha256":DEDUP_CANON,"holdout_canonical_sha256":HOLDOUT_CANON,
                  "holdout_csv_sha256":HOLDOUT_CSV_SHA,"holdout_gzip_sha256":HOLDOUT_GZ_SHA,"poss_commit":POSS_COMMIT},
      "shard":{"index":a.shard_index,"count":SHARD_COUNT,"assigned_plates":assigned,"assigned_plates_sha256":stable_sha(assigned),"source_rows":int(len(sample)),"distinct_target_tiles":int(sample.tile_id.nunique())},
      "execution":{"plate_receipts":plate_receipts,"exact_NUMBER_recovered":int(exact.sum()),"sky_consistency_le10arcsec":int((exact & np.isfinite(sep) & (sep<=10)).sum()),
                   "reference_normalization_pass":int(norm.sum()),"shape_success_exact":int((exact & shape_failed.eq(0)).sum()),"shape_returncode":int(shape_exec.get("returncode",-999)),
                   "full_remote_plate_array_accessed":False},
      "compatibility_repair":{"metric_formula_changed":False,"patch":patch},
      "external_label_firewall":{"external_label_reveal_authorized":False,"date_or_external_environment_used":False},
      "sidecar":{"path":side,"rows":int(len(full)),"csv_sha256":csvsha,"gzip_sha256":gzsha}
    }
    receipt["integrity"]={"canonical_payload_sha256_without_integrity":canon(receipt)}
    rp=a.out_dir/f"JANUS-PALOMAR-JPFM-2F-C2B1-SHARD-{a.shard_index:02d}-RECEIPT-RUN-001.json"; rp.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n")
    print(f"[C2B1 shard {a.shard_index}] exact={int(exact.sum())}/{len(full)} norm={int(norm.sum())}/{len(full)} shape={int((exact & shape_failed.eq(0)).sum())}/{len(full)}",flush=True)

if __name__=="__main__": main()
