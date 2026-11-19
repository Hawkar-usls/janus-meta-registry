"""Read only published OpenFOAM results; no external code execution or solver run."""
import hashlib, json, math, pathlib, re, tarfile, tempfile, urllib.request
URL="https://zenodo.org/records/13149491/files/OpenFoamData.tgz?download=1"
MD5="922663cb89aa3f47c611de8b2c7af5f4"
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
            if md5.hexdigest()!=MD5:raise ValueError("archive checksum mismatch")
            found={};count=0;expanded=0
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
                        if len(f)!=3:raise ValueError(f"unexpected flux record {m.name}:{lineno}")
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
                for kind,scale in (("inletOutletFlux",4e6),("inletOutletWaterFlux",4e6)):
                    q=data.get(kind,[]);ins=sorted(x for x in q if x[2]=="inlet");outs=sorted(x for x in q if x[2]=="outlet")
                    if ins and outs and ins[-1][:2]==outs[-1][:2]:
                        row[kind+"_net_scaled"]=scale*(ins[-1][3]+outs[-1][3])
                points.append(row)
            result["points"]=points;result["expected_cases"]=26;result["missing_cases"]=sorted(TARGET-{(x["rpm"],x["internal_pO2_pa"]) for x in points})
            result["status"]="PASS_CFD_POSTPROCESSING_ONLY" if len(points)==26 else "PARTIAL_CFD_POSTPROCESSING"
            result["boundary"]="Published CFD postprocessing, not an independent simulation or physical validation. No permeance retuning. Figure 3 uses 15 of 24 main cases; report all 26."
    except Exception as e:
        result["status"]="BLOCKED_CFD";result["error"]=f"{type(e).__name__}: {e}"
    pathlib.Path("r0d1c1-cfd.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    if result["status"]!="PASS_CFD_POSTPROCESSING_ONLY":raise SystemExit(1)
if __name__=="__main__":main()
