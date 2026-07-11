# Sorteio-Racha — SaaS Readiness Audit

## Executive summary

This is a small, well-written **single-user personal tool** for drawing balanced
pickup-soccer teams — not a multi-tenant SaaS, and it never claims to be
(`DEPLOY.md` calls it "app de uso pessoal"). The code itself is clean: SQL is
fully parameterized, the schema has real constraints, and the balancing logic
carries its own self-tests. The single dominant risk is that **there is no
authentication of any kind on a publicly-deployed app** — anyone who discovers
the Railway URL can read, edit, and delete the entire player database. The
single biggest *feature* gap is that there is no account or tenancy model at
all, so nothing here can become multi-user without that foundation being built
first. Everything else on the checklist is secondary to those two facts.

## Stack & architecture overview

- **Stack:** Python / Flask 3.1 / raw SQLite (no ORM) / gunicorn. Vanilla JS
  frontend (no build step). Deployed on Railway.
- **Tenancy model:** **None.** There is one global `players` / `attendance` /
  `aliases` dataset shared by everyone who hits the app. No `user_id` /
  `org_id` column exists anywhere (`racha_app/models.py:21-37`). This is a
  deliberate single-tenant-per-deploy design, not a broken multi-tenant one.
- **Apparent stage:** Working personal prototype. Two commits, no CI, no tests
  wired into a runner (though `balancing.py`, `parsing.py` carry inline
  `__main__` self-checks — a good sign), no migrations framework. Deploy docs
  are thoughtful and honest about limits.

## Security & architecture findings

| Severity | Area | Finding | Evidence | Recommendation |
|----------|------|---------|----------|----------------|
| **High** | Authentication | No auth on any route. Every API endpoint — including destructive ones — is fully open to anyone with the URL. | `racha_app/app.py` — no `@login_required`, no session, no API key on any of `POST /api/apply-import`, `DELETE /api/players/<id>`, `DELETE /api/aliases/<id>`, `POST /api/sortear`. | If it's on a public URL, put *something* in front: HTTP Basic auth (a `before_request` hook + one env-var password) is ~10 lines and enough for a personal tool. Or restrict the Railway service to private networking. |
| **Medium** | DoS / unbounded compute | `POST /api/parse-list` and `POST /api/sortear` run O(n²) Levenshtein matching and a 500-iteration local-search over every player pair, with no input size cap. A large pasted list or a huge `num_times` ties up the single worker. | `matching.py:14-27` + `app.py:41`; `balancing.py:59-73`; `Procfile` runs `--workers 1`. | Cap input length in `parse_list` and clamp `num_times` to a sane max (e.g. ≤ number of present players) in `api_sortear`. With one worker, one slow request blocks the whole app. |
| **Medium** | CSRF | State-changing routes use `get_json(force=True)`, which ignores Content-Type, so a cross-site form POST can drive them. Currently moot (no auth = nothing to ride), but becomes real the moment auth is added. | `app.py:64-83`, `app.py:143-146` etc. — `force=True` everywhere. | When you add auth, add CSRF protection (or require a custom header / `SameSite` cookie). Drop `force=True` and require `application/json`. |
| **Low** | Debug mode | `app.run(..., debug=True)` would expose the Werkzeug interactive debugger (RCE console) if the app is ever started directly. | `app.py:172`. | Not hit in production (gunicorn runs `app:app`, not `__main__`), so low. Still, gate it: `debug=os.environ.get("FLASK_DEBUG") == "1"`. |
| **Low** | Error detail leak | `api_create_player` returns `str(ex)` straight to the client, exposing raw SQLite error text (e.g. UNIQUE-constraint messages). | `app.py:96-99`. | Return a generic message; log the detail server-side. |
| **Low** | Input validation | `stars` is coerced with `int(...)` but not range-checked in the app layer; the DB `CHECK(stars BETWEEN 1 AND 6)` catches it, but the resulting error surfaces as the raw-500/`str(ex)` above. `grupo` similarly relies solely on the DB CHECK. | `app.py:75`, `app.py:97`; `models.py:25-26`. | Validate at the boundary and return a clean 400. Minor — the DB constraint prevents bad data, it just fails ungracefully. |

