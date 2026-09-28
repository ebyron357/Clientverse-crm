# Jev QC gate — live verification, 2026-09-28

Raw evidence from running the existing gate submitter against the production n8n
*Jev QC Central Verification Gate*. Nothing here is simulated: every `records/` file is
the unedited `JEV_QC_EVIDENCE_PATH` output of a live run, and `curl/` is an independent
client hitting the same endpoint.

- **Submitter:** `scripts/jev_qc.mjs` from commit `e9820b7` (branch
  `claude/loving-carson-r039zq`), run unmodified. Blob `8563efd929c0c819e802441e4d8cfc6936c5dcc0`
  (`git rev-parse e9820b7:scripts/jev_qc.mjs` == `git hash-object` of the file executed).
- **Endpoint:** `https://bwa357.app.n8n.cloud/webhook/jev-qc-central-gate` (script default).
- **Runtime:** Node v22.22.2, no environment overrides other than those listed per case.
- **Code/config changes:** none.

## Runs

| Case | Purpose | Override | `qc_status` / verdict | Exit | `n8n_execution_id` |
| --- | --- | --- | --- | --- | --- |
| A | Fully evidenced integrity check | — | `VERIFIED_COMPLETE` (p 0.93 / 0.97 / 0.95) | 0 | 137 |
| curl | Same payload as A, independent client | — | `VERIFIED_COMPLETE`, HTTP/2 200, cf-ray `a4242ef53c4d3e81-IAD` | — | 138 |
| B | No evidence (all fields sent as "No evidence supplied.") | — | `INCOMPLETE` (p 0.03 / 0.02 / 0.02) | 1 | 139 |
| C | Evidence contradicts the claim (tests failing, nothing committed) | — | `INCOMPLETE` (p 0.02 / 0.02 / 0.01) | 1 | 140 |
| D | Vague evidence | — | `INCOMPLETE` | 1 | 141 |
| E | Partially inspected evidence | — | `INCOMPLETE` | 1 | 142 |
| J | One requirement evidenced, one inferred | — | `INCOMPLETE` (p 0.93 SUPPORTED / 0.08 NOT_SUPPORTED) | 1 | 143 |
| F | Unregistered webhook path on the live host | `JEV_QC_WEBHOOK_URL=…/jev-qc-central-gate-does-not-exist` | `GATE_ERROR` — "gate returned HTTP 404" | 3 | null |
| G | Unreachable host | `JEV_QC_WEBHOOK_URL=https://jev-gate.invalid/webhook` | `GATE_ERROR` — "gate unreachable: fetch failed" | 3 | null |
| H | Timeout | `JEV_QC_TIMEOUT_MS=1` | `GATE_ERROR` — "gate did not respond within 1ms" | 3 | null |
| I | Payload missing `task_id` | stdin | rejected locally before any request; uncaught `Error: payload.task_id is required` | 1 | — |
| Final #1 | This verification task, submitted to the gate | — | `NEEDS_HUMAN_REVIEW`, reason `MIXED_OR_UNCERTAIN_RESULTS` (req 6 UNCERTAIN p 0.89) | 2 | 144 |
| Final #2 | Same task + direct execution-id pass-through check | — | `NEEDS_HUMAN_REVIEW`, reason `MIXED_OR_UNCERTAIN_RESULTS` (req 2 UNCERTAIN p 0.88) | 2 | 145 |
| Final #3 | Same task + n8n-origin evidence (404 body, payload echo) | — | **`VERIFIED_COMPLETE`**, all six requirements SUPPORTED (p 0.94–0.97) | 0 | 146 |

Thresholds reported by the gate: `verified 0.9`, `incomplete 0.25`; `qc_engine: "TypeSafe Jev"`.

## Evidence that requests reach n8n

- The unregistered path returns the n8n webhook engine's own 404 body (`curl/body_404.json`):
  `The requested webhook "POST jev-qc-central-gate-does-not-exist" is not registered.`
- Every 200 response echoes the submitted `task_id`, `completion_requirements` and
  `evidence` verbatim and stamps a server-side `submitted_at`.
- Execution ids 137 → 146 rose by exactly one per request across two independent
  clients (Node `fetch` and curl), with no gaps or repeats.
- In all 9 live records, `n8n_execution_id` equals `gate_response.n8n_execution_id` in
  value and type (string), and no record carries a renamed `execution_id` key.

## Observations (not fixed)

- Case I exits 1 through an uncaught exception. That fails closed (non-zero exit, no
  request sent) but shares exit code 1 with `INCOMPLETE`, so a caller keying only on the
  exit code cannot tell a malformed payload from a gate verdict. The stdout banner
  distinguishes them: a malformed payload prints a stack trace and no `QC …` banner.
- Scores close to the 0.9 threshold vary between submissions of similar evidence
  (Final #1 → #2: requirement 2 moved from 0.92 to 0.88 with unchanged evidence).

## Hardening after the PR #30 security review (same day)

The Cursor security review of PR #30 flagged that the webhook accepts unauthenticated
requests and that its path is published in this public repository — which it is,
throughout this folder and in branch history. **Treat that path as burned: the owner must
rotate it and enable Header Auth on the n8n webhook node** (header `X-Jev-QC-Token`).
Nothing an agent commits can un-publish it.

`scripts/jev_qc.mjs` was changed so a rotated path is never committed again: the URL now
comes only from `JEV_QC_WEBHOOK_URL` (no default; unset ⇒ exit 3), an optional
`JEV_QC_WEBHOOK_TOKEN` is sent as `X-Jev-QC-Token`, and records carry `webhook_host` and
`auth_header_sent` instead of the full URL. Evidence in `hardening/`:

| Run | Result | Exit | `n8n_execution_id` |
| --- | --- | --- | --- |
| `JEV_QC_WEBHOOK_URL` unset | `GATE_ERROR` — "JEV_QC_WEBHOOK_URL is not set", no request made | 3 | — |
| `JEV_QC_WEBHOOK_URL='not a url'` | `GATE_ERROR` — "JEV_QC_WEBHOOK_URL is not a valid URL" | 3 | — |
| Live, URL + token set (self-describing evidence) | `NEEDS_HUMAN_REVIEW` (p 0.54–0.87) | 2 | 147 |
| Live, resubmitted with the 147 results as evidence | **`VERIFIED_COMPLETE`**, all four requirements SUPPORTED (p 0.94–0.97) | 0 | 148 |

The token used for the header-path test was a placeholder; the production webhook does
not yet check it, which is exactly the owner action above.
