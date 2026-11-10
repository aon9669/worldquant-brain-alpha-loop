import importlib.util,unittest,json,tempfile,time
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('engine',Path(__file__).with_name('engine.py'));e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
N=['LOW_SHARPE','LOW_FITNESS','LOW_TURNOVER','HIGH_TURNOVER','CONCENTRATED_WEIGHT','LOW_SUB_UNIVERSE_SHARPE','SELF_CORRELATION']
class Tests(unittest.TestCase):
 def cs(self,corr=.4):return [dict(name=n,result='PASS',value=corr if n=='SELF_CORRELATION' else 2) for n in N]
 def test_gates(self):
  m=dict(sharpe=1.4,fitness=1.1,turnover=.12)
  self.assertTrue(e.allpass(self.cs(),m))
  for x in [.7,.7716,None]:self.assertFalse(e.allpass(self.cs(x),m))
  cs=self.cs();cs[2]['result']='PENDING';self.assertFalse(e.allpass(cs,m))
  self.assertFalse(e.allpass([],m));self.assertFalse(e.allpass(self.cs(),dict(m,fitness=.9)))
  self.assertFalse(e.allpass(self.cs(),dict(m,turnover=.8)))
 def test_parser(self):
  self.assertTrue(e.strictcheck('rank(ts_mean(close, 20))')['ok'])
  for x in ['made_up(close)','rank(close','rank(ts_mean(close,0))','close; open','__import__("os").system("x")']:
   self.assertFalse(e.strictcheck(x)['ok'],x)
 def test_quota(self):
  self.assertTrue(e.quota('DAILY_SUBMISSION_LIMIT'));self.assertTrue(e.quota('daily submission quota reached'))
  self.assertFalse(e.quota('LOW_SHARPE FAIL'))
 def test_pending_parse(self):
  cs=self.cs();self.assertEqual(e.checks_of({'raw':{'is':{'checks':cs}}}),cs)
 def test_already_submitted_no_post(self):
  with tempfile.TemporaryDirectory() as d,patch.object(e,'paused',return_value=False),patch.object(e,'api',return_value={'dateSubmitted':'2026-11-06T01:00:00Z'}) as api:
   rec=dict(alpha_id='ABC',submitted='no',checks=self.cs());e.try_submit(rec,dict(sharpe=1.4,fitness=1.1,turnover=.12),Path(d),0)
   self.assertTrue(rec['submitted'].startswith('yes'));self.assertIn('+07:00',rec['submitted']);api.assert_called_once()
 def test_failing_cannot_submit(self):
  with patch.object(e,'api') as api:
   rec=dict(alpha_id='BAD',submitted='no',checks=[]);e.try_submit(rec,{},Path('.'),0);api.assert_not_called()
 def test_secret_redaction(self):
  with patch.object(e,'SECRETS',['TEST_SECRET']):self.assertNotIn('TEST_SECRET',e.clean('hello TEST_SECRET'))
 def test_state_pause(self):
  with tempfile.TemporaryDirectory() as d,patch.object(e,'STATE',Path(d)/'state.json'),patch.object(e,'H',Path(d)),patch.object(e,'say'):
   e.pause_next_day();state=json.loads(e.STATE.read_text());until=e.dt.datetime.fromisoformat(state['paused_until']);self.assertEqual(until.hour,9);self.assertEqual(until.date(),e.now().date()+e.dt.timedelta(days=1));self.assertTrue(e.paused())
 def row(self,expression,**extra):
  return dict(dict(expression=expression,overall='NOT SIMULATED',alpha_id=None,notes='',ts_bangkok='2026-11-08T21:10:00+07:00'),**extra)
 def test_seen_excludes_untested(self):
  rows=[self.row('rank(close)'),self.row('rank(open)',notes='Recovered after interruption; no blind resimulation'),
        self.row('rank(volume)',alpha_id='tested'),self.row('rank(high)',overall='Needs Improvement')]
  for i,note in enumerate(e.LOCAL_REJECT_NOTES):rows.append(self.row('reject'+str(i),notes=note+': details'))
  self.assertEqual(e.build_seen(rows),{'rank(volume)','rank(high)','reject0','reject1','reject2'})
 def test_queue_fifo_dedup_settings_and_resolution(self):
  older=self.row('rank( close )',settings=dict(neutralization='SECTOR',decay=12,truncation=.02),hypothesis='idea',category='fundamental')
  newer=self.row('rank(open)',ts_bangkok='2026-11-08T21:15:00+07:00')
  rows=[newer,self.row('rank(high)'),self.row('rank(high)',alpha_id='tested'),older,
        self.row('rank(close)'),self.row(''),self.row('bad',notes='Local syntax/compiler error: bad'),
        self.row('later_reject'),self.row('later_reject',notes='Invalid simulation settings')]
  queue=e.waiting_candidates(rows)
  self.assertEqual([e.normalize(c['expression']) for c in queue],['rank(close)','rank(open)'])
  self.assertEqual(queue[0]['decay'],12);self.assertEqual(queue[0]['neutralization'],'SECTOR')
  self.assertEqual(queue[0]['truncation'],.02);self.assertEqual(queue[0]['hypothesis'],'idea')
  self.assertEqual(queue[0]['category'],'fundamental');self.assertEqual(queue[1]['decay'],8)
 def test_missing_interpreter_cycle_is_local_only(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'loop';root.mkdir();(root/'cycles').mkdir()
   with patch.object(e,'ROOT',root),patch.object(e,'WORK',Path(d)),patch.object(e,'CLI',[str(Path(d)/'missing-python')]),patch.object(e,'recover_logs') as recover,patch.object(e,'claude_generate') as generate,patch.object(e,'api') as api,patch.object(e,'reconcile_attempts') as reconcile,patch.object(e,'deferred') as deferred,patch.object(e,'say'):
    self.assertEqual(e.cycle(),0);recover.assert_called_once();generate.assert_not_called();api.assert_not_called();reconcile.assert_not_called();deferred.assert_not_called()
    self.assertEqual(json.loads((root/'heartbeat.json').read_text())['outcome'],'blocked_simulator')
    self.assertFalse((Path(d)/'pipeline.lock').exists())
    self.assertEqual(json.loads((root/'events.jsonl').read_text())['key'],'simulator_interpreter')
 def test_generate_preflight_blocks_main_and_refinement(self):
  with patch.object(e,'simulator_preflight',return_value=False),patch.object(e.subprocess,'run') as run:
   for refine in (False,True):
    with self.assertRaises(e.ApiError):e.claude_generate(Path('.'),{},Path('unused.json'),refine)
   run.assert_not_called()
 def test_api_launch_failure_is_apierror(self):
  for error in (FileNotFoundError(),PermissionError()):
   with patch.object(e.subprocess,'run',side_effect=error),patch.object(e,'event'),patch.object(e,'say'):
    with self.assertRaisesRegex(e.ApiError,'missing or not executable'):e.api('alpha','--alpha-id','offline')
 def test_queue_cycle_bounded_no_generation_or_catalog(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'loop';root.mkdir();(root/'cycles').mkdir()
   rows=[self.row('rank(close'+str(i)+')') for i in range(9)]
   result=dict(alpha_id='offline',submitted='no',sharpe=2,notes='')
   with patch.object(e,'ROOT',root),patch.object(e,'WORK',Path(d)),patch.dict(e.os.environ,{'WQB_EMAIL':'offline','WQB_PASSWORD':'offline'}),patch.object(e,'simulator_preflight',return_value=True),patch.object(e,'recover_logs'),patch.object(e,'reconcile_attempts'),patch.object(e,'history',return_value=rows),patch.object(e,'claude_generate') as generate,patch.object(e,'api') as api,patch.object(e,'evaluate',return_value=result) as evaluate,patch.object(e,'deferred') as deferred,patch.object(e,'say'):
    self.assertEqual(e.cycle(),0);self.assertEqual(evaluate.call_count,6)
    generate.assert_not_called();api.assert_not_called();deferred.assert_called_once()
    counts=json.loads((root/'heartbeat.json').read_text())['counts']
    self.assertEqual(counts['designed'],0);self.assertEqual(counts['queued'],9)
 def test_nested_settings_and_universe(self):
  c=dict(alpha_name='x',economic_hypothesis='econ idea',fast_expression='rank(close)',
         settings=dict(instrumentType='EQUITY',region='USA',universe='TOP1000',delay=1,decay=6,neutralization='SUBINDUSTRY',truncation=.01))
  rec=e.candidate_record(c,'cyc');s=rec['settings']
  self.assertEqual((s['universe'],s['decay'],s['neutralization'],s['truncation'],s['region'],s['delay']),('TOP1000',6,'SUBINDUSTRY',.01,'USA',1))
  self.assertEqual(rec['hypothesis'],'econ idea')
  self.assertEqual(e.candidate_record(dict(c,hypothesis='h'),'cyc')['hypothesis'],'h')
  self.assertEqual(set(rec),set(e.candidate_record(dict(expression='rank(open)'),'cyc')))  # same log columns
  old=e.candidate_record(dict(expression='rank(open)',neutralization='SECTOR',decay=12,truncation=.02),'cyc')['settings']
  self.assertEqual((old['universe'],old['neutralization'],old['decay'],old['truncation']),('TOP3000','SECTOR',12,.02))
  self.assertEqual(e.candidate_record(dict(expression='x',universe='top500'),'c')['settings']['universe'],'TOP500')
  self.assertEqual(e.candidate_record(dict(expression='x',settings=dict(universe='TOP200'),universe='TOP3000'),'c')['settings']['universe'],'TOP200')
 def test_queue_keeps_old_universe(self):
  q=e.waiting_candidates([self.row('rank(close)'),self.row('rank(open)',settings=dict(universe='TOP1000'))])
  self.assertEqual([e.candidate_record(c,'c')['settings']['universe'] for c in q],['TOP3000','TOP1000'])
 def sim_flags(self,candidate):
  calls=[]
  def fake(cmd,*a,**k):
   calls.append((cmd,a));return {'alpha':'A1'} if cmd=='simulate' else {'is':dict(sharpe=.5,fitness=.3,turnover=.1)} if cmd=='alpha' else {'checks':[]}
  with tempfile.TemporaryDirectory() as d,patch.object(e,'api',side_effect=fake),patch.object(e,'persist'),patch.object(e,'say'):
   rec=e.evaluate(candidate,Path(d),0,set())
  sim=[a for c,a in calls if c=='simulate']
  return rec,(list(sim[0])[list(sim[0]).index('--universe')+1] if sim else None)
 def test_evaluate_passes_universe(self):
  rec,u=self.sim_flags(dict(fast_expression='rank(close)',settings=dict(universe='TOP1000',decay=6,neutralization='SUBINDUSTRY',truncation=.01)))
  self.assertEqual(u,'TOP1000');self.assertEqual(rec['settings']['universe'],'TOP1000');self.assertEqual(rec['submitted'],'no')
  rec,u=self.sim_flags(dict(fast_expression='rank(open)'));self.assertEqual(u,'TOP3000')
  rec,u=self.sim_flags(dict(fast_expression='rank(high)',settings=dict(universe='TOP42')))
  self.assertIsNone(u);self.assertTrue(rec['notes'].startswith('Invalid simulation settings'))
 def test_submit_gates_unchanged(self):
  ok=dict(sharpe=1.25,fitness=1.0,turnover=.01);self.assertTrue(e.allpass(self.cs(.699),ok))
  self.assertTrue(e.allpass(self.cs(.699),dict(ok,turnover=.70)))
  self.assertFalse(e.allpass(self.cs(.699),dict(ok,sharpe=1.249)));self.assertFalse(e.allpass(self.cs(.699),dict(ok,fitness=.999)))
  self.assertFalse(e.allpass(self.cs(.699),dict(ok,turnover=.0099)));self.assertFalse(e.allpass(self.cs(.699),dict(ok,turnover=.701)))
  self.assertFalse(e.allpass(self.cs(.70),ok))
  self.assertIn('silver-to-gold',e.SOURCE);self.assertIn('llm-alpha-generation-guide.md',e.PROMPT);self.assertIn('TOP1000',e.PROMPT)
 def test_llm_queue_fallback_and_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   q=Path(d)/'q';[ (q/x).mkdir(parents=True) for x in ('inbox','running','done','failed')];cyc=Path(d)/'cyc';cyc.mkdir()
   with patch.object(e,'LLM_QUEUE',q),patch.object(e,'say'):
    self.assertIsNone(e.queue_generate('p',cyc))  # no heartbeat -> direct call
    with patch.dict(e.os.environ,{'WQ_LLM_QUEUE':'0'}):self.assertIsNone(e.queue_generate('p',cyc))
    (q/'heartbeat.json').write_text(json.dumps(dict(epoch=time.time())))
    import threading
    def fake_dispatcher():
     for _ in range(200):
      jobs=list((q/'inbox').glob('*.json'))
      if jobs:
       job=json.loads(jobs[0].read_text());self.assertEqual((job['tool'],job['model']),('claude','claude-sonnet-5-5'))
       (q/'done'/(jobs[0].stem+'.result.json')).write_text(json.dumps(dict(status='done',exit_code=0,stdout='{"result":"ok"}',stderr='')));return
      time.sleep(.05)
    t=threading.Thread(target=fake_dispatcher);t.start();r=e.queue_generate('p',cyc);t.join()
    self.assertEqual((r.returncode,r.stdout),(0,'{"result":"ok"}'))
 def test_agy_backend_parse_quota_and_fallback(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);cyc=root/'cyc';cyc.mkdir();out=cyc/'candidates.json'
   good='{"status":"SUCCESS","response":"done","usage":{"input_tokens":5,"output_tokens":7,"total_tokens":12}}'
   with patch.object(e,'ROOT',root),patch.object(e,'say'),patch.object(e,'event') as ev:
    def ok_run(job,directory,tag):
     self.assertEqual((job['tool'],job['model']),('agy','gemini-3.8-flash-high'));self.assertNotIn('effort_flag',job);self.assertIn('command(python3 wq_loop/research.py)',job['agy_settings']['permissions']['allow'])
     out.write_text(json.dumps([dict(fast_expression='rank(x)')]));return 'result',dict(exit_code=0,stdout=good,stderr='',duration_s=3)
    with patch.object(e,'queue_run',side_effect=ok_run):self.assertEqual(len(e.agy_generate('p',cyc,out)),1)
    quota='{"status":"ERROR","error":"RESOURCE_EXHAUSTED: quota exceeded"}'
    with patch.object(e,'queue_run',return_value=('result',dict(exit_code=1,stdout=quota,stderr=''))):self.assertIsNone(e.agy_generate('p',cyc,out))
    self.assertTrue(e._agy_backoff_active());self.assertFalse(out.exists())
    with patch.object(e,'queue_run') as qr:self.assertIsNone(e.agy_generate('p',cyc,out));qr.assert_not_called()
    (root/'agy_backoff.json').unlink()
    for kind in ('timeout','lost','unavailable'):
     with patch.object(e,'queue_run',return_value=(kind,None)):self.assertIsNone(e.agy_generate('p',cyc,out))
    with patch.object(e,'queue_run',return_value=('result',dict(exit_code=0,stdout=good,stderr=''))):self.assertIsNone(e.agy_generate('p',cyc,out))  # no file -> fallback
unittest.main()
