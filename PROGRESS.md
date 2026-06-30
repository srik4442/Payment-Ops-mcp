# PROGRESS.md

## Day 1 — 2026-06-30
- **Built:** Full project scaffold — SQLAlchemy models (Customer, Order, RefundLog), DB setup, Stripe client wrapper, seed + reset scripts
- **Learned:** stripe_customer_id is the join key between internal DB and Stripe; dual-write seed is what makes the demo work
- **Confused:** Nothing yet — structure is clean

## Day 2 — 2026-06-30
- **Built:** MCP server with 3 read tools: lookup_customer, list_payments, get_order_history; resources + prompts
- **Learned:** All logging must go to stderr — any print() to stdout corrupts the JSON-RPC stream in stdio transport
- **Confused:** —

## Day 3 — 2026-06-30
- **Built:** Write tools: issue_refund (2-step confirm gate + 90-day rule + audit log), create_payment_link, revenue_summary, flag_for_review
- **Learned:** Defense-in-depth safety: confirmed flag + server-side business rule + restricted Stripe key
- **Confused:** —

## Day 4 — 2026-06-30
- **Built:** Full pytest suite with mocked Stripe client, in-memory SQLite, 10+ test cases covering orchestration + business rules
- **Learned:** Mock the Stripe client at the service layer (not at stripe SDK level) for clean, fast tests
- **Confused:** —
