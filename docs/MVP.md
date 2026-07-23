# MVP Definition

The MVP proves the core technician workflow on a strong technical foundation.

## MVP user journey

A technician can:

1. Open LaundryConnect.
2. Search by model number, serial number, part number, fault code, or keyword.
3. Search across configured provider connectors.
4. View grouped and normalised results.
5. Open a machine/model workspace.
6. View relevant information categories.
7. Open official source documents.
8. Search inside supported documents.
9. See the original source, provider, document title, and page reference.
10. Navigate to the relevant section quickly.

## What the MVP does *not* require

- Full automation of every provider (connectors may start with mock or
  manually indexed data — clearly labelled as such).
- Individual technician accounts (internal use, one shared provider account
  per provider initially).
- Full offline mode (but architecture must not preclude it).
- AI answers (but architecture must allow retrieval-augmented generation to be
  added cleanly later).
- Automated part compatibility confirmation.

## Non-negotiables even in MVP

- Provider credentials only on the backend, never in the mobile client.
- One provider failing must not fail the whole search.
- Results retain source, provider, document, and page references.
- Mock data is never presented as live data.

## Current status

Milestone 1 (Foundation) — see [ROADMAP.md](ROADMAP.md). No provider
connectors, search, or mobile app exist yet. Nothing is mocked because nothing
is integrated yet.
