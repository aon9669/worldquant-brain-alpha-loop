#!/usr/bin/env python3
"""llm-queue dispatcher (com.aon.llmqueue). File queue for headless LLM CLI jobs on this Mac.
inbox/<id>.json -> running/<id>.json -> done|failed/<id>.json + <id>.result.json. Max 2 concurrent jobs.
No network listener. Prompts and outputs stay local. Never forwards WQ/Anthropic secrets to jobs."""
import json, os, signal, subprocess, sys, threading, time, datetime as dt
from pathlib import Path
Q = Path(os.environ.get('LLMQ_HOME', str(Path.home()/'llm-queue')))
MAX_JOBS = int(os.environ.get('LLMQ_CONCURRENCY', '2'))
BIN = Path.home()/'.local/bin'
TOOLS = {'claude': str(BIN/'claude'), 'agy': str(BIN/'agy'), 'codex': str(BIN/'codex')}
STRIP = ('ANTHROPIC_API_KEY', 'WQB_EMAIL', 'WQB_PASSWORD', 'WQB_COOKIE_HEADER', 'CLAUDE_CODE_OAUTH_TOKEN', 'OPENAI_API_KEY', 'GEMINI_API_KEY')
CAP = 400_000
def now(): return dt.datetime.now().astimezone().isoformat(timespec='seconds')
def log(msg):
    with open(Q/'logs'/'dispatcher.log', 'a') as f: f.write(f'{now()} {msg}\n')
def write_json(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp'); tmp.write_text(json.dumps(data, indent=1)); os.replace(tmp, path)

def build_cmd(job, prompt):
    tool, model, effort, extra = job['tool'], job.get('model'), job.get('effort'), list(job.get('extra_args') or [])
    timeout = int(job.get('timeout', 900))
    if tool == 'claude':
        cmd = [TOOLS['claude'], '-p', prompt, '--output-format', 'json', '--no-session-persistence',
               '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
        if model: cmd += ['--model', model]
        if effort: cmd += ['--effort', effort]
    elif tool == 'agy':
        cmd = [TOOLS['agy'], '-p', prompt, '--output-format', 'json', '--disable-slash-commands', '--print-timeout', f'{max(30, timeout-15)}s']
        if model: cmd += ['--model', model]
        if effort: cmd += ['--effort', effort]
        if job.get('mode'): cmd += ['--mode', job['mode']]
        if job.get('agy_settings'): cmd += ['--settings', json.dumps(job['agy_settings'])]
    elif tool == 'codex':
        cmd = [TOOLS['codex'], 'exec', '--json', '--skip-git-repo-check']
        if model: cmd += ['-m', model]
        cmd += [prompt]
    else:
        raise ValueError('unknown tool ' + str(tool))
    return cmd + extra

def output_text(tool, stdout):
    try: parsed = json.loads(stdout)
    except ValueError: return None, None, None
    if not isinstance(parsed, dict): return None, None, parsed
    if tool == 'claude': return parsed.get('result'), parsed.get('usage'), parsed
    if tool == 'agy': return parsed.get('response'), parsed.get('usage'), parsed
    return None, parsed.get('usage'), parsed

def codex_ready():
    try:
        r = subprocess.run([TOOLS['codex'], 'login', 'status'], capture_output=True, text=True, timeout=30)
        return r.returncode == 0 and 'not logged' not in (r.stdout + r.stderr).lower()
    except Exception: return False

def run_job(path):
    jid = path.stem; job = json.loads(path.read_text()); t0 = time.time()
    res = dict(id=jid, tool=job.get('tool'), model=job.get('model'), effort=job.get('effort'), created_by=job.get('created_by'),
               started_at=now(), status='failed', exit_code=None, output_text=None, usage=None, error=None)
    try:
        if job.get('tool') not in TOOLS: raise ValueError('tool must be claude|agy|codex')
        if job['tool'] == 'codex' and not codex_ready(): raise RuntimeError('codex not signed in (run `codex login` on the Mac)')
        prompt = job.get('prompt') or Path(job['prompt_file']).read_text()
        workdir = job.get('workdir') or str(Path.home())
        env = {k: v for k, v in os.environ.items() if k not in STRIP}
        env['PATH'] = ':'.join(list(job.get('path_prepend') or []) + [str(BIN), '/usr/bin', '/bin', '/usr/sbin', '/sbin'])
        cmd = build_cmd(job, prompt); timeout = int(job.get('timeout', 900))
        log(f'start {jid} tool={job["tool"]} model={job.get("model")} cwd={workdir}')
        p = subprocess.Popen(cmd, cwd=workdir, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        holder = {}
        th = threading.Thread(target=lambda: holder.update(zip(('out', 'err'), p.communicate())), daemon=True); th.start()
        while th.is_alive():
            th.join(2)
            cancelled = (Q/'cancel'/jid).exists()
            if time.time() - t0 > timeout or cancelled:
                try: os.killpg(p.pid, signal.SIGTERM); time.sleep(5); os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                th.join(10); res['error'] = 'cancelled' if cancelled else f'timeout after {timeout}s'; break
        out, err = holder.get('out') or '', holder.get('err') or ''
        res.update(exit_code=p.returncode, stdout=out[-CAP:], stderr=err[-CAP:])
        text, usage, parsed = output_text(job['tool'], out)
        res.update(output_text=text, usage=usage)
        if isinstance(parsed, dict) and parsed.get('status') == 'ERROR' and not res['error']: res['error'] = parsed.get('error')
        if isinstance(parsed, dict) and parsed.get('is_error') and not res['error']: res['error'] = 'is_error'
        if p.returncode == 0 and not res['error']: res['status'] = 'done'
        elif not res['error']: res['error'] = f'exit code {p.returncode}'
    except Exception as e:
        res['error'] = f'{type(e).__name__}: {e}'
    res.update(finished_at=now(), duration_s=round(time.time() - t0, 1))
    dest = Q/('done' if res['status'] == 'done' else 'failed')
    write_json(dest/f'{jid}.result.json', res); os.replace(path, dest/f'{jid}.json')
    (Q/'cancel'/jid).unlink(missing_ok=True)
    log(f'finish {jid} status={res["status"]} exit={res["exit_code"]} secs={res["duration_s"]} err={str(res["error"])[:200]}')

def main():
    for d in ('inbox', 'running', 'done', 'failed', 'cancel', 'logs'): (Q/d).mkdir(parents=True, exist_ok=True)
    # Jobs left in running/ by a crash or reboot are failed, never silently re-run.
    for stale in (Q/'running').glob('*.json'):
        write_json(Q/'failed'/f'{stale.stem}.result.json', dict(id=stale.stem, status='failed', error='dispatcher restarted while job was running', finished_at=now()))
        os.replace(stale, Q/'failed'/stale.name)
    log(f'dispatcher up pid={os.getpid()} concurrency={MAX_JOBS}')
    active = {}
    while True:
        for jid, th in list(active.items()):
            if not th.is_alive(): active.pop(jid)
        if len(active) < MAX_JOBS:
            for f in sorted((Q/'inbox').glob('*.json'), key=lambda f: f.stat().st_mtime):
                if len(active) >= MAX_JOBS: break
                dst = Q/'running'/f.name
                try: os.replace(f, dst)
                except FileNotFoundError: continue
                th = threading.Thread(target=run_job, args=(dst,), daemon=True); th.start(); active[f.stem] = th
        write_json(Q/'heartbeat.json', dict(pid=os.getpid(), at=now(), epoch=time.time(), running=sorted(active), concurrency=MAX_JOBS))
        time.sleep(1)

if __name__ == '__main__':
    main()
