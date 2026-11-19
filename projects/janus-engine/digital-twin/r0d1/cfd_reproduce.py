"""Read only published OpenFOAM results; no external code execution or solver run."""
import hashlib, json, math, pathlib, re, tarfile, tempfile, urllib.request
URL="https://zenodo.org/records/13149491/files/OpenFoamData.tgz?download=1"
MD5="922663cb89aa3f47c611de8b2c7af5f4"
SHA256="3f5d6e8fe5d07cbd022ac63c08b7873571b3333176fec7ef5303be2fe984ed4d"
LIMIT=1500*1024**2
CASE=re.compile(r"(?:^|/)bugsScalarTransport3D(1200|1500|1800|2100|2400)Sc1LRp(\d+)/postProcessing/(flux|inletOutletFlux|inletOutletWaterFlux)/([0-9.eE+-]+)/[^/]+\.dat$")
TARGET={(r,p) for r in (1200,1800,2400) for p in range(3000,17001,2000)}|{(1500,7000),(2100,7000)}
def main():
    result={"stage":"R0D1C1_CFD","source_doi":"10.5281/zenodo.13149491","status":"INCOMPLETE","physical_janus_runs":0,"run008_modified":False}
    try:
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/"OpenFoamData.tgz";md5=hashlib.md5(usedforsecurity=False);sha=hashlib.sha256();size=0
            with urllib.request.urlopen(URL,timeout=120) as response,path.open("wb") as out:
                for chunk in iter(lambda:response.read(4*1024**2),b""):
                    size+=len(chunk)
                    if size>LIMIT:raise ValueError("compressed size exceeds bound")
                    md5.update(chunk);sha.update(chunk);out.write(chunk)
            result.update(archive_bytes=size,md5=md5.hexdigest(),sha256=sha.hexdigest())
            if md5.hexdigest()!=MD5 or sha.hexdigest()!=SHA256:raise ValueError("archive checksum mismatch")
            found={};count=0;expanded=0
            format_counts={};format_examples={}
            with tarfile.open(path,mode="r|gz") as archive:
                for m in archive:
                    count+=1;expanded+=m.size
                    if count>500000 or expanded>40*1024**3:raise ValueError("inventory bound")
                    match=CASE.search(m.name)
                    if not match or not m.isfile():continue
                    rpm,p,kind,time=match.groups();key=(int(rpm),int(p))
                    if key not in TARGET:continue
                    expected={"flux":"flux.dat","inletOutletFlux":"inletOutletFlux.dat","inletOutletWaterFlux":"inletOutletWaterFlux.dat"}[kind]
                    if pathlib.PurePosixPath(m.name).name!=expected:continue
                    if m.size>50*1024**2:raise ValueError("flux table too large")
                    rows=found.setdefault(key,{}).setdefault(kind,[])
                    for lineno,line in enumerate(archive.extractfile(m),1):
                        s=line.decode("ascii").strip()
                        if not s or s.startswith("#"):continue
                        f=s.split()
                        fmt=f"{kind}:{len(f)}"
                        format_counts[fmt]=format_counts.get(fmt,0)+1
                        format_examples.setdefault(fmt,s[:300])
                        result["format_counts"]=format_counts
                        result["format_examples"]=format_examples
                        # Archived MembraneFluxPostProcessing.parse reads fields 0,1,2,
                        # allowing extra columns; inlet/outlet LineParserFactory requires 3.
                        if len(f)<3 or (kind!="flux" and len(f)!=3):raise ValueError(f"unexpected flux record {m.name}:{lineno}: {s[:200]}")
                        tm,val=float(f[0]),float(f[2])
                        if not math.isfinite(tm) or not math.isfinite(val):raise ValueError("nonfinite flux")
                        rows.append((float(time),tm,f[1],val))
            result.update(members=count,expanded_bytes=expanded)
            points=[]
            for rpm,p in sorted(TARGET):
                data=found.get((rpm,p),{});totals=sorted(x for x in data.get("flux",[]) if x[2]=="total")
                if not totals:continue
                last=totals[-1];flux=-4e6*last[3]
                row={"rpm":rpm,"internal_pO2_pa":p,"delta_p_pa":17660-p,"membrane_flux_umol_s":flux,"last_time_s":last[1],"total_records":len(totals),"figure3_visible":rpm in (1200,1800,2400) and p<=11000}
                for kind in ("inletOutletFlux","inletOutletWaterFlux"):
                    q=data.get(kind,[])
                    ins={x[:2]:x[3] for x in q if x[2]=="inlet"};outs={x[:2]:x[3] for x in q if x[2]=="outlet"}
                    common=sorted(ins.keys() & outs.keys())
                    row[kind+"_matched_records"]=len(common)
                    if common:
                        t=common[-1];net=ins[t]+outs[t]
                        if kind=="inletOutletFlux":
                            row["scalar_net_umol_s_author_sign"]=4e6*net
                            steady=[4e6*(ins[k]+outs[k]) for k in common if k[1]>=10]
                            row["scalar_steady_net_umol_s_author_sign"]=sum(steady)/len(steady) if steady else None
                            if t==last[:2]:row["signed_membrane_scalar_closure_umol_s"]=flux+4e6*net
                        else:
                            row["water_inlet_m3_s"]=-4*ins[t]
                            row["water_outlet_m3_s"]=4*outs[t]
                            row["water_net_m3_s"]=4*net
                points.append(row)
            result["points"]=points;result["expected_cases"]=26;result["missing_cases"]=sorted(TARGET-{(x["rpm"],x["internal_pO2_pa"]) for x in points})
            result["status"]="PASS_CFD_POSTPROCESSING_ONLY" if len(points)==26 else "PARTIAL_CFD_POSTPROCESSING"
            result["boundary"]="Published CFD postprocessing, not an independent simulation or physical validation. Parser semantics reconstructed from archived foamfiles.py and oxygenflux.py; extra membrane fields counted, never used as flux. Water Q is volumetric, not oxygen. No permeance retuning. Figure 3 uses 15 of 24 main cases; report all 26."
    except Exception as e:
        result["status"]="BLOCKED_CFD";result["error"]=f"{type(e).__name__}: {e}"
    pathlib.Path("r0d1c1-cfd.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    if result["status"]!="PASS_CFD_POSTPROCESSING_ONLY":raise SystemExit(1)
if __name__=="__main__":main()
