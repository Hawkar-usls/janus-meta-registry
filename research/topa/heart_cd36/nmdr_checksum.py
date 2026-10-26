import json, pathlib, os, hashlib, zipfile, collections, re
d=pathlib.Path(os.environ['TEMP'])/'JANUS_HEART_CD36_20261026'
store=d/'nmdr'
results={}
for sid,fn,bio,qc in [
 ('ST005014','ST005014_Fig2D_cell_siCD36.zip',4,0),
 ('ST005062','ST005062_Rawdata.zip',9,3)]:
 p=store/fn
 z=zipfile.ZipFile(p)
 bad=z.testzip()
 files=z.namelist()
 factors=(store/(sid+'_factors.json')).read_text('utf-8')
 listed=json.loads((store/(sid+'_files.json')).read_text('utf-8'))
 known={f['name'] for f in listed['compressed_file_content'][fn]}
 assert not bad
 assert set(files)==known,('ZIP_MISMATCH',sid,files,known)
 data=(store/(sid+'_data.json')).read_text('utf-8')
 metas=set(re.findall(r'^metabolite_name\t([^\r\n]+)',data,re.M))
 results[sid]={
  'study_id':sid,'raw_zip_name':fn,
  'raw_zip_bytes':p.stat().st_size,'raw_zip_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
  'raw_zip_crc':'PASS','mzml_files':len(files),
  'individual_biological_samples':bio,'pooled_qc_samples':qc,
  'processed_table_sha256':hashlib.sha256((store/(sid+'_data.json')).read_bytes()).hexdigest(),
  'processed_table_bytes':(store/(sid+'_data.json')).stat().st_size,
  'processed_metabolite_names':len(metas),
  'analytical_notes':'These samples are lipidomic study replicates, NOT mouse-level echocardiography pairs.'
 }
 z.close()
print(json.dumps(results,indent=2))
(d/'nmdr_check.json').write_text(json.dumps(results,indent=2),encoding='utf-8')