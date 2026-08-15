#!/usr/bin/env python3
"""Build cryptographically separated blind Wedjat annotation packets.

Primary design goals:
- source museum bytes are SHA-256 sealed before any derived blind copy;
- annotators never receive object IDs, dates, periods, glyph targets, fractions,
  prior scores, chronology direction, or the private blind-ID mapping;
- the displayed blind PNG preserves decoded pixel values and dimensions exactly
  while removing filename/metadata leakage by lossless PNG re-encoding;
- source-file SHA-256 and canonical decoded-pixel SHA-256 are recorded privately;
- no crop, mirror, rotation, denoise, contrast change, or rescale is performed.

This tool prepares packets. It cannot create independent human annotators.
"""
from __future__ import annotations
import argparse, hashlib, json, random, shutil
from pathlib import Path
from PIL import Image

COMPONENTS = [
    "A1_EYEBROW_UPPER_EYE",
    "A2_HUMAN_EYE_CONTOUR",
    "A3_PUPIL",
    "A4_VERTICAL_FALCON_MARK",
    "A5_DIAGONAL_FALCON_MARK",
    "A6_SPIRAL_CURL",
]
VISIBILITY = ["VISIBLE","PARTIAL","DAMAGED","OCCLUDED","NOT_SEPARABLE","ABSENT_OR_NOT_DEPICTED","UNSURE"]

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()

def canonical_pixel_hash(im: Image.Image) -> str:
    # Preserve stored orientation and dimensions; no EXIF transpose.
    mode = im.mode
    payload = f"{mode}|{im.width}|{im.height}|".encode() + im.tobytes()
    return sha256_bytes(payload)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True, help='Private source JSON list')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--seed', type=int, required=True, help='Private deterministic shuffle seed')
    args=ap.parse_args()

    src=json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    if not isinstance(src, list) or len(src)<2: raise SystemExit('manifest must be a JSON list with >=2 items')
    out=Path(args.out_dir); public=out/'public_packet'; private=out/'private_control'
    public.mkdir(parents=True, exist_ok=True); private.mkdir(parents=True, exist_ok=True)

    rows=[]
    for rec in src:
        p=Path(rec['path'])
        raw_sha=sha256_file(p)
        expected=rec.get('expected_sha256')
        if expected and raw_sha.lower()!=expected.lower(): raise SystemExit(f"SHA mismatch: {p}")
        with Image.open(p) as im:
            im.load(); pix_sha=canonical_pixel_hash(im); size=[im.width, im.height]; mode=im.mode
        rows.append({**rec,'source_sha256':raw_sha,'pixel_sha256':pix_sha,'size':size,'mode':mode})

    rng=random.Random(args.seed); rng.shuffle(rows)
    private_map=[]; public_manifest=[]
    for i,rec in enumerate(rows,1):
        blind=f"WJ-{i:03d}"
        p=Path(rec['path'])
        blind_file=f"{blind}.png"
        with Image.open(p) as im:
            im.load(); before=canonical_pixel_hash(im)
            im.save(public/blind_file, format='PNG', optimize=False)
        with Image.open(public/blind_file) as chk:
            chk.load(); after=canonical_pixel_hash(chk)
        if before!=after: raise SystemExit(f"pixel mismatch after blind re-encode: {p}")
        packet_sha=sha256_file(public/blind_file)
        public_manifest.append({
            'blind_id':blind,'file':blind_file,'width':rec['size'][0],'height':rec['size'][1],
            'mode':rec['mode'],'pixel_sha256':after,'packet_file_sha256':packet_sha
        })
        private_map.append({
            'blind_id':blind,'source_path':str(p),'source_sha256':rec['source_sha256'],
            'pixel_sha256':rec['pixel_sha256'],'museum_object_id':rec.get('museum_object_id'),
            'period':rec.get('period'),'date':rec.get('date'),'source_url':rec.get('source_url')
        })
        template={
            'blind_id':blind,'annotator_id':'REPLACE_WITH_PSEUDONYMOUS_ID','submission_version':'v0.13',
            'image_pixel_sha256':after,'image_width':rec['size'][0],'image_height':rec['size'][1],
            'components':{c:{'visibility':'UNSURE','representation':'UNSET','points_px':[],
                              'width_px':None,'confidence_0_to_1':None,'note':''} for c in COMPONENTS},
            'annotator_attestation':{
                'worked_independently':False,'did_not_view_other_annotation':False,
                'did_not_use_object_identity_date_glyph_fraction_or_prior_scores':False
            }
        }
        (public/f"{blind}.annotation.template.json").write_text(json.dumps(template,indent=2)+'\n',encoding='utf-8')

    (public/'PUBLIC_MANIFEST.json').write_text(json.dumps({'version':'v0.13','images':public_manifest,'components':COMPONENTS,'visibility_states':VISIBILITY},indent=2)+'\n',encoding='utf-8')
    (private/'PRIVATE_MAP.json').write_text(json.dumps({'version':'v0.13','shuffle_seed':args.seed,'mapping':private_map},indent=2)+'\n',encoding='utf-8')
    # Hash the complete public package file set after generation.
    entries=[]
    for p in sorted(public.iterdir()): entries.append({'file':p.name,'sha256':sha256_file(p)})
    bundle_hash=sha256_bytes(json.dumps(entries,sort_keys=True,separators=(',',':')).encode())
    (private/'PACKET_RECEIPT.json').write_text(json.dumps({'version':'v0.13','public_entries':entries,'public_bundle_sha256':bundle_hash},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PACKET_BUILT','public_bundle_sha256':bundle_hash,'n_images':len(rows)},indent=2))

if __name__=='__main__': main()
