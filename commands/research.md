---
description: Conduct and document research on external topics — papers, articles, blog posts, tutorials, and web resources. Research notes are organized by topic and sub-topic under the research/ directory, separate from code exploration notes. Use for competitive analysis, technical deep-dives, literature reviews, or learning about technologies relevant to the project.
argument-hint: "TOPIC [--url URL1 URL2...] [--paper \"TITLE\"] [--category CATEGORY] [--search]"
allowed-tools: ["Read", "Write", "Edit", "Bash(cd ~/.claude/*)", "Bash(uv run*)", "Bash(git *)", "Bash(find *)", "Glob", "Grep", "Agent", "WebFetch", "WebSearch"]
---

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
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts repo-id
```

Research notes live at: `~/.claude/repo_notes/<repo_id>/notes/research/`

Read the research index if it exists:
```
Read ~/.claude/repo_notes/<repo_id>/notes/research/index.md
```

## Step 1: Determine Research Scope

Based on the user's request, identify:
- **Topic** — the broad research area (e.g., "autonomous labs", "transformer architectures", "vector databases")
- **Category** — optional grouping (e.g., "competitive-analysis", "foundational-tech", "best-practices")
- **Source** — specific URL, paper, or search query

If `--url` was specified, use WebFetch to retrieve each URL, then summarize and structure the content. If `--paper` was specified, search for the paper by title and summarize it. If `--search` was specified, conduct a web search on the topic first to find relevant resources. If `--category` was specified, tag the research notes with the given category. If none of these flags are provided, ask the user how they want to proceed.

## Step 2: Scaffold Research Directory

If the research directory doesn't exist, create it:

```
research/
├── index.md                    # Research overview — all topics
├── 01-{topic}/
│   ├── index.md               # Topic overview — papers/articles list
│   ├── 01-{paper-or-article}.md
│   ├── 02-{paper-or-article}.md
│   └── ...
├── 02-{topic}/
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
Map concepts to specific parts of our system.

## Key Takeaways

| Takeaway | Applicability |
|----------|--------------|
| Finding 1 | How we could use this |
| Finding 2 | What this means for our approach |
```

### For a broader topic research:

Use web search to find relevant resources, then create multiple paper/article notes under the topic directory.

### For web-fetched content:

Use WebFetch to retrieve the content, then summarize and structure it into a research note.

## Step 4: Update Topic Index

The topic's `index.md` should contain:

```markdown
---
type: research-overview
---
# Topic Name

> **Navigation:** Up: [Research](../index.md)
> **Sub-topics:** links to papers/articles

## What is it?

One paragraph overview of the research area.

## Paper/Article Index

| # | Title | Year | Theme | Relevance |
|---|-------|------|-------|-----------|
| 1 | Paper Name | 2024 | sub-theme | foundational |
| 2 | Article Name | 2025 | sub-theme | competitive |

## Key Insights

Summary table of the most important cross-cutting insights.
```

## Step 5: Update Research Root Index

Update `research/index.md` with the new topic:

```markdown
---
type: research-overview
---
# Research Knowledge Base

> **Navigation:** Up: [Overview](../00-overview.md)

## Research Areas

| # | Topic | Papers | Relevance |
|---|-------|--------|-----------|
| 1 | Topic A | 4 papers | foundational |
| 2 | Topic B | 3 articles | competitive |
```

## Step 6: Rebuild Navigation

```bash
cd ~/.claude/skills/codebase-notes/scripts && uv run python -m scripts nav
```

## Grouping Principles

Research notes should be grouped and sub-grouped by:

1. **Top-level**: Broad research domain (e.g., "autonomous-labs", "ml-architectures", "testing-strategies")
2. **Sub-group**: Specific theme or approach within the domain
3. **Individual notes**: One per paper, article, or resource

When a topic grows large (>5 papers), consider splitting into sub-groups:

```
research/01-autonomous-labs/
├── index.md
├── 01-hardware-automation/
│   ├── index.md
│   ├── 01-a-lab.md
│   └── 02-a-lab-os.md
└── 02-software-orchestration/
    ├── index.md
    ├── 01-chemos.md
    └── 02-self-driving-labs.md
```
