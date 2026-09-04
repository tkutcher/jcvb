---
description: Build and deploy the JCVB site — staging by default, prod on request
---

Deploy the JCVB site. Target: $ARGUMENTS (empty means **staging**).

## What to run

```bash
cd ~/TK/github/jcvb && sh scripts/deploy.sh staging     # default
cd ~/TK/github/jcvb && sh scripts/deploy.sh prod        # only when asked for prod/production/live
```

Add `--dry-run` to build and report the file count without touching anything
remote.

## Rules

1. **Staging unless TK says otherwise.** "prod", "production", or "live" in the
   arguments means prod; anything else, including no argument, is staging.
2. Before a **prod** deploy, say what is going out — the pages that changed since
   the last deploy, and anything newly public (a game result, a recap, a stream
   link). Prod is the public site; TK invoking `/deploy prod` is the go-ahead,
   but he should still see the list.
3. Run `uv run --group dev pytest tests/ -q` first. Do not deploy a red suite;
   report the failure instead.
4. Check what the deploy would publish is meant to be public — game pages carry
   only `PUBLIC_STAT_KEYS`, and nothing labelled for an internal audience
   (`jcvb/audience.py`) belongs in `site/content/`.
5. Afterwards, give TK the URL and name anything worth clicking through.

## If the staging container is missing

`deploy.sh staging` fails with the exact `az storage container create` command.
Creating a container and routing `/jcvb-staging` in Anvilor Sites is
infrastructure — show TK the command, let him decide; do not create it unasked.
