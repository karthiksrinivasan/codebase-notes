# Notes Generation Rules

Rules for how exploration notes should be created and maintained.

Notes are stored centrally at `~/.claude/repo_notes/<repo_id>/notes/`.

## Structure

- **Hierarchical folders** — each topic gets a folder with `index.md` + children. Nest deeper as subtopics are explored.
- **`00-overview.md`** is the root. It links to all top-level topic folders and tracks exploration status.
- **`index.md`** in each folder serves as the topic overview and links to all children.
- **Naming**: folders use `topic-name/`, files use `subtopic.md` (no numeric prefix). Use the optional `order:` frontmatter field if explicit ordering is needed.
- **Centralized storage**: all notes live under `~/.claude/repo_notes/<repo_id>/notes/`. Do not store notes inside the repository itself.

- **Research directory**: `research/` holds notes on external resources — papers, articles, blog posts, competitive analysis. Organized by topic and sub-topic, separate from code exploration notes.

Example tree:

```
~/.claude/repo_notes/<repo_id>/
  notes/
    00-overview.md
    auth/
      index.md
      oauth-flow.md
      session-management.md
    data-pipeline/
      index.md
      ingestion.md
      transformations.md
  research/
    index.md
    topic-name/
      index.md
      paper-or-article.md
      another-paper.md
    another-topic/
      index.md
      sub-group/
        index.md
        paper.md
  commits/
  projects/
```

## Cross-References and Navigation

Use **wikilinks** for all cross-references between notes. Obsidian resolves these automatically and builds the graph view and backlinks panel — no manual navigation bars needed.

```markdown
[[index|Parent Topic]]
[[oauth-flow|OAuth Flow]]
[[session-management]]
```

- Use `[[target-file|Display Label]]` when the file name differs from the desired label
- Use `[[target-file]]` when the file name is the label
- Obsidian's backlinks panel and graph view replace manual navigation bars — do not add `> **Navigation:**` or `> **Sub-topics:**` blockquotes

## Frontmatter

Every note should include YAML frontmatter with at minimum:

```yaml
---
tags:
  - auth
  - jwt
aliases:
  - JWT Auth
  - Token Authentication
git_tracked_paths:
  - path: src/auth/
    commit: a1b2c3d
last_updated: 2026-03-18
---
```

- **`tags:`** — topic tags for Obsidian tag search and filtering
- **`aliases:`** — alternate names Obsidian uses for wikilink resolution
- **`git_tracked_paths:`** — links the note to the source code it documents (see Git Freshness Tracking)
- **`order:`** — optional integer for explicit ordering within a folder (e.g., `order: 2`)

Use **Dataview queries** for dynamic tables that aggregate data across notes:

````markdown
```dataview
TABLE last_updated, tags FROM "notes/auth"
SORT last_updated DESC
```
````

## Capture Matrix

Every note should be written through one or more of these lenses. Each lens asks a different follow-up question after "What is X?". Notes that only answer "What?" without any follow-up lens produce shallow, unhelpful documentation.

### What + Why (Architecture Decisions)

Capture the reasoning behind architectural choices: why this approach over alternatives, what constraints drove the decision, what trade-offs were accepted.

**Good:**
> The auth service uses JWT with short-lived access tokens (15 min) and long-lived refresh tokens (30 days). This avoids per-request database lookups for token validation while still allowing revocation within 15 minutes. Alternative considered: opaque tokens with Redis lookup — rejected because it added a Redis dependency to every service.

**Bad:**
> The auth service uses JWT tokens. Access tokens expire after 15 minutes and refresh tokens expire after 30 days.

The bad example states facts without explaining *why* those values were chosen or what alternatives existed.

### What + How (Implementation Patterns)

Capture the non-obvious implementation pattern: how something actually works under the hood when reading the code alone would be confusing or time-consuming.

**Good:**
> Retry logic uses exponential backoff with jitter. The base delay doubles each attempt (1s, 2s, 4s, 8s) up to a 30s cap, then adds random jitter of 0-25% to prevent thundering herd. The `RetryPolicy` class wraps any async callable and is applied via decorator `@with_retry(max_attempts=5)`.

