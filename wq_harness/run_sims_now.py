import json,subprocess,sys,time,concurrent.futures as cf
c=json.load(open('wq_harness/candidates_this_run.json'))
ok=[]
for i,x in enumerate(c):
    r=subprocess.run(['python3','wq_harness/precheck.py',x['expression']],capture_output=True,text=True)
    try: pr=json.loads(r.stdout)
    except Exception: pr={'ok':False,'errors':[r.stdout[:200]+r.stderr[:200]]}
    x['precheck']=pr; print(i,pr.get('ok'),pr.get('errors'),flush=True)
    if pr.get('ok'): ok.append(i)
def sim(i):
    x=c[i]
    cmd=['venv/bin/python','tool/worldquant_brain_cli.py','--pretty','simulate','--expression',x['expression'],'--region','USA','--universe','TOP3000','--delay','1','--decay',str(x['decay']),'--neutralization',x['neutralization'],'--truncation',str(x['truncation']),'--pasteurization','ON']
    for att in range(4):
        r=subprocess.run(cmd,capture_output=True,text=True)
        open(f'wq_harness/sim_run_{i}.out.json','w').write(r.stdout); open(f'wq_harness/sim_run_{i}.err.txt','w').write(r.stderr)
        if r.returncode==0: return i,0
        if '429' in (r.stdout+r.stderr) or 'CONCURRENT' in (r.stdout+r.stderr).upper(): time.sleep(30); continue
        return i,r.returncode
    return i,r.returncode
with cf.ThreadPoolExecutor(2) as ex:
    for i,rc in ex.map(sim,ok): print('sim',i,rc,flush=True)
json.dump(c,open('wq_harness/candidates_this_run.json','w'),indent=1)
