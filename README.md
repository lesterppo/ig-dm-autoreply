# IG DM auto-reply

Automatic replies to **authorized contacts only** (usernames kept in the
`IG_TARGETS` secret, never in code) on the owner's Instagram DMs. Replies are
drafted by a free NVIDIA model (`z-ai/glm-5.3-flash`, fallback
`nvidia/nemotron-3-super-120b-a12b`) following a persona prompt: short,
playful, no plans, no personal details. Every message gets a reply — no
escalation, no going quiet. (Note: the popular reasoning models were tested
and rejected — they leak chain-of-thought into the reply text; the GLM flash
model keeps thinking in a separate field.)

## How it works

A cron job on the owner's VM runs `vm_dm_reply.py` every 5 minutes:

1. Checks Instagram DMs via `instagram-messages-cli` (existing auth).
2. Finds messages newer than the stored bookmark (`state.json`) from each
   authorized contact.
3. Drafts one reply per thread via the NVIDIA chat API (free tier).
4. Sends the reply, advances the bookmark.

If both NVIDIA models fail, a generic fallback reply ("Haha 😂") is sent
rather than leaving the message unanswered. Truncated or garbage model
outputs are rejected and retried with the fallback model.

## GitHub Actions (manual only)

The `.github/workflows/dm-autoreply.yml` workflow is kept for **manual runs
only** (`workflow_dispatch`). Its `schedule` trigger is disabled — GitHub's
built-in scheduler was not firing reliably, so the VM cron is the sole
scheduler.

`automation/dm_autoreply.py` is the GitHub Actions version of the script
(uses `instagrapi`). It supports `dry_run` mode: drafts replies but sends
nothing, useful for testing prompt changes before they go live.

## Setup (one time)

For GitHub Actions manual runs, add four secrets under **Settings → Secrets
and variables → Actions**:

| Secret | Value |
|---|---|
| `IG_USERNAME` | Instagram username |
| `IG_PASSWORD` | Instagram password (enter in GitHub UI, never in chat) |
| `NVIDIA_API_KEY` | API key from [build.nvidia.com](https://build.nvidia.com) (free tier) |
| `IG_TARGETS` | Comma-separated Instagram usernames to auto-reply to |

If Instagram has 2FA / login challenges enabled, approve the challenge in the
Instagram app once from a trusted device before the first run.

## Test before ship

1. Go to **Actions → DM auto-reply → Run workflow**.
2. Keep `dry_run: true`. The run logs in with your real account, reads the real
   threads, drafts real replies with the NVIDIA model, but **sends nothing**.
3. Review the step summary: each target shows `init` (first run), `noop`,
   `dryrun`, or `replied`, plus the exact drafted text in the logs.
4. If the drafts sound right, run again with `dry_run: false` to send one real
   batch, then watch the thread.

## Risks (read before shipping)

- This uses unofficial Instagram automation — Instagram ToS violation,
  account warning/ban risk. Datacenter IPs (GitHub runners) get extra
  suspicion; the VM approach with cached auth minimizes fresh logins.
- If Instagram throws a login challenge, runs fail until it's cleared in the
  app — DMs simply go unanswered until then.
- NVIDIA free tier: ~40 req/min, ~1000 req/day — far above what DM threads
  need.
- The model drafts, but the guardrails are prompt-based: review dry-run output
  before going live.
