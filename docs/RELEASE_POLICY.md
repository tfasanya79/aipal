# AiPal release policy

This document defines the minimum release bar for AiPal so product quality and trust improve alongside feature delivery.

## Release gates

Every release must satisfy the following before promotion:

- API tests pass for the affected area.
- Mobile analysis and tests pass for the affected area.
- Critical voice planning journeys pass regression coverage.
- Latency budgets for text and voice turns are within the current threshold.
- Production-like configuration is validated before deployment.

## Quality expectations

- Voice turns should be observable with request IDs and timing metadata.
- Production deployments must not rely on insecure development defaults.
- Release notes must document user-facing changes, known issues, and rollback steps.

## Rollback rule

If a release causes a measurable regression in planning accuracy, wake-word reliability, or turn latency, the release should be rolled back until the issue is resolved.
