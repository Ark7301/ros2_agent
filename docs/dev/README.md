# Developer Documentation

- title: Developer Documentation
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, dev, navigation

## Purpose

This section contains material that directly helps contributors set up, run, configure, debug, and verify the repository.

## Sections

- [Onboarding](onboarding/): environment setup and first-run guidance
- [Architecture](architecture/): active implementation architecture and design notes
- [Runbooks](runbooks/): task-oriented operational guides
- [Reference](reference/): stable configuration and API reference
- [Reports](reports/): smoke tests, fix reports, and verification records

## Key Documents

- [Simulation environment setup](onboarding/sim-environment-setup.md)
- [Auto mapping improvement plan](architecture/2026-03-11-auto-mapping-improvement-plan.md)
- [ARIA-centric architecture status](architecture/2026-04-08-aria-centric-architecture-status.md)
- [Embodied demo brain CTO review](architecture/2026-04-08-embodied-demo-brain-cto-review.md)
- [SLAM simulation mapping](runbooks/slam-sim-mapping.md)
- [Scene graph integration testing](runbooks/scene-graph-integration-testing.md)
- [Human-surrogate memory demo](runbooks/human-surrogate-memory-demo.md)
- [API keys reference](reference/api-keys.md)
- [MOSAIC v2 smoke test](reports/2026-04-03-mosaic-v2-smoke-test.md)
- [SLAM mapping fix report](reports/2026-04-03-slam-mapping-fix-report.md)

## Reading Order

1. Read [Simulation environment setup](onboarding/sim-environment-setup.md) to get the environment running.
2. Consult [ARIA-centric architecture status](architecture/2026-04-08-aria-centric-architecture-status.md) for the current system judgment.
3. Read [Embodied demo brain CTO review](architecture/2026-04-08-embodied-demo-brain-cto-review.md) for the management-facing next-stage recommendation.
4. Use [Auto mapping improvement plan](architecture/2026-03-11-auto-mapping-improvement-plan.md) and the process plans under `docs/superpowers/plans/` for execution detail.
5. Use [SLAM simulation mapping](runbooks/slam-sim-mapping.md) and [Scene graph integration testing](runbooks/scene-graph-integration-testing.md) for operational workflows.
6. Use [API keys reference](reference/api-keys.md) and the reports section as supporting reference and verification material.

## Document Status

- `onboarding/`, `architecture/`, `runbooks/`, and `reference/` contain active guidance.
- `reports/` contains historical verification artifacts that remain useful but are tied to specific dates and test runs.

## Related Areas

- Return to the main [Documentation Hub](../README.md).
- Use [Research Documentation](../research/README.md) for design rationale and source material.
- Use [Archive](../archive/README.md) for superseded or historical notes.

## Related Process Assets

- [Knowledge base design spec](../superpowers/specs/2026-04-03-document-knowledge-base-design.md)
- `.kiro/specs/`