**Confirmed handled (worth noting):**
- **SQL injection:** Not present. Every query is parameterized; the only f-string
  in a query (`models.py:95`) interpolates column *names* from a fixed
  code-controlled set, not user input. Good.
- **Secrets:** No secrets in the repo. `.gitignore` correctly excludes
  `racha_app/racha.db` and `.venv/`; the DB path is env-driven (`RACHA_DB`).
  There are no API keys or credentials to leak (no external services).
- **HTTPS:** Terminated by Railway's proxy (not in-repo, so not independently verified).

## Feature gaps for scale

Framing matters here: this app is a personal tool and most SaaS features are
**intentionally out of scope**. The table below is "what you'd need *if* you
decide to turn this into a multi-user product" — not a list of things that are
wrong today. The one that gates all the others is at the top.

| Category | Missing/Incomplete | Impact | Effort |
|----------|--------------------|--------|--------|
| Accounts & tenancy | No user/org model; single global dataset (`models.py`). | Blocks *any* multi-user use — two different groups can't use the same deploy without seeing each other's players. This is the prerequisite for everything else below. | **L** |
| Auth & onboarding | No signup, login, or session. | No self-serve; each "customer" = a separate manual Railway deploy. | M (once tenancy exists) |
| Roles | Everyone who can reach the app has full admin rights. | Fine for personal use; a blocker for shared use. | M |
| Observability | No structured logging or error tracking; a production error is invisible unless you tail Railway logs. | An incident is debugged blind. Add even a `/healthz` + Sentry-equivalent if this grows. | S |
| Backups | SQLite on a Railway volume with no backup/restore routine. | A volume loss = total data loss. `DEPLOY.md` is honest that no-volume = ephemeral, but even *with* a volume there's no backup. | S |
| Persistence at scale | SQLite single-writer, pinned to `--workers 1`. | Documented and correct *for personal scale*. Multi-user = migrate to Postgres before raising worker count. | M |

Out of scope for what this is (noted, not counted as gaps): billing/plans,
invite flows, audit logs, transactional email, background job queue, public
API versioning, in-app notifications.

## Prioritized action plan

### Now (before it sits on a public URL any longer)
1. **Put auth in front of the app.** HTTP Basic via a `before_request` hook +
   one env-var password is enough for a personal tool. This is the only
   genuinely urgent item.
2. **Set up a backup for `racha.db`** if the data matters — even a periodic
   `sqlite3 .backup` copy off the volume. Right now a volume loss is
   unrecoverable.

### Next (cheap hardening, do when convenient)
1. Clamp input sizes on `/api/parse-list` and `num_times` on `/api/sortear`
   (single worker = easy to stall).
2. Gate `debug=True` behind an env var; stop returning `str(ex)` to clients.
3. Add a `/healthz` endpoint and wire minimal error tracking.

### Later (only if you decide to make it multi-user — a real project, not a tweak)
1. Introduce a user/org model and scope every query by it — this is a rewrite
   of `models.py`, not an add-on. Do this *before* Postgres, billing, or
   anything else on the feature-gap list, because they all depend on it.
2. Migrate SQLite → Postgres, then raise gunicorn workers.

## What wasn't assessed

- **Railway infra config** (volume setup, HTTPS/TLS, networking visibility,
  whether the deploy is actually public or private) is not in the repo — the
  "no auth" severity assumes it's publicly reachable. If the service is already
  restricted to private networking, drop that finding to Low. Verify this first.
- **Frontend JS** (`static/*.js`) was not audited for client-side issues; the
  focus was the server and data layer.
- **Dependency CVEs**: Flask 3.1.2 and gunicorn 23.0.0 are current as of this
  audit; not cross-checked against a live advisory feed.
- No load testing was performed — the DoS finding is from reading the
  algorithms' complexity, not measured.