**Bad:**
> The system retries failed requests. It uses the `RetryPolicy` class with exponential backoff.

The bad example names the class but does not explain the actual behavior, cap, jitter, or how to apply it.

### What + Where (Data Flow)

Capture how data moves through the system: entry points, transformations, storage destinations, and exit points.

**Good:**
> User upload flow: file arrives at `POST /api/uploads` -> validated in `UploadHandler` (size, type, virus scan) -> stored to S3 via `StorageService.put()` -> metadata row inserted in `uploads` table -> async job queued on `file-processing` SQS queue -> worker resizes images and extracts text -> results written to `upload_artifacts` table -> webhook fires to notify caller.

**Bad:**
> Files are uploaded through the API and stored in S3. A background job processes them.

The bad example omits the intermediate steps, the queue, the database tables, and the webhook — the details that actually help someone debug or extend the flow.

### What + When (Configuration)

Capture environment variables, config files, feature flags, and — critically — *when* each setting should be changed and what effect the change has.

**Good:**
> | Variable | Default | When to Change | Effect |
> |---|---|---|---|
> | `MAX_POOL_SIZE` | 10 | Under high DB load; increase to 25 for >1k RPS | More concurrent DB connections; watch for DB connection limits |
> | `CACHE_TTL_SECS` | 300 | When stale reads cause user-visible bugs | Lower = fresher data but more DB hits |
> | `FEATURE_NEW_UI` | false | After QA sign-off on the redesign | Enables new dashboard for all users |

**Bad:**
> The application uses these environment variables: `MAX_POOL_SIZE` (default 10), `CACHE_TTL_SECS` (default 300), `FEATURE_NEW_UI` (default false).

The bad example lists variables and defaults but gives no guidance on when or why to change them.

### What + Who (Integration Points)

Capture how this system connects to external systems: what it calls, what calls it, authentication methods, failure modes, and ownership boundaries.

**Good:**
> The billing service integrates with Stripe via their v2 API. Auth uses a restricted API key stored in `STRIPE_SECRET_KEY` (rotated quarterly by the platform team). On payment failure, Stripe sends a webhook to `POST /webhooks/stripe` — the handler retries charge 3x over 72 hours, then marks the subscription as `past_due`. The platform team owns the Stripe account; billing team owns the webhook handler.

**Bad:**
> The billing service uses the Stripe API for payments. Webhooks handle payment events.

The bad example omits auth details, failure behavior, retry logic, and ownership — the things someone needs when debugging a production payment issue.

### What + What-If (Error Handling)

Capture failure modes, error propagation, recovery strategies, and what operators should do when things go wrong.

**Good:**
> If Redis is unreachable, the session middleware falls back to in-memory sessions with a 5-minute TTL and emits a `redis.fallback` metric. This means: (1) sessions are not shared across pods — sticky sessions required, (2) a Redis outage lasting >5 min causes all users to re-authenticate. Alert threshold: `redis.fallback` count > 0 for 2 consecutive minutes. Recovery: once Redis is back, new sessions automatically use it; existing in-memory sessions expire naturally.

**Bad:**
> The system handles Redis failures gracefully with a fallback mechanism.

The bad example says "gracefully" without explaining what the fallback does, what it costs, or how to respond.

### What + When (Lifecycle/Deployment)

Capture processes, triggers, schedules, and deployment mechanics — distinct from static configuration.

**Good:**
> Database migrations run automatically during deploy via the `migrate` init container, which executes before the app container starts. Migrations are sequential (files named `V001__create_users.sql`). Rollback: there is no automatic rollback — failed migrations halt the deploy and require manual intervention via `flyway repair`. Schema changes that break backward compatibility must be split across two deploys: (1) add new column with default, (2) remove old column after all pods are on new code.

**Bad:**
> Database migrations are run during deployment. The system uses Flyway for migration management.

The bad example names the tool but omits the mechanism, ordering, failure behavior, and the critical two-phase migration strategy.

