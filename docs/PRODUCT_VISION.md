# Product Vision

LaundryConnect is a unified technical knowledge platform for commercial laundry
service technicians.

It is **not** merely a parts finder, a manual library, a document viewer, or a
search box over PDFs. It is the technician's complete workspace for finding and
using information about commercial laundry equipment.

## The problem

Technicians lose significant time because manuals, diagrams, parts information,
wiring diagrams, technical bulletins, service instructions, and maintenance
information are spread across multiple manufacturer and distributor portals —
initially:

- Alliance Laundry Systems
- Girbau
- Richard Jay Service

Each portal has separate credentials, different search systems, slow
interfaces, inconsistent organisation, and large technical manuals that are
difficult to navigate. The most time is wasted:

- finding the correct manual
- finding the correct section inside a large manual
- confirming that a part applies to the exact machine
- locating wiring and diagnostic information
- identifying model or serial-specific documentation
- switching repeatedly between portals

## The principle

Every major feature is evaluated against one question:

> Does this help a technician standing in front of a machine find the correct
> information in as few steps as possible?

Typical technician conditions: on a phone or tablet, standing at a machine,
limited time, possibly poor connectivity, needing correct information fast and
confidence that it applies to the exact machine.

## Source of truth

The official manuals and provider documents remain the source of truth.
LaundryConnect makes them easier to find, navigate, search, reference, and use.
Any future AI assistance must be grounded in retrieved document content, cite
source document and page, and make uncertainty explicit — never a generic
chatbot answering from general model knowledge.

## Scope guardrails

- Parts lookup is one component of the wider machine knowledge workspace, not
  the product.
- Mock, demo, manual, and live provider data must always be clearly labelled.
- No unauthorised scraping or access-control bypasses; respect provider terms.
