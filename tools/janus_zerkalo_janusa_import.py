#!/usr/bin/env python3
"""Import all immutable numeric-sky mirror directions to Meta Registry via GitHub Actions.
Run in Hawkar-usls/janus-meta-registry under explicit contents:write and source archive read.
"""
import base64, hashlib, io, json, os, pathlib, sys, zipfile
import requests
SOURCE_REPO="Hawkar-usls/Janus-Cosmos"
RUN=44835058758
ARTIFACT=14678325996
ARTIFACT_DIGEST="a6737de1bd44b74b56e04358d23ca635856f73d9c61a33e469eaa77ccaa22d2f"
COORD_SHA="6f8d9bc5c034ac023df84002a5fadfadb7491766ebbb931f140a51d4838310ef"
COORD="data/JANUS-ZERKALO-JANUSA-R0M2-CELESTIAL-COORDINATES-2026-11-21.json"
SYNTH="data/JANUS-ZERKALO-JANUSA-R0M2-NUMERIC-PROJECTIONS-2026-11-21.json"
MANIFEST="data/JANUS-ZERKALO-JANUSA-R0M2-MANIFEST-2026-11-21.json"
TARGET_REPO="Hawkar-usls/janus-meta-registry"
H={"Authorization":"Bearer "+os.environ["GH_TOKEN"],"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
def sha(b):return hashlib.sha256(b).hexdigest()
def get(url,timeout=100):
    r=requests.get(url,headers=H,timeout=timeout);r.raise_for_status();return r
def upload(path,data):
    # Contents API accepts up to 100MB, all objects are UTF8 JSON and under 4MB.
    assert len(data)<30*1024*1024 and isinstance(data,bytes)
    url="https://api.github.com/repos/"+TARGET_REPO+"/contents/"+path
    prev=requests.get(url,headers=H,timeout=30)
    assert prev.status_code in (200,404),prev.text[:200]
    payload={"message":"Зеркало Януса: сохранить в Meta Registry проверенный числовой небесный атлас",
             "content":base64.b64encode(data).decode(),"branch":"main"}
    if prev.status_code==200:
        existing=prev.json(); assert existing["type"]=="file"
        # Avoid overwriting another update by racing.
        payload["sha"]=existing["sha"]
    r=requests.put(url,headers=H,json=payload,timeout=120)
    r.raise_for_status()
    j=r.json()
    print("JANUS_MIRROR_IMPORT",json.dumps({"path":path,"size":len(data),"sha256":sha(data),
      "commit":j["commit"]["sha"],"url":j["content"]["html_url"]}),flush=True)
def main():
    url=f"https://api.github.com/repos/{SOURCE_REPO}/actions/artifacts/{ARTIFACT}"
    m=get(url).json()
    assert m["workflow_run"]["id"]==RUN and m["digest"]=="sha256:"+ARTIFACT_DIGEST and not m["expired"]
    b=get(url+"/zip",timeout=180).content
    assert sha(b)==ARTIFACT_DIGEST and len(b)<100*1024*1024
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        names=z.namelist()
        assert len(names)==len(set(names))
        def read(n):
            assert n in names
            return z.read(n)
        raw=read("mirror/mirrored_explicit_icrs_directions.json")
        assert sha(raw)==COORD_SHA
        coords=json.loads(raw)
        assert coords["generated_directions"]==3772 and coords["source_coordinates"]==943
        assert len(coords["directions"])==3772
        assert len({(round(x["ra_deg"],6),round(x["dec_deg"],6)) for x in coords["directions"]})==3770
        assert all(x["operator"] in ("original","ra_meridian_reflection","equatorial_reflection","antipode") for x in coords["directions"])
        synthetic=read("mirror/mirrored_synthetic_math_directions.json")
        syn=json.loads(synthetic)
        assert syn["generated"]==320 and len(syn["directions"])==320
        # Already frozen at source; never promote artificial numerical projections.
        assert all(x.get("scientific_qualified") is False or x.get("valid") is False for x in syn["directions"])
        receipt=json.loads(read("numeric_source_merge_receipt.json"))
        assert receipt["full_failed"]==0 and receipt["input_repos"]==48 and receipt["labelled_coordinates"]==1529
        manifest={
           "schema":"janus.zerkalo.janusa.coordinate.atlas.v1","name_ru":"Зеркало Януса",
           "date":"2026-11-21","state":"SOURCE_ARCHIVED_FULL_SNAPSHOT__SCIENTIFIC_CROSSMATCH_SEPARATE",
           "source_repo":SOURCE_REPO,"source_run":RUN,"source_artifact":ARTIFACT,
           "archive_sha256":ARTIFACT_DIGEST,
           "coordinate_json":COORD,"coordinate_json_sha256":COORD_SHA,
           "numeric_projections_json":SYNTH,"numeric_projections_sha256":sha(synthetic),
           "original_declared_directions":943,"all_declared_and_mirrored_directions":3772,
           "numeric_only_projections":320,
           "public_repos_scanned":48,"complete_repos":42,"partial_repos":6,"unscanned_private_repos":3,
           "rules":{"source_values_unchanged":True,"mirror_variants_not_physical_measurements":True,
             "numeric_projection_is_arbitrary":True,"no_discovery_claim_without_independent_repeated_observations":True},
           "cosmos_validation":"R42B pointing provenance HOLD; survey is catalog-only, not a radio observation",
           "origin_reference":"data/JANUS-NUMERIC-SKY-MIRROR-AUDIT-R0M2-2026-11-21.json"
        }
        upload(COORD,raw)
        upload(SYNTH,synthetic)
        upload(MANIFEST,(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode())
        print("JANUS_MIRROR_IMPORT_FINAL",json.dumps(manifest,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
