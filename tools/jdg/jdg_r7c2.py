"""JDG R7C.2: pinned public artifact export and independent registry intake.
The compiler output is inert data. No engine, execution, training or remote dispatch.
The original per-run public key is pinned from the verified CI log.
"""
import base64,hashlib,json,os,re,subprocess,sys,tempfile,time,urllib.request,urllib.error
from pathlib import Path
P=json.loads(Path(__file__).with_name("JDG_R7C2_PIN.json").read_text())
FILES={"RESULT.json":16384,"PUBLIC.pem":1024,"COMPILED_LOCK.txt":2000000}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def sha(raw):return hashlib.sha256(raw).hexdigest()
def unique(pairs):
    out={}
    for k,v in pairs:
        require(k not in out,"DUPLICATE_KEY");out[k]=v
    return out
def decode(raw):return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))
def cmd(args,timeout=30):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=timeout)
    require(p.returncode==0,"COMMAND_FAILED:"+args[0]+":"+args[1])
    return p.stdout.decode().strip()
def verified(files):
    require(set(files)==set(FILES),"FILE_SET")
    require(all(0<len(files[k])<=FILES[k] for k in FILES),"FILE_LIMIT")
    require(sha(files["PUBLIC.pem"])==P["public_key_sha256"],"PUBLIC_KEY_PIN")
    require(len(files["COMPILED_LOCK.txt"])==P["compiled_bytes"] and sha(files["COMPILED_LOCK.txt"])==P["compiled_sha256"],"COMPILED_PIN")
    env=decode(files["RESULT.json"]);require(set(env)=={"report","signature"},"ENVELOPE")
    r=env["report"];sig=base64.b64decode(env["signature"],validate=True);require(len(sig)==64,"SIGNATURE")
    q={"schema":"janus.jdg.request.v1","capability":P["capability"],"provider":P["provider"],"version":P["version"],"fixture_sha256":P["fixture_sha256"],"binary_sha256":P["compiler_sha256"],"run_id":str(P["source_run"]),"run_attempt":str(P["source_attempt"]),"head":P["source_merge_head"],"action_authority":False}
    expected={"schema":"janus.jdg.result.v1","request":q,"request_sha256":P["request_sha256"],"compiler_sha256":P["compiler_sha256"],"compiled_sha256":P["compiled_sha256"],"compiled_bytes":P["compiled_bytes"],"positive_exit":0,"negative_exit":1,"runtime_execution":False,"engine_calls":False,"external_peer":False,"action_authority":False}
    require(r==expected and sha(canonical(q))==P["request_sha256"],"EXACT_RESULT_PIN")
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);(root/"key").write_bytes(files["PUBLIC.pem"]);(root/"msg").write_bytes(canonical(r));(root/"sig").write_bytes(sig)
        cmd(["openssl","pkeyutl","-verify","-pubin","-rawin","-inkey",str(root/"key"),"-in",str(root/"msg"),"-sigfile",str(root/"sig")])
    return {k:sha(v) for k,v in files.items()}
def read_local(root):
    out={}
    for k,lim in FILES.items():
        p=Path(root)/k;require(p.is_file() and not p.is_symlink() and p.stat().st_size<=lim,"LOCAL_FILE")
        out[k]=p.read_bytes()
    return out
def receipt(hashes,source_commit=None):
    return {"schema":"janus.jdg.registry_receipt.v1","status":"VERIFIED_PUBLIC_TOOL_RESULT_RESEARCH_ONLY","source_repository":P["source_repo"],"source_run_id":P["source_run"],"source_run_attempt":P["source_attempt"],"source_head_sha":P["source_head"],"source_artifact_id":P["artifact_id"],"source_artifact_sha256":P["artifact_sha256"],"source_export_commit":source_commit,"provider":P["provider"],"version":P["version"],"capability":P["capability"],"file_sha256":hashes,"original_ci_key_pinned":True,"signed_result_verified":True,"execution_authority":False,"training_authority":False,"external_peer":False,"external_compute":False,"production_changed":False,"storage_policy":"REPORT_ONLY_NOT_TRAINING"}
def write(root,files,r):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    for k,v in files.items():(root/k).write_bytes(v)
    (root/"RECEIPT.json").write_bytes(canonical(r)+b"\n")
def scope(repo,branch):
    require(os.environ["GITHUB_REPOSITORY"]==repo and os.environ["JDG_HEAD_REPO"]==repo and os.environ["JDG_HEAD_BRANCH"]==branch,"EVENT_SCOPE")
    remote=cmd(["git","remote","get-url","origin"]);require(remote in ("https://github.com/"+repo,"https://github.com/"+repo+".git"),"REMOTE_SCOPE")
