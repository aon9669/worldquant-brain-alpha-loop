#!/usr/bin/env python3
import json, subprocess, time, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
cands = json.loads((ROOT / 'candidates_this_run.json').read_text())
start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
end = int(sys.argv[2]) if len(sys.argv) > 2 else len(cands)
detail_path = ROOT / '_sim_batch_detail.json'
if detail_path.exists():
    try:
        detail = json.loads(detail_path.read_text())
    except Exception:
        detail = []
else:
    detail = []
# index by i
by_i = {d['i']: d for d in detail if isinstance(d, dict) and 'i' in d}

for i in range(start, end):
    x = cands[i]
    print(f'=== SIM cand{i} {x["category"]} ===', flush=True)
    (ROOT / f'_expr_cand{i}.txt').write_text(x['expression'])
    cmd = [
        str(WORK / 'venv/bin/python'), str(WORK / 'tool/worldquant_brain_cli.py'),
        '--pretty', 'simulate',
        '--expression-file', str(ROOT / f'_expr_cand{i}.txt'),
        '--region', 'USA', '--universe', 'TOP3000', '--delay', '1',
        '--decay', str(x['decay']),
        '--neutralization', x['neutralization'],
        '--truncation', str(x['truncation']),
        '--pasteurization', 'ON',
        '--nan-handling', 'ON',
    ]
    out = err = ''
    rc = 1
    for att in range(5):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WORK))
        out, err, rc = r.stdout, r.stderr, r.returncode
        (ROOT / f'_sim_cand{i}.json').write_text(out or '')
        (ROOT / f'_sim_cand{i}.err.txt').write_text(err or '')
        blob = (out or '') + (err or '')
        if rc == 0:
            break
        if '429' in blob or 'CONCURRENT' in blob.upper():
            print(f'  retry {att} rate/concurrent', flush=True)
            time.sleep(35)
            continue
        print(f'  fail rc={rc} err={(err or out)[:400]}', flush=True)
        break
    alpha_id = None
    metrics = {}
    data = {}
    try:
        data = json.loads(out) if out.strip() else {}
    except Exception as e:
        data = {'_parse_error': str(e)}
    if isinstance(data, dict):
        alpha_id = data.get('alpha') if isinstance(data.get('alpha'), str) else data.get('id')
        is_ = data.get('is') or {}
        if isinstance(is_, dict):
            metrics = {k: is_.get(k) for k in ('sharpe','fitness','turnover','returns','drawdown','margin','subUniverseSharpe')}
        print(f'  keys={list(data.keys())[:25]} alpha={alpha_id} sharpe={metrics.get("sharpe")}', flush=True)
    rec = {'i': i, 'rc': rc, 'alpha_id': alpha_id, 'metrics': metrics, 'category': x['category']}
    by_i[i] = rec
    detail_path.write_text(json.dumps([by_i[k] for k in sorted(by_i)], indent=2))
    if alpha_id and isinstance(alpha_id, str) and 4 < len(alpha_id) < 24:
        time.sleep(2)
        r2 = subprocess.run([
            str(WORK / 'venv/bin/python'), str(WORK / 'tool/worldquant_brain_cli.py'),
            '--pretty', 'check', '--alpha-id', alpha_id
        ], capture_output=True, text=True, cwd=str(WORK))
        (ROOT / f'_check_cand{i}.json').write_text(r2.stdout or '')
        (ROOT / f'_check_cand{i}.err.txt').write_text(r2.stderr or '')
        r3 = subprocess.run([
            str(WORK / 'venv/bin/python'), str(WORK / 'tool/worldquant_brain_cli.py'),
            '--pretty', 'alpha', '--alpha-id', alpha_id
        ], capture_output=True, text=True, cwd=str(WORK))
        (ROOT / f'alpha_{alpha_id}.json').write_text(r3.stdout or '')
        (ROOT / f'alpha_{alpha_id}.err.txt').write_text(r3.stderr or '')
        print(f'  check/alpha fetched for {alpha_id} check_rc={r2.returncode} alpha_rc={r3.returncode}', flush=True)
    time.sleep(2)
print('DONE', flush=True)