### What + Constraints (Schemas / Models)

Capture data shapes, validation rules, invariants, and the relationships between models — not just field lists.

**Good:**
> The `Order` model enforces these invariants:
>
> | Field | Type | Constraint | Why |
> |---|---|---|---|
> | `status` | enum | `created -> paid -> shipped -> delivered` | Transitions are one-directional; no skipping steps |
> | `total_cents` | int | Must equal sum of `line_items.price_cents * quantity` | Denormalized for query speed; recomputed on line item change |
> | `customer_id` | FK | Must reference active customer | Prevents orders for deactivated accounts |
>
> The `status` transition is enforced in `Order.transition_to()` — direct field assignment raises `InvalidTransitionError`.

**Bad:**
> The Order model has fields: id (int), status (string), total_cents (int), customer_id (int), created_at (datetime).

The bad example is a field list. It says nothing about invariants, transitions, or why the fields exist.

## Applying Multiple Capture Rules in One Note

Most notes benefit from combining several lenses. Here is an example note that uses four capture types together:

```markdown
# Transformation Engine

The transformation engine converts raw event payloads into normalized records
stored in the analytics warehouse.

## Architecture Decision (What + Why)

The engine uses a pull-based model: workers poll SQS rather than receiving
pushed messages. This was chosen over SNS fan-out because (1) individual
transforms vary wildly in cost (10ms to 30s), and (2) pull-based allows
per-worker concurrency control via `MAX_INFLIGHT` without a separate
rate-limiter.

## Data Flow (What + Where)

Raw event lands in `raw_events` SQS queue -> worker calls
`TransformRouter.route(event)` to select the correct transformer ->
transformer outputs a `NormalizedRecord` -> record is batch-written to
the `analytics.events` table every 500 records or 10 seconds (whichever
comes first) via `BatchWriter`.

## Configuration (What + When)

| Variable | Default | When to Change |
|---|---|---|
| `MAX_INFLIGHT` | 5 | If transforms are I/O-bound, increase to 15 |
| `BATCH_SIZE` | 500 | Lower to 100 for debugging; never above 1000 (DynamoDB limit) |
| `BATCH_TIMEOUT_SECS` | 10 | Lower in latency-sensitive environments |

## Error Handling (What + What-If)

If a transform raises an unhandled exception, the message is sent to
`raw_events_dlq` after 3 delivery attempts. Alert: `dlq.message.count > 0`.
Operator action: inspect the DLQ message, fix the transformer, then replay
via `python manage.py replay_dlq --message-id <id>` after fixing the root cause.
```

## Content Rules

- **Lead with "What is it?"** — one-paragraph summary at the top of every note.
- **Prefer tables over prose** for structured data (config fields, API endpoints, database schemas, status codes, comparisons).
- **Code snippets** — use sparingly. Only for schemas, key data structures, or non-obvious patterns. Never paste entire files.
- **No filler** — no "In this section we will..." intros. Get to the point.
- **Architecture diagrams** — use Excalidraw (see Diagrams section). **Never use ASCII art** for architecture, data flow, or state machine diagrams. ASCII art is only acceptable for directory tree listings.
- **Text fallback for diagrams** — every diagram must have a written description below it that conveys the same information. Readers with broken images should still understand the architecture.
- **Key Files table** — end each note with a table mapping files to their purpose.

## Anti-Patterns

These are common mistakes that produce low-value notes. Each includes a bad example and the fix.

### 1. Vague labeling without insight

**Bad:**
> This module handles authentication and authorization.

**Fix:**
> The auth module validates JWTs on every request via `AuthMiddleware`, checks role-based permissions against the `permissions` table, and issues new token pairs through `POST /auth/refresh`. It does NOT handle user registration (that is in the `accounts` service).

### 2. Listing files without saying what is interesting

**Bad:**
> Key files: `handler.py`, `service.py`, `models.py`, `utils.py`, `config.py`