def publish(repo,branch,root):
    scope(repo,branch)
    paths=[str(Path(root)/k) for k in (*FILES,"RECEIPT.json")]
    cmd(["git","add","--",*paths])
    staged=set(cmd(["git","diff","--cached","--name-only"]).splitlines());require(staged==set(paths),"STAGING_SCOPE")
    cmd(["git","-c","user.name=JDG research archive","-c","user.email=41898282+github-actions[bot]@users.noreply.github.com","commit","-m","research(JDG): archive verified public tool result"])
    cmd(["git","push","origin","HEAD:refs/heads/"+branch],timeout=40)
    commit=cmd(["git","rev-parse","HEAD"])
    with open(os.environ["GITHUB_OUTPUT"],"a") as f:f.write("checkpoint="+commit+"\n")
    return commit
def export(folder):
    scope(P["source_repo"],P["export_branch"])
    files=read_local(folder);h=verified(files);r=receipt(h)
    write(P["export_path"],files,r)
    c=publish(P["source_repo"],P["export_branch"],P["export_path"])
    print("JDG_R7C2_EXPORT "+json.dumps({"commit":c,"receipt":r},sort_keys=True),flush=True)
def remote_files():
    end=time.monotonic()+180
    while time.monotonic()<end:
        try:
            with tempfile.TemporaryDirectory() as d:
                env={"PATH":"/usr/bin:/bin","HOME":d,"GIT_CONFIG_NOSYSTEM":"1","GIT_TERMINAL_PROMPT":"0"}
                p=subprocess.run(["git","ls-remote","--heads","https://github.com/"+P["source_repo"]+".git","refs/heads/"+P["export_branch"]],cwd=d,env=env,capture_output=True,timeout=12,check=True)
                parts=p.stdout.decode().split()
            require(len(parts)==2 and re.fullmatch("[a-f0-9]{40}",parts[0]) and parts[1]=="refs/heads/"+P["export_branch"],"SOURCE_REF")
            c=parts[0];files={}
            for k,lim in {**FILES,"RECEIPT.json":16384}.items():
                url="https://raw.githubusercontent.com/"+P["source_repo"]+"/"+c+"/"+P["export_path"]+"/"+k
                with urllib.request.urlopen(url,timeout=10) as f:
                    require(f.status==200 and f.geturl()==url,"SOURCE_URL");raw=f.read(lim+1)
                require(0<len(raw)<=lim,"SOURCE_SIZE");files[k]=raw
            r=decode(files.pop("RECEIPT.json"));h=verified(files);require(r==receipt(h),"EXPORT_RECEIPT")
            return c,files,h
        except (urllib.error.URLError,TimeoutError,subprocess.TimeoutExpired,subprocess.CalledProcessError) as e:
            if isinstance(e,urllib.error.HTTPError) and e.code not in (404,429,500,502,503,504):raise
            time.sleep(5)
    raise ValueError("EXPORT_NOT_AVAILABLE")
def intake():
    repo="Hawkar-usls/janus-meta-registry";scope(repo,P["intake_branch"])
    c,files,h=remote_files();r=receipt(h,c);write(P["archive_path"],files,r)
    commit=publish(repo,P["intake_branch"],P["archive_path"])
    print("JDG_R7C2_INTAKE "+json.dumps({"commit":commit,"receipt":r},sort_keys=True),flush=True)
def audit(root,mode):
    files=read_local(root);h=verified(files);r=decode((Path(root)/"RECEIPT.json").read_bytes())
    if mode=="export":require(r==receipt(h),"ARCHIVE_RECEIPT")
    else:
        c=r["source_export_commit"];require(isinstance(c,str) and re.fullmatch("[a-f0-9]{40}",c) and r==receipt(h,c),"ARCHIVE_RECEIPT")
    print("JDG_R7C2_ARCHIVE_PASS "+json.dumps({"mode":mode,"commit":cmd(["git","rev-parse","HEAD"]),"receipt_sha256":sha(canonical(r)),"original_signed_result":True,"no_execution":True,"no_training":True},sort_keys=True))
if __name__=="__main__":
    if sys.argv[1]=="export":export(sys.argv[2])
    elif sys.argv[1]=="intake":intake()
    elif sys.argv[1]=="audit":audit(sys.argv[2],sys.argv[3])
    else:raise ValueError("MODE")
