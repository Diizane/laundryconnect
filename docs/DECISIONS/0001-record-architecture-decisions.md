# ADR 0001: Record architecture decisions

- Status: accepted
- Date: 2026-07-23

## Context

LaundryConnect will be reviewed frequently by another technical overseer, and
the architecture must remain auditable as it grows across a backend, a mobile
app, an admin portal, and multiple provider integrations.

## Decision

Record significant architectural decisions as numbered Architecture Decision
Records in `docs/DECISIONS/`, using this lightweight format (context,
decision, consequences). A decision is "significant" if it constrains future
work, affects security, or would surprise a reviewer.

## Consequences

Reviewers can trace why the system is shaped the way it is. Superseded ADRs
are marked as such rather than deleted.