**Fix:**
> | File | What is interesting |
> |---|---|
> | `handler.py` | Routes requests but also contains the rate-limit decorator — easy to miss |
> | `service.py` | The `process()` method has a hidden retry loop (L45-60) that masks transient errors |
> | `models.py` | `Order.total_cents` is denormalized; recomputed in `recalculate_total()` on every line-item change |

### 3. Describing config without saying when to change

**Bad:**
> `WORKER_COUNT` controls the number of worker threads (default: 4).

**Fix:**
> `WORKER_COUNT` (default: 4) — increase to 8-16 for CPU-bound workloads on machines with 8+ cores. Keep at 4 or lower for I/O-bound tasks to avoid thread contention. Monitor `worker.idle_pct`; if consistently >50%, reduce count.

### 4. Architecture diagrams that are just labeled boxes

**Bad:**
> A diagram showing "Frontend", "Backend", "Database" as three boxes with arrows.

**Fix:**
> Show what travels along each arrow (HTTP/JSON, gRPC/protobuf, SQL), what triggers the flow (user click, cron job, webhook), and where failures are caught. Label the arrows, not just the boxes.

### 5. "See code for details"

**Bad:**
> The retry logic is complex. See `retry.py` for details.

**Fix:**
> Retries use exponential backoff: 1s, 2s, 4s up to 30s cap, with 0-25% jitter. Non-retryable errors (4xx) are excluded via `is_retryable()`. After max attempts, the error propagates to the caller wrapped in `MaxRetriesExceeded`. See `retry.py:RetryPolicy` for the implementation.

### 6. Prose where a table would be clearer

**Bad:**
> The API returns 200 for success, 400 for bad input, 401 for missing auth, 403 for insufficient permissions, 404 when the resource does not exist, and 429 when the rate limit is exceeded.

**Fix:**
> | Status | Meaning | Common Cause |
> |---|---|---|
> | 200 | Success | — |
> | 400 | Bad input | Missing required field, invalid enum value |
> | 401 | Missing auth | Expired or missing JWT |
> | 403 | Forbidden | User lacks required role |
> | 404 | Not found | Deleted resource or wrong ID format |
> | 429 | Rate limited | >100 req/min per API key |

### 7. Copying docstrings verbatim

**Bad:**
> `process_event(event: Event) -> Result`: Processes an event and returns a Result.

