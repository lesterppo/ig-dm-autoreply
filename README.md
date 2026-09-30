# IG DM auto-reply

Scheduled auto-replies to **authorized contacts only** (usernames kept in the
`IG_TARGETS` GitHub secret, never in code) on the owner's Instagram DMs. Replies are drafted by a free NVIDIA
model (`z-ai/glm-5.3-flash`, fallback `nvidia/nemotron-3-super-120b-a12b`)
following a strict persona prompt: short, playful, no plans, no personal
details, escalate anything serious. (Note: the popular reasoning models were
tested and rejected — they leak chain-of-thought into the reply text; the
GLM flash model keeps thinking in a separate field.)

## How it works

`automation/dm_autoreply.py` runs on GitHub Actions:

1. Logs in to Instagram via `instagrapi` (session cached between runs; password
   login only when the session expires).
2. Finds the 1:1 thread for each target, lists messages newer than the stored
   bookmark (`automation/state.json`, committed back each run).
3. Drafts one reply per thread via the NVIDIA chat API. If the model returns
   `ESCALATE: <reason>`, nothing is sent and the run summary flags it for review.
4. Sends (or dry-run logs), advances the bookmark.

`concurrency.group: dm-autoreply` guarantees a single writer so two runs can
never double-reply.

## Setup (one time)

Add four secrets under **Settings → Secrets and variables → Actions**:

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
   `dryrun`, `replied`, or `escalated`, plus the exact drafted text in the logs.
4. If the drafts sound right, run again with `dry_run: false` to send one real
   batch, then watch the thread.
5. **Ship:** the `schedule` block in `.github/workflows/dm-autoreply.yml` is
   already live — the job runs every 10 minutes on its own. Nothing else to do.

## Risks (read before shipping)

- This uses `instagrapi`, an **unofficial** library — Instagram ToS violation,
  account warning/ban risk. GitHub runners are datacenter IPs, which Instagram
  treats with extra suspicion (fresh logins are the riskiest moment; the
  session cache exists to minimize them).
- If Instagram throws a login challenge mid-schedule, the run fails loudly
  (exit 2) and waits for you to clear it in the app — DMs simply go unanswered
  until then.
- NVIDIA free tier: ~40 req/min, ~1000 req/day — far above what two DM threads
  need.
- The model drafts, but the guardrails are prompt-based: review dry-run output
  before going live, and keep an eye on the run summaries for `escalated`.
