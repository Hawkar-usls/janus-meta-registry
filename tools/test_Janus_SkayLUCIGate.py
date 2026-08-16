import importlib.util, json, tempfile, unittest
from pathlib import Path
M=Path(__file__).with_name('Janus_SkayLUCIGate.py'); s=importlib.util.spec_from_file_location('skay',M); skay=importlib.util.module_from_spec(s); s.loader.exec_module(skay)
class T(unittest.TestCase):
 def row(self,t,status,name):
  rec={'status':status,'overlap_frame_r1_gate':{'native_psf_median_fwhm_px':6.0,'background_sigma':100.0,'passed':True}}
  if 'CANDIDATE' in status: rec['counterpart_test']={'matched_control_count':4,'morphology_status':'INSUFFICIENT_MATCHED_LOCAL_CONTROLS','source':{'peak_snr':4.2,'fwhm_geom_px':6.05,'elongation':1.2,'x':100.5,'y':100.5}}
  return {'src_id':'S','date_obs':t,'file_name':name,'instrument':'LUCI1','filters':'Br_gam clear','exact_x':'100','exact_y':'100','recovery':rec}
 def test_bracket(self):
  r=[self.row('2022-01-01T00:00:00','QUALIFIED_NO_COUNTERPART_INHERITED_R1','a'),self.row('2022-01-01T00:04:00','COUNTERPART_CANDIDATE','b'),self.row('2022-01-01T00:10:00','QUALIFIED_NO_COUNTERPART_INHERITED_R1','c')]; x=skay.classify_candidate(r,1); self.assertEqual(x['temporal_class'],'BRACKETED_ONE_FRAME_IR_EVENT'); self.assertFalse(x['persistent_counterpart_supported'])
 def test_multiframe(self):
  r=[self.row('2022-01-01T00:00:00','COUNTERPART_CANDIDATE','a'),self.row('2022-01-01T00:05:00','COUNTERPART_CANDIDATE','b')]; self.assertTrue(skay.classify_candidate(r,0)['persistent_counterpart_supported'])
 def test_secret_firewall(self):
  x=skay.safe_macro_extract('#define YG_IR_CARRIER_HZ 38256\n#define WIFI_PASSWORD "secret"\n',skay.SAFE_YAKS); self.assertEqual(x['YG_IR_CARRIER_HZ'],'38256'); self.assertNotIn('WIFI_PASSWORD',x)
 def test_accounting(self):
  receipt={'unresolved_sources':['U'],'source_evidence':{'A':{'parent_qualified':0,'new_qualified':1,'edge_recovered':0,'counterpart_candidates':0},'U':{'parent_qualified':0,'new_qualified':0,'edge_recovered':0,'counterpart_candidates':0}},'untested_results':[]}; x=skay.source_summary(receipt,[],42,39); self.assertEqual(x['sources_with_at_least_one_qualified_no_counterpart_epoch'],40); self.assertEqual(x['fully_sensitivity_unresolved_sources'],['U'])
if __name__=='__main__':unittest.main()
