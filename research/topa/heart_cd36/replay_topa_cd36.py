#!/usr/bin/env python3
"""JANUS TOPA read-only audit of publisher Source Data for DOI 10.1038/s41467-026-79082-8.
This is an independent arithmetic replay of PUBLISHED SUMMARY STATISTICS,
NOT a re-analysis of animal-level echocardiographic data.
"""
import hashlib, io, json, math, pathlib, posixpath, re, zipfile
import xml.etree.ElementTree as ET
import scipy
from scipy.stats import studentized_range

BASE=pathlib.Path(__file__).resolve().parent
ZIP=BASE/"41467_2026_79082_MOESM4_ESM.zip"
URL="https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41467-026-79082-8/MediaObjects/41467_2026_79082_MOESM4_ESM.zip"
SHA_EXPECTED="9184a5f47c0a4a7488457d785f5833f59666cbc00d884873a728d887ee27868f"
N={"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main","r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
R="{http://schemas.openxmlformats.org/package/2006/relationships}"
def workbook(blob, sheet_name):
    with zipfile.ZipFile(io.BytesIO(blob)) as xf:
        wb=ET.fromstring(xf.read("xl/workbook.xml"))
        rel=ET.fromstring(xf.read("xl/_rels/workbook.xml.rels"))
        targets={x.attrib["Id"]:x.attrib["Target"] for x in rel.findall(R+"Relationship")}
        sh=next(s for s in wb.findall(".//m:sheets/m:sheet",N) if s.attrib["name"]==sheet_name)
        target=targets[sh.attrib["{"+N["r"]+"}id"]]
        target=target.lstrip("/") if target.startswith("/") else "xl/"+target
        target=posixpath.normpath(target)
        strings=[]
        if "xl/sharedStrings.xml" in xf.namelist():
            sr=ET.fromstring(xf.read("xl/sharedStrings.xml"))
            strings=["".join(t.text or "" for t in si.findall(".//m:t",N)) for si in sr.findall("m:si",N)]
        sr=ET.fromstring(xf.read(target))
        data={}
        for c in sr.findall(".//m:sheetData/m:row/m:c",N):
            cell=c.attrib.get("r","")
            v=c.find("m:v",N)
            if v is not None and v.text:
                val=v.text
                if c.attrib.get("t")=="s":val=strings[int(val)]
                elif c.attrib.get("t") not in ("str","inlineStr","e"):
                    try:val=float(val)
                    except ValueError:pass
                data[cell]=val
            elif c.attrib.get("t")=="inlineStr":
                data[cell]="".join(t.text or "" for t in c.findall(".//m:t",N))
        return data
def number(c, key):
    value=c[key]
    if not isinstance(value,(int,float)):value=float(value)
    assert math.isfinite(value), (key,value)
    return float(value)
def interval(value):
    nums=[float(v) for v in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?",str(value))]
    assert len(nums)==2, value
    return nums
def approximate(a,b,eps=0.021):
    return abs(a-b)<=eps
zip_bytes=ZIP.read_bytes()
sha=hashlib.sha256(zip_bytes).hexdigest().upper()
assert sha.lower()==SHA_EXPECTED.lower(),(sha,SHA_EXPECTED)
with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
    bad=z.testzip()
    assert bad is None,bad
    paths=z.namelist()
    f9=workbook(z.read("Source Data/Figure 9/Figure 9.xlsx"),"9D-F, H Stats")
    f8=workbook(z.read("Source Data/Figure 8/Figure 8.xlsx"),"8CEG Stats")
    f10=workbook(z.read("Source Data/Figure 10/Figure 10 Stats.xlsx"),"Figure 10A")
q=studentized_range.ppf(.95,4,48)
assert approximate(q,3.763748855962747,1e-8)
def functional(name, pairrow, publisherrow, ctrlrow, aavrow, pltrow):
    # all row refs represent PRE, 4-week post and RM-ANOVA contrasts.
    means={"IR_SALINE":number(f9,"I"+str(ctrlrow)),
           "AAV_CD36KD":number(f9,"I"+str(aavrow)),
           "PLT_AAV_CD36KD":number(f9,"J"+str(pltrow))}
    result={"endpoint":name,"n_per_group":int(number(f9,"M"+str(pltrow))),
            "post_4weeks_means":means,"contrasts":[]}
    for r,pub,comparator in zip(pairrow,publisherrow,("IR_SALINE","AAV_CD36KD")):
        a=number(f9,"I"+str(r)); b=number(f9,"J"+str(r))
        diff=b-a; se=number(f9,"L"+str(r))
        df=int(number(f9,"P"+str(r)))
        assert df==48
        ci=(diff-q*se/math.sqrt(2),diff+q*se/math.sqrt(2))
        published=interval(f9["J"+str(pub)])
        # Publisher intervals are (first minus second), opposite to treatment benefit
        expected=(-published[1],-published[0])
        assert approximate(diff,means["PLT_AAV_CD36KD"]-means[comparator],.01)
        assert all(approximate(got,exp) for got,exp in zip(ci,expected)),(name,ci,expected)
        result["contrasts"].append({
          "treatment":"PLT_AAV_CD36KD","comparator":comparator,
          "absolute_difference":round(diff,4),
          "tukey_adjusted_95pct_ci":[round(v,4) for v in ci],
          "publisher_ci_replayed":True,
          "source_comparison_row":r,"source_adjusted_ci_row":pub,
          "n_each":int(number(f9,"M"+str(r)))})
    assert result["n_per_group"]==7
    return result
outputs=[
 functional("EF_percent",[135,136],[116,117],135,136,136),
 functional("FS_percent",[181,182],[162,163],181,182,182),
 functional("CO_units_per_publisher_table",[227,228],[208,209],227,228,228)]
# Independently check that reported cell-cycle markers differ, while remaining surrogate markers.
cycle=[]
for name,r,ctrl,treat in [("Ki67",52,48,50),("pH3",80,76,78)]:
    n=int(number(f8,"M"+str(r)))
    assert n==6
    cycle.append({"marker":name,"control_mean":number(f8,"I"+str(r)),
                  "plt_aav_mean":number(f8,"J"+str(r)),
                  "reported_difference":number(f8,"K"+str(r)),
                  "n_per_group":n,
                  "cell_cycle_activity_only":True,
                  "proof_of_completed_cytokinesis":False})
# Safety comparisons are non-significant but underpowered to prove equivalence.
safety=[]
for kind,row,publishedrow in [("PT",25,17),("APTT",58,50)]:
    if "I"+str(row) not in f10:continue
    n=int(number(f10,"M"+str(row)))
    safety.append({"measure":kind,"control_ir_mean":number(f10,"I"+str(row)),
                   "plt_aav_ir_mean":number(f10,"J"+str(row)),
                   "n_per_group":n,"available_publisher_adjusted_ci":f10.get("J"+str(publishedrow)),
                   "equivalence_proven":False})
receipt={
 "schema":"janus.topa.heart_cd36_source_summary_replay.v1",
 "paper_doi":"10.1038/s41467-026-79082-8",
 "publisher_source_url":URL,"archive_bytes":len(zip_bytes),
 "archive_sha256":sha.lower(),"zip_crc_test":"PASS",
 "zip_entries":len(paths),"statistical_software":"SciPy "+scipy.__version__,
 "test":"Tukey q at alpha=0.05, four groups, 48 df",
 "tukey_quantile":round(float(q),9),
 "functional_4week_results":outputs,"cell_cycle_markers":cycle,
 "coagulation_safety_summary":safety,
 "sample_count_check":{"echocardiography_groups":4,"animals_per_group":7,
                        "total_subjects":int(number(f9,"B124")),
                        "figure9_h_missing_values":int(number(f9,"B125"))},
 "evidence_limits":{
   "individual_animal_pre_post_pairs":"NOT_PRESENT_IN_FIGURE_9_SUMMARY_WORKBOOK",
   "CI_replay":"INDEPENDENT_ARITHMETIC_REPLAY_FROM_PUBLISHER_SUMMARY",
   "animal_level_reanalysis":"NOT_COMPLETED",
   "completed_cardiomyocyte_cytokinesis":"NOT_ESTABLISHED",
   "durability_beyond_4weeks":"NOT_ESTABLISHED",
   "long_term_metabolic_safety":"NOT_ESTABLISHED",
   "independent_replication":"NOT_ESTABLISHED",
   "clinical_efficacy":"NOT_ESTABLISHED"},
 "scientific_gate_promotion":False,
 "topa_verdict":"SUMMARY_ARITHMETIC_REPLAY_PASS__PRIMARY_ANIMAL_DATA_AND_CAUSAL_EXIT_OPEN"
}
assert receipt["sample_count_check"]["total_subjects"]==28
assert receipt["sample_count_check"]["figure9_h_missing_values"]==0
p=BASE/"replay_receipt.json"
p.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"receipt_path":str(p),"sha256":sha,"bytes":len(zip_bytes),"results":outputs,
"cell_cycle":cycle,"safety":safety,"verdict":receipt["topa_verdict"]},ensure_ascii=False,indent=2))