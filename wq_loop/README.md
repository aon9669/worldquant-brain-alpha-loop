# WorldQuant box loop
# NOTE: historical notes from the earlier Linux-box version; the current Mac setup is described in the top-level README.md.

Start/restart (from an environment already containing WQB_EMAIL and WQB_PASSWORD):

```bash
bash wq_loop/start.sh
```

No credentials are persisted. Missing inherited credentials cause start.sh to refuse to start. After a box restart the owner must supply the environment again; the supervisor cannot recover credentials from files. Claude runs through `env -u ANTHROPIC_API_KEY HTTPS_PROXY=http://127.0.0.1:8791 claude -p ...` using the existing subscription login. BRAIN credentials are additionally removed from Claude's environment; only the deterministic API controller receives them. Claude has Read/Write/Edit and narrowly allowed Bash access to the offline research/precheck helper, not blanket Bash or submission permission.

`loop.sh` is a detached singleton supervisor (`loop.pid`, kernel flock `supervisor.lock`). Cycles use `pipeline.lock` containing the actual cycle Python PID, and a transition flock. Stale prior pipeline lock files are archived under this folder rather than deleted. A running prior routine cycle is allowed to finish first. New starts are approximately 300 seconds apart; cycles exceeding five minutes run back-to-back. Usage-limit failures back off 30 minutes. Simulations run serially (one slot); explicit rate/concurrency rejection gets exponential backoff, ambiguous timeout POSTs are not blindly repeated.

## Parent integration still needed

Disable the former five-minute Grok Bot routine to avoid duplicate independently scheduled work. This code does NOT modify Grok Bot routines or profile. The local loop itself never sends messages or writes Google Sheets. A lightweight Grok Bot routine every 2–3 hours should:

1. Check heartbeat/process and run start.sh only if needed, with inherited credentials; do not touch agents-keepalive.
2. Read runs_log.jsonl since its durable sync cursor and upsert Alpha Log Runs sheet `<ALPHA_LOG_SHEET_ID>` (sheet is SOR). Use alpha_id when present, otherwise record_key/expression+cycle; don't duplicate recovery/status update records. Null metrics mean unavailable, not zero.
3. Read events.jsonl since its notification cursor. Forward submissions and blockers once. Send one daily summary. The loop records timestamps in Asia/Bangkok (+07:00).
4. Keep the durable cursors outside runs_log.jsonl (e.g. sheet_sync_state.json and report_state.json).

## Files

- engine.py: deterministic generation orchestration, syntax precheck, simulate/check/read-before-submit, strict submit gate and logging.
- research.py: offline category->theme->5–15 real field retrieval and local precheck. API field summary currently contains only IDs, so unavailable descriptions/vector metadata are NOT invented.
- catalog.json: actual BRAIN CLI data-fields response (IDs/metadata only, no credentials).
- cycles/TIMESTAMP/: Claude responses, candidate manifests, syntax results, API simulation/check/alpha results and durable per-alpha journals.
- runs_log.jsonl: EVERY designed alpha, including duplicates/precheck failures/NOT SIMULATED. Updates/deferred submission results may yield later records for an existing alpha_id; sync must upsert.
- events.jsonl: confirmed submissions and deduplicated blockers (same blocker suppressed for the current Bangkok date).
- heartbeat.json: current/latest cycle PID, start/end, counts, outcome.
- submit_attempts.json: durable intent/outcome ledger prevents duplicate POST after an ambiguous failure. Unconfirmed attempts require read-only reconciliation; never clear them blindly.
- ../submit_state.json and ../wq_harness/submit_state.json: compatible daily-quota pause state. Both are honored. A quota rejection sets next-day 09:00 Asia/Bangkok, not same-day 09:00.
- ../wq_harness/memory.jsonl: retained research memory; append-only.

## Submit safety / limitations

Requires every returned check PASS, all seven mandatory gate names present, Sharpe >=1.25, Fitness >=1, turnover 1–70%, and a **numeric** SELF_CORRELATION strictly below .70 in absolute value. A platform PASS exemption above .70 is rejected. PENDING is rechecked once, then skipped. The CLI lacks daily PnL/ACTIVE-list commands: correlation uses BRAIN's own self-correlation check, NOT a separately computed local daily-PnL screen. Missing/unknown correlation is fail-closed. Existing all-PASS unsubmitted memory candidates are rechecked and eligible after quota reset. API submit HTTP success alone is not proof: status/dateSubmitted must confirm before recording submitted=yes and emitting a submission event.

No email/chat/sheet connector credentials, tokens or API keys are installed or persisted. No payment, broker/live trade, repository changes, Orca, Tailscale or watchdog modifications.

Tests: `python3 wq_loop/test_engine.py` (offline, no BRAIN API calls).

## Simulator preflight and waiting queue

Each cycle recovers local journals, then checks that `venv/bin/python` exists and is executable before any CLI/API or generation work. A missing interpreter records a daily-deduplicated blocker and ends cleanly; unexpected CLI launch failures become logged API errors. Never-tested `NOT SIMULATED` expressions are not permanently seen. History supplies a deduplicated, oldest-first queue (preserving candidate settings/hypothesis/category); already simulated or locally rejected expressions are excluded. While waiting work exists, up to six candidates use the existing evaluation/submit gates, both generation calls are skipped, and deferred processing still runs. With no waiting work, the existing generation/refinement flow is unchanged. No authenticated health probe is made.
