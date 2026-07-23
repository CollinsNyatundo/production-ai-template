# AGENTS.md — AI Product Studio Agent Guidelines

This file serves as a system-level operational rulebook. Coding assistants and agents working on this project must abide by these rules.

## Core Directives

1. **Strict Monorepo Separation:**
   - Keep `app/` (backend logic) and `frontend/` (Streamlit web client) dependencies separate.
   - Do not cross-import packages from `frontend/` into `app/`, and vice versa.

2. **Data Safety & Git hygiene:**
   - Never commit raw text, CSV, PDF, or binary source files to the git history.
   - Data files must be stored in external buckets. Local development files must be explicitly git-ignored.

3. **Observability Strictness:**
   - Never create custom file-based trace logging mechanisms.
   - Utilize the OpenTelemetry wrapper in `observability/tracer.py` for standard spans.

4. **Async-first standard:**
   - Event loops must not be blocked. Avoid blocking operations (`time.sleep`, synchronous requests) in API routers.
   - Use asynchronous file I/O or `asyncio.to_thread` for blocking system operations.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **production-ai-template** (728 symbols, 1132 relationships, 21 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/production-ai-template/context` | Codebase overview, check index freshness |
| `gitnexus://repo/production-ai-template/clusters` | All functional areas |
| `gitnexus://repo/production-ai-template/processes` | All execution flows |
| `gitnexus://repo/production-ai-template/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
