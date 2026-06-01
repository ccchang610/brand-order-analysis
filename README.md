# Brand Order Analysis - Daming Tea

Static dashboard and dataset for the Taiwan store ordering-system analysis of 大茗本位製茶堂.

Current version: `v25 gmb-pending-recheck`

## What Is Included

- `index.html`: dashboard entry point
- `app.js`, `styles.css`, `taiwan-map.js`: static frontend assets
- `data/stores.json`: store-level source and ordering-system evidence
- `data/summary.json`: aggregate counts and adoption statistics
- `data/stores.csv`: spreadsheet-friendly export
- `data-inline.js`: inline data bundle for file-based viewing
- `scripts/`: collection and re-check scripts used to build and verify the report

## Reusable Skills

Installable Codex skill copies live under `skills/`.

- `skills/brand-order-analysis/`: reusable Brand Order Analysis skill for creating brand ordering-system overview datasets and dashboard reports.

## Current GMB Rule

GMB pickup/delivery mode is counted only when the Google Order panel mode is active or clickable and the provider appears as a visible provider row in the opened panel.

Greyed or disabled mode labels, official Nidin/order links, and background Google result text are not counted as GMB provider evidence. Nidin can still be counted if it appears as a real provider row inside the opened Google Order panel.

For stores stuck in `button_confirmed_provider_pending`, rerun `scripts/human_gmb_order_recheck.py` with `--fresh-profile`. The re-check opens Google Search first to inspect the business-card order buttons, then falls back to stored panel and Maps URLs. If repeated fresh checks find no blue Google Order entry, the store is downgraded to `no_gmb_order_button` instead of preserving a stale pending state.
