# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

For behavioral/coding guidelines (think-before-coding, simplicity, surgical changes, goal-driven execution), see the `karpathy-guidelines` skill — it's the source of truth, don't duplicate it here.

## Project Status

Greenfield project — no pipeline, site, or distribution code exists yet. The full product vision, architecture, tech stack, repository structure, article schema, phased roadmap, and hard rules live in [Readme.md](Readme.md); read it first and keep it as the source of truth rather than duplicating it here.

## Intended Architecture (summary)

One monorepo, no planned split into separate repos:

- **`pipeline/`** — Python 3.11+, run on a GitHub Actions cron. Fetch (RSS/HN/GitHub trending/arXiv/etc.) → dedupe → LLM summarize → LLM rank → publish, writing markdown to `content/`.
- **`site/`** — Next.js (App Router), reads `content/`, renders Essential/Latest/category/post pages, hosted on Vercel.
- **`distribution/`** — Phase 4: draft generators (LinkedIn/Instagram/YouTube script) only, human-reviewed, no auto-posting.

See `Readme.md` for the full architecture diagram and details.

## Working in This Repo

No build, lint, or test commands exist yet because nothing has been scaffolded.

- Do not assume standard Next.js or Python tooling/structure are already in place — verify what actually exists first.
- Once real commands (pipeline run, dev server, build, lint, test) are established, update this file with the exact commands rather than generic framework defaults.
- Follow `Readme.md`'s phased roadmap — Phase 1 (pipeline MVP) is next; don't jump ahead to the site or distribution phases.