**Fix:**
> `process_event()` is the main entry point for the worker loop. It deserializes the SQS message, routes to the correct handler based on `event.type`, and wraps the result in a `Result` that includes timing metrics. It is NOT idempotent — duplicate delivery causes duplicate processing (tracked in issue #1234).

## Diagrams (Excalidraw)

Notes should include Excalidraw diagrams where visual representation adds clarity beyond what text provides.

### Content-Type to Diagram-Style Mapping

| Content Type | Diagram Style | When to Use |
|---|---|---|
| Architecture overview | Component diagram with labeled connections | Showing system boundaries and communication protocols |
| Data flow | Left-to-right flow with transformation steps | Tracing data from input to storage |
| State machines | State nodes with labeled transitions | Documenting status fields or workflow stages |
| Request lifecycle | Vertical sequence diagram | Showing order of operations across services |
| Schema relationships | Entity-relationship diagram | Mapping foreign keys and model associations |
| Deployment topology | Infrastructure diagram with environments | Showing where services run and how they connect |
| Decision trees | Branching flowchart | Documenting conditional logic or routing rules |
| Timeline / lifecycle | Horizontal timeline with milestones | Showing deployment phases, migration steps, or event ordering |

### File Format

- Store `.excalidraw` files alongside the note they belong to
- Naming: `<topic>-<diagram-type>.excalidraw` (e.g., `auth-architecture.excalidraw`, `auth-dataflow.excalidraw`)
- Embed in markdown using wikilink syntax: `![[auth-architecture.png]]`
- The Excalidraw plugin auto-exports PNGs alongside `.excalidraw` files; embed the PNG — no manual render script needed
- Multiple diagrams per note are encouraged when covering distinct concepts

### Style Rules

- `roughness: 0` (clean lines), `fontFamily: 3` (monospace), `opacity: 100`
- Diagrams must **argue visually** — show relationships and flow, not just labeled boxes
- Use shape variety: fan-out, convergence, timelines, cycles
- Clear flow direction: left-to-right or top-to-bottom
- Hero element (most important component) gets the most whitespace
- Label arrows with what travels along them (protocol, data format, trigger)

## Git Freshness Tracking

Every note MUST include YAML frontmatter linking it to the source code it documents:

```yaml
---
tags:
  - auth
git_tracked_paths:
  - path: src/auth/
    commit: a1b2c3d
  - path: src/middleware/
    commit: f4e5d6c
last_updated: 2026-03-18
---
```

- **`path`**: relative path (from repo root) to the source directory this note covers
- **`commit`**: short hash from `git log -1 --format=%h -- <path>` when the note was written or updated
- **`last_updated`**: date the note content was last revised
- Multiple paths per note are supported for notes covering multiple source areas

### Checking Freshness

Run the staleness checker to find notes that may need updating:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale
```

This compares each note's tracked commit against the current HEAD for those paths and reports which notes have fallen behind.

### Updating Rules

When updating a note after source code changes:

1. Re-read the changed source files to understand what changed
2. Update the note content to reflect the changes
3. Update the `commit` hash to the current HEAD for each tracked path
4. Update the `last_updated` date
5. Update any affected diagrams

## Maintenance

- **Update overview**: when exploring a new topic, update `00-overview.md` to link the new folder
- **Update parent links**: when adding a child note, update the parent `index.md` using wikilinks
- **Prefer updates over new notes**: if a note already covers the topic, update it rather than creating a duplicate
- **Delete stale notes**: when information becomes obsolete, remove the note rather than leaving it to mislead
- **Check freshness** periodically to catch notes that have drifted from the source:

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts stale
```

## Research Notes

Research notes capture knowledge from external resources — papers, articles, blog posts, tutorials, competitive analysis. They live in a dedicated `research/` subdirectory.

### Structure

```
research/
├── index.md                        # Research overview — all topics
├── {broad-topic}/
│   ├── index.md                    # Topic overview + paper index table
│   ├── {paper-or-article}.md       # Individual paper/article note
│   ├── {another-paper}.md
│   └── {sub-group}/               # Optional sub-grouping for large topics
│       ├── index.md
│       └── {paper}.md
```

### Grouping Principles

- **Top-level folders**: Broad research domains (e.g., `autonomous-labs/`, `ml-architectures/`)
- **Sub-groups**: When a topic has >5 papers, split by theme (e.g., `hardware-automation/`, `software-orchestration/`)
- **Individual notes**: One per paper, article, or resource

### Research Paper Template

```yaml
---
type: research-paper
tags:
  - research
  - ml
aliases:
  - Paper Short Title
source_url: https://...
relevance: foundational|competitive|adjacent|overview
date_added: YYYY-MM-DD
---
```

| Field | Value |
|-------|-------|
| **Authors** | Names (Affiliations) |
| **Year** | YYYY |
| **Source** | Journal/Blog/Conference |
| **URL** | link |
| **Relevance** | Why this matters to the project |

Required sections:
1. **Core Contribution** — one paragraph on the key insight
2. **Technical Approach** — methods, architecture, algorithms
3. **Key Results** — bullet points of important findings
4. **Project Context** — how this relates to our codebase, what we can learn

### Topic Index Template

Each topic's `index.md` should have:
- `type: research-overview` in frontmatter
- `tags:` and `aliases:` for Obsidian discoverability
- Overview paragraph
- Paper/Article Index table (columns: #, Title, Year, Theme, Relevance)
- Key cross-cutting insights
- Optional Dataview query to list all notes in the folder automatically

### What Makes Good Research Notes

**Good:** Maps findings back to the project — "A-Lab uses robotic powder dispensing; our Mosaic module handles equivalent automation"

**Bad:** Summarizes the paper without connecting to the project — "A-Lab synthesized 41 compounds"

**Good:** Extracts actionable technical details — specific architectures, algorithms, configuration choices

**Bad:** Generic summary that could come from reading the abstract
