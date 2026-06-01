# Brand Order Analysis

Static dashboards and datasets for Taiwan brand ordering-system analyses.

## Site Structure

- `index.html`: brand report selector for GitHub Pages.
- `daming/`: Daming Tea report, data bundle, JSON, and CSV.
- `chage/`: CHAGE report, data bundle, JSON, and CSV.
- `assets/`: shared dashboard frontend assets.
- `scripts/`: collection, rebuild, and Google Order re-check scripts.
- `skills/brand-order-analysis/`: reusable Codex skill copy.

## Report URLs

- Daming: `/daming/`
- CHAGE: `/chage/`

## Current Google Order Rule

Google Order pickup/delivery mode is counted only when the Google Order panel mode is active or clickable and the provider appears as a visible provider row in the opened panel.

Greyed or disabled mode labels, official ordering links, marketplace links, and background Google result text are not counted as Google Order provider evidence. A provider is counted as `sourceType: gmb` only when it appears as a real provider row inside the opened Google Order panel.

For stores stuck in `button_confirmed_provider_pending`, rerun `scripts/human_gmb_order_recheck.py` with `--fresh-profile`. The re-check opens Google Search first to inspect the business-card order buttons, then falls back to stored panel and Maps URLs. If repeated fresh checks find no blue Google Order entry, the store is downgraded to `no_gmb_order_button` instead of preserving a stale pending state.
