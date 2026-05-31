# Brand Order Analysis - Daming Tea

Static dashboard and dataset for the Taiwan store ordering-system analysis of 大茗本位製茶堂.

Current version: `v23 gmb-provider-strict`

## What Is Included

- `index.html`: dashboard entry point
- `app.js`, `styles.css`, `taiwan-map.js`: static frontend assets
- `data/stores.json`: store-level source and ordering-system evidence
- `data/summary.json`: aggregate counts and adoption statistics
- `data/stores.csv`: spreadsheet-friendly export
- `data-inline.js`: inline data bundle for file-based viewing
- `scripts/`: collection and re-check scripts used to build and verify the report

## Current GMB Rule

GMB pickup/delivery mode is counted only when the Google Order panel mode is active or clickable and the provider appears as a visible provider row in the opened panel.

Greyed mode labels, official Nidin/order links, and background Google result text are not counted as GMB provider evidence.
