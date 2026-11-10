# llm-queue (MacBook Air M1)

Shared file queue for headless LLM CLI jobs. Martin (Grok Bot) writes job briefs; the dispatcher runs them, **max 2 at a time** (WorldQuant loop counts as one).

- Dispatcher: `~/llm-queue/dispatcher.py`, launchd **com.aon.llmqueue** (`launchctl list | grep llmqueue`), log `~/llm-queue/logs/dispatcher.log`
- Folders: `inbox/` (waiting) → `running/` → `done/` or `failed/` (`<id>.json` job + `<id>.result.json` result). `heartbeat.json` = dispatcher alive.
- Tools: `claude` (Claude Pro, Sonnet 5.5 for WQ), `agy` (Antigravity, see `agy models`), `codex` (NOT signed in yet: jobs fail with "codex not signed in").
- No network listener. Never put secrets in a prompt. Argon (`~/antigravity-work/argon`) is NOT routed through this queue.

## Submit and read (exact commands)

```bash
# enqueue an Antigravity job, get its id
~/llm-queue/q submit --tool agy --model <model-id-from-agy-models> --prompt "Your brief" --workdir ~/some/dir --timeout 900 --by antigravity-partner
# or with a brief file
~/llm-queue/q submit --tool agy --model <model-id> --prompt-file ~/briefs/job.md --workdir ~/some/dir --by antigravity-partner

# read the result (add --wait to block until finished)
~/llm-queue/q result <id> --wait
# one-shot: submit and wait
~/llm-queue/q submit --tool claude --model claude-sonnet-5-5 --prompt "Reply OK" --wait

~/llm-queue/q status          # dispatcher alive? counts, running jobs
~/llm-queue/q status <id>     # inbox|running|done|failed
~/llm-queue/q cancel <id>
```

Result JSON: `id, tool, model, effort, status (done|failed), exit_code, output_text, usage, error, started_at, finished_at, duration_s` (+ raw `stdout`/`stderr` in the .result.json file).

agy options: `--mode plan|accept-edits|auto` (q flag `--mode`). agy model ids embed effort (e.g. `-high`); do not also pass `--effort` for those.
Job JSON fields (for writing jobs directly): id, tool, model, effort, prompt | prompt_file, workdir, timeout, created_by, optional mode, agy_settings, extra_args, path_prepend. Write to `inbox/.<id>.tmp` then rename to `inbox/<id>.json`.

## WorldQuant loop
`wq_loop/engine.py` submits each generation/refine as an **agy gemini-3.8-flash-high** job (`<ts>-wqag|wqar`), with a `--settings` permission allowlist: read only inside the repo, write only in `wq_loop/cycles/`, the only command allowed is `python3 wq_loop/research.py`. If the agy job fails, times out (840 s), or writes no valid candidates, that cycle falls back to claude-sonnet-5-5 (job `<ts>-wqg|wqr`, or a direct `claude -p` if the queue is down). An agy quota/limit error pauses agy for 30 min (`wq_loop/agy_backoff.json`) and Sonnet runs meanwhile. agy token usage goes to `wq_loop/llm_usage.jsonl`.
Revert to Sonnet only: put `export WQ_LLM_BACKEND=claude` in loop.sh (or edit `LLM_BACKEND` in engine.py). `WQ_LLM_QUEUE=0` forces direct Claude calls.

## Orca
Orca 1.4.255 runs on this Mac (`com.stablyai.orca.serve`, ws://127.0.0.1:6768). Its orchestration commands need an Orca terminal context, so this dispatcher runs the CLIs directly for now; Orca-supervised execution is a later step.
