# Documentation Hub

- title: Documentation Hub
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, navigation, knowledge-base

## Structure

- [Developer docs](dev/README.md)
- [Research docs](research/README.md)
- [Archive](archive/README.md)

## Developer docs

- [Onboarding](dev/onboarding/)
- [Architecture](dev/architecture/)
- [Runbooks](dev/runbooks/)
- [Reference](dev/reference/)
- [Reports](dev/reports/)

## Research docs

- [Directions](research/directions/)
- [Surveys](research/surveys/)
- [Papers](research/papers/)
- [Thesis](research/thesis/)
- [References](research/references/)

## Process Assets

- [Design specs](superpowers/specs/)
- [Implementation plans](superpowers/plans/)
- Historical Kiro specs live in `.kiro/specs/`

## Reading Order

1. Start at [Developer docs](dev/README.md) if you need to run, debug, or extend the repository.
2. Go to [Research docs](research/README.md) if you need architectural rationale, surveys, or thesis context.
3. Use [Archive](archive/README.md) only for historical reference.

## Maintenance Rules

- Do not add topic documents directly under `docs/`.
- Update the nearest `README.md` when adding or moving a document.
- Keep developer-facing and research-facing materials in separate trees.
- Move obsolete documents into `docs/archive/` instead of leaving them in place.

## Document Status

- Documents under `docs/dev/` and `docs/research/` are the active knowledge base.
- Documents under `docs/archive/` are preserved for history and should not be treated as current guidance.
