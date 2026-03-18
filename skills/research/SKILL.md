---
name: research
description: Research external topics and create structured notes from papers, articles, blog posts, and web resources. Organized by topic in a dedicated research/ directory with relevance tagging.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent", "WebFetch", "WebSearch"]
---

**Shared context:** Before starting, read `references/shared-context.md` in this plugin's directory for script invocation patterns, note structure rules, and diagram guidelines. All script paths use `<plugin_root>` — resolve it from this skill's location: `skills/research/SKILL.md` → plugin root is `../../`.

# Research Notes

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `TOPIC` | **Yes** | The research topic (e.g., "vector databases", "transformer architectures") |
| `--url URL1 URL2...` | No | One or more URLs to fetch, read, and summarize as research notes |
| `--paper "TITLE"` | No | Search for and summarize a specific paper by title |
| `--category CATEGORY` | No | Categorize as: `foundational`, `competitive`, `adjacent`, `overview`, `best-practices` |
| `--search` | No | Conduct a web search on the topic before creating notes |

**Examples:**
- `/codebase-notes:research "vector databases" --search`
- `/codebase-notes:research "attention mechanisms" --url https://arxiv.org/abs/1706.03762`
- `/codebase-notes:research "competing products" --category competitive --search`

---

You are creating or updating research notes — a curated knowledge base of external resources (papers, articles, web content) organized by topic. Research notes live alongside code notes but in a dedicated `research/` subdirectory.

## Step 0: Resolve Notes Path

**MANDATORY** — always resolve where notes live before doing anything:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts repo-id
```

Research notes live at: `~/.claude/repo_notes/<repo_id>/notes/research/`

Read the research index if it exists:
```
Read ~/.claude/repo_notes/<repo_id>/notes/research/index.md
```

## Step 1: Determine Research Scope

Based on the user's request, identify:
- **Topic** — the broad research area
- **Category** — optional grouping
- **Source** — specific URL, paper, or search query

If `--url` was specified, use WebFetch to retrieve each URL. If `--paper` was specified, search for the paper by title. If `--search` was specified, conduct a web search first. If `--category` was specified, tag the notes accordingly. If none provided, ask the user.

## Step 2: Scaffold Research Directory

If the research directory doesn't exist, create it:

```
research/
├── index.md                    # Research overview — all topics
├── 01-{topic}/
│   ├── index.md               # Topic overview — papers/articles list
│   ├── 01-{paper-or-article}.md
│   └── ...
```

## Step 3: Research and Document

### For a specific paper or article:

Create a note with this structure:

```markdown
---
type: research-paper
source_url: https://...
relevance: foundational|competitive|adjacent|overview
date_added: YYYY-MM-DD
---
# Paper/Article Title

> **Navigation:** Up: [Topic](./index.md) | Prev/Next links

| Field | Value |
|-------|-------|
| **Authors** | Names (Affiliations) |
| **Year** | YYYY |
| **Source** | Journal/Blog/Conference |
| **URL** | link |
| **Relevance** | Why this matters to the project |

## Core Contribution

One paragraph: what is the key insight or finding?

## Technical Approach

How did they do it? Key methods, architecture, algorithms.

## Key Results

Bullet points of the most important findings.

## Project Context

How does this relate to our codebase? What can we learn or apply?

## Key Takeaways

| Takeaway | Applicability |
|----------|--------------|
| Finding 1 | How we could use this |
```

### For broader topic research:

Use web search to find relevant resources, then create multiple paper/article notes under the topic directory.

## Step 3.5: Create Diagrams

Every research note MUST include at least one Excalidraw diagram. Research notes benefit greatly from visual representation — readers grasp technical approaches and comparisons much faster with diagrams.

| Research Content | Diagram Type |
|-----------------|-------------|
| Technical approach / architecture | Architecture diagram showing system components |
| Algorithm or pipeline | Data flow diagram showing processing steps |
| Comparison of approaches | Side-by-side comparison layout with key differences highlighted |
| Concept or mental model | Concept map showing relationships between ideas |
| Multiple papers on same topic | Landscape/positioning diagram showing how papers relate |

For individual paper/article notes, diagram the paper's technical approach or architecture. For topic index notes with multiple papers, create an overview diagram showing the research landscape — how papers/articles relate to each other and to the project.

Build diagrams section-by-section. After creating all `.excalidraw` files:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts render
```

View each rendered PNG with the Read tool to verify quality. Fix and re-render until clean. Embed in the note with `![description](./filename.png)` and always include a text description below that stands alone without the image.

## Step 4: Update Topic Index

The topic's `index.md` should contain a Paper/Article Index table and Key Insights summary.

## Step 5: Update Research Root Index

Update `research/index.md` with the new topic and paper counts.

## Step 6: Rebuild Navigation

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts nav
```

## Step 7: Verify Diagram Coverage

**MANDATORY** — run the diagram verifier after writing research notes:

```bash
export REPO_ROOT=$(git rev-parse --show-toplevel) && cd <plugin_root>/scripts && uv run python -m scripts verify-diagrams
```

If any HIGH or MEDIUM issues are reported, go back and create the missing diagrams. Do not skip this step.

## Grouping Principles

1. **Top-level**: Broad research domain
2. **Sub-group**: Specific theme (when >5 papers)
3. **Individual notes**: One per paper, article, or resource
