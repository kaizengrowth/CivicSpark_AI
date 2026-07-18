# Contributing to CivicSpark AI

CivicSpark AI is in active development as an evidence-first civic
platform for Tulsa. Contributions are welcome.

## Ground rules

The project's core commitments (see the
[design notes](https://kaizencode.art/garden/citycamp-ai/)) are not up
for negotiation in PRs:

1. **Search before chat** — every feature must work without the LLM;
   AI layers sit on top of a browsable, linkable evidence layer.
2. **Cite or refuse** — no generated claim ships without a citation to
   a source chunk; numeric figures must appear verbatim in the cited
   source. Refusal is the correct behavior when evidence is missing.
3. **No silent staleness** — anything that fetches external data must
   record success/failure in `scrape_runs` and surface breakage.
4. **Human-gated outreach** — nothing sends email on a user's behalf
   without an explicit human send step.

## Workflow

1. Fork, branch from `main`.
2. `pre-commit install` (ruff, mypy, eslint, bandit, gitleaks).
3. Backend: `pytest tests/backend/` must pass; add fixture-pinned
   tests for any parser changes.
4. Frontend: `npm run lint && npm run type-check && npm test`.
5. Changes to retrieval, generation, or verification should include a
   gold-set run (`python -m app.evals.runner`) and mention scorecard
   deltas in the PR.

## Reporting issues

Wrong answers, stale content, or missing documents are product
signals, not just bugs — please include the query, the answer, and the
expected source document if you have it.

## License

MIT — see the LICENSE file.

**Contact:** kaitlin.cort@owasp.org
