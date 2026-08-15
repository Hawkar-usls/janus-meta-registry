#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import requests
from pathlib import Path

URL='https://irsa.ipac.caltech.edu/data/DSS/images/dss1red/dss1red_XE454.fits'
UA='JANUS-JPFM-4A-XE454-time-audit/1.0'


def sha256(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def header_end(buf:bytes):
    for i in range(len(buf)//80):
        if buf[i*80:i*80+8]==b'END     ':
            logical=(i+1)*80
            return ((logical+2879)//2880)*2880
    return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
    with requests.get(URL,headers={'Range':'bytes=0-131071','Accept-Encoding':'identity','User-Agent':UA},stream=True,timeout=(20,60)) as r:
        if r.status_code not in (200,206):r.raise_for_status()
        data=bytearray()
        for chunk in r.iter_content(16384):
            if not chunk:continue
            data.extend(chunk);end=header_end(data)
            if end is not None:break
            if len(data)>1024*1024:raise RuntimeError('header >1MiB')
        else:raise RuntimeError('no FITS END')
        hb=bytes(data[:end]);status=r.status_code;cr=r.headers.get('Content-Range')
    cards=[hb[i:i+80].decode('ascii',errors='replace') for i in range(0,len(hb),80)]
    wanted={}
    for c in cards:
        k=c[:8].strip()
        if k in {'DATE-OBS','EXPOSURE','TIMESYS','TIMEUNIT','TELESCOP','PLATELAB','PLATEID','REGION','PLTRAH','PLTRAM','PLTRAS','PLTDECSN','PLTDECD','PLTDECM','PLTDECS'}:
            wanted.setdefault(k,[]).append(c)
    date_cards=wanted.get('DATE-OBS',[])
    if not date_cards:raise RuntimeError('DATE-OBS missing')
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-XE454-FITS-TIME-CARD-AUDIT-v1.0',
      'date':'2026-08-15',
      'status':'PUBLIC_FITS_RAW_HEADER_CARD_FROZEN__INTERPRETATION_GATE_PENDING',
      'plate_id':'XE454','source_url':URL,'http_status':status,'content_range':cr,
      'primary_header_sha256':sha256(hb),'primary_header_bytes':len(hb),
      'selected_raw_cards':wanted,
      'fits_default_time_semantics_reference':'STScI FITS standard: for four-digit DATE-OBS before 1972, default time interpretation is UT; DATE-OBS defaults to start of observation unless otherwise explained. Explicit TIMESYS/header comments override defaults if present.',
      'outcome_access':{'bluebook':False,'nuclear':False,'additional_poss_outcomes':False},
      'claim_ceiling':'RAW_FITS_TIME_CARD_AUDIT_ONLY__NO_ROCKET_ATTRIBUTION'
    }
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
