---
name: brand-order-analysis
description: Build or update reusable brand ordering-system overview analyses. Use when the user wants to analyze a brand's official store population, active store population after excluding permanently closed Google Business Profile / Google Maps stores, Taiwan city or region store distribution, Google Business Profile / Google Maps / GMB store coverage, ordering-system adoption from official sites, Google search, GMB, marketplaces, LINE links, Google Order panel links such as Instagram/LINE/merchant-site links visible after opening the order flow, or local ordering platforms, generate stores.json / summary.json / CSV datasets, compare all-source ordering systems against Google Order provider evidence, create Taiwan maps with region and city filters, build an internal dashboard-style HTML report, or publish the analysis as a static site such as GitHub Pages.
---

# Brand Order Analysis

## Overview

Use this skill to create a brand ordering-system overview. The analysis should show how many stores the brand has, where stores are distributed, which ordering systems are used overall, which providers are visible inside Google Order, and which stores still need manual review.

The core output is a dashboard-ready dataset plus, when requested, an HTML report. The report should answer four questions at a glance:

1. How many stores exist and where are they distributed?
2. Which ordering systems does the brand use overall, and how does adoption vary by region or city?
3. Which providers are visible inside Google Order, and where are Google Order provider evidence gaps?
4. What does each store-level record show, including evidence and verification status?

Read `references/workflow.md` for the full execution and HTML report structure. Read `references/data-model.md` for fields, statuses, adoption-rate rules, Taiwan geography rules, and validation requirements.

## Core Workflow

1. Identify the brand, target market, and target geography.
2. Build the official store population from the most authoritative source, preferably the brand website, official store locator, official API, or user-provided source.
3. Classify active stores before computing the report denominator. Exclude stores that Google Maps/GMB or user-provided evidence clearly marks as permanently closed, closed, or moved unless the user explicitly requests historical coverage.
4. Normalize store name, address, phone, city/county, district, and Taiwan region group when applicable.
5. Capture source coverage for each store:
   - official listed
   - Google search found
   - GMB / Google Maps found
   - third-party or marketplace found
6. Audit ordering systems from all available public sources: official ordering, store pages, Google results, GMB, marketplace pages, LINE/order links, and local ordering platforms.
7. Store each ordering-system claim as structured evidence with `system`, `sourceType`, `orderMode`, `evidenceUrl`, and `confidence`. Store non-provider links visible inside an opened Google Order flow separately in `gmbOrderLinks`.
8. Compute two separate ordering views:
   - all-source ordering systems
   - Google Order provider evidence
9. Calculate adoption rates using active official store count as the denominator.
10. Treat missing or blocked Google Order provider evidence as a coverage gap, not as proof that the store has no ordering system.
11. Generate `data/stores.json`, `data/summary.json`, and optionally `data/stores.csv`.
12. If the user asks for an HTML output, build a dashboard-style report with store overview, all-source ordering overview, Google Order provider overview, comparison table, and store details.
13. For multi-brand static sites, keep the repository root as the brand selector and place each brand report in its own stable slug directory.

## Source Rules

- Prefer official brand sources for store population counts.
- Prefer official ordering sites or APIs for official ordering availability.
- Use Google search, GMB, marketplaces, aggregators, and LINE/order links as evidence sources, and keep their source type explicit.
- Count a provider as `sourceType: gmb` only when it is read from the Google Business Profile blue online-order button flow, such as `線上點餐`, `點餐外帶`, or `點餐外送`, after opening the pickup or delivery panel. Do not infer Google Order providers from official ordering links, marketplace links, embedded Maps links, or search results.
- Preserve evidence URLs for ordering-system claims when possible.
- Do not merge all sources into one untraceable provider list; keep all-source ordering systems and Google Order provider evidence separate.
- Do not infer unavailable dynamic Google Order entries. Mark them as `no_gmb_order_button`, `unavailable_or_blocked`, or `needs_manual_review`. If Google blocks a re-check but prior confirmed blue-button evidence exists, preserve the confirmed evidence and note the block.
- Do not rely only on an official-site Maps link. Official links may open an address page or the wrong GMB profile. When a GMB result does not match the store name/address, search again by brand, store name, and address, then update `gmbUrl` or record the mismatch in `manualReviewReason`.
- Count `sourceCoverage.gmbFound` only after a named Google Business Profile / Maps profile is visible and the profile name is highly similar to the intended store. A Google Maps address-only page, pin, or generic place page is only a lead; click the listed store card or re-search by brand + store name + address before counting GMB coverage or auditing Google Order.
- If no GMB profile is found from the official Maps link or address search, search Google with `brand name + store name` before finalizing `not_found`. If the result is a highly similar named GMB profile and there is no competing duplicate for that store, recognize it as the store's GMB profile, update `gmbUrl`, set `sourceCoverage.gmbFound`, and record the match basis in `gmbSignals`.
- If a matching GMB/Google Maps profile or user-provided screenshot clearly shows permanent closure, closed, or moved status, exclude that store from the active report population and active denominator. Preserve the exclusion in notes or an auxiliary audit trail when useful, but do not leave the closed store in `stores.json`, CSV, KPI cards, map counts, charts, or store details unless the user explicitly asks for historical stores.
- Keep uncertain stores in the dataset instead of deleting them.

## Platform Direct Audit Rule

All-source ordering adoption must include platform-direct checks, not only Google/GMB evidence. If any candidate ordering platform appears for the brand, such as Nidin, QuickClick, LINE ordering, an official ordering portal, foodpanda, Uber Eats, or another local platform, search or open the platform or brand ordering entry directly and attempt to match every official active store by store name, address, phone, or platform store ID. Do not infer chain-wide coverage from one matched store, but do not treat absence from Google Order as absence from the platform. Store platform-direct evidence as `sourceType: official`, `marketplace`, `line`, or `third_party`, and keep it separate from strict `sourceType: gmb` Google Order provider rows.

## Google Order Audit Rule

For Google Business Profile / Google Order, keep these principles in the top-level skill and use `references/workflow.md` for the detailed re-check protocol.

- First verify the correct named GMB profile. Official Maps links and address-only pages are leads, not confirmed profiles.
- If a profile is missing, re-search Google by `brand + store name` and, when useful, `brand + store name + address`; accept a highly similar, non-duplicate GMB result and record why it matched.
- Separate Google Order entry coverage from provider evidence. A blue order button confirms entry only; provider claims require visible provider rows inside the opened panel.
- First successful Google Order panel reads must be mode-aware: inspect pickup and delivery before writing provider evidence.
- Scope provider extraction to the visible Google Order panel/dialog containing the online-order provider list. Do not parse provider names from the background Google results page, Knowledge Panel website row, snippets, ads, or generic `網站` links.
- Treat merchant-site rows such as `ocard.co` as valid Google Order provider evidence only when the row is visible inside the active Google Order pickup/delivery panel; outside that panel they remain all-source evidence.
- For one-button Google Order flows, read the active/pressed/disabled state of the inner `自取` / `運送` controls. Count only the active or successfully selected mode; if the mode cannot be determined, use `unknown` instead of copying providers into both modes.
- Preserve visible post-click order-flow links in `gmbOrderLinks`, but keep strict `gmbSystemCounts` limited to visible provider rows.
- Blocked, timed-out, ambiguous, provider-pending, or no-button checks stay reviewable with `gmbSignals`; do not treat them as no ordering system.
## Output Requirements

When producing datasets, include:

- `data/stores.json`: store-level records with source coverage and ordering-system evidence.
- Include `gmbOrderLinks` in store-level records when Google Order panel links are visible after opening the order flow.
- `data/summary.json`: overall counts, region/city counts, all-source system counts, Google Order provider counts, adoption rates, and coverage gaps.
- `data/stores.csv`: spreadsheet-friendly store export when useful.

For GitHub Pages or other reusable multi-brand static sites:

Fixed HTML output for reusable multi-brand report repositories means each brand must produce a stable sibling directory with `index.html`, `data-inline.js`, `data/stores.json`, `data/summary.json`, and `data/stores.csv`, loading shared root assets such as `../assets/styles.css`, `../assets/taiwan-map.js`, and `../assets/app.js` when they exist. Do not leave a new brand as only a root-level one-off HTML file when the repository already uses shared brand folders such as `chage/` or `toastman/`.


- Use the repository or site root as the brand entry page, such as `/brand-order-analysis/`.
- Put every brand in a sibling slug directory, such as `/brand-order-analysis/daming/`, `/brand-order-analysis/chage/`, and `/brand-order-analysis/<brand-slug>/`.
- Do not nest a new brand under an existing brand directory.
- Do not let the first analyzed brand name become the repository or site base path when the intent is a reusable multi-brand analysis site.
- Keep shared frontend assets in a shared root-level directory when multiple brand reports use the same dashboard code.
- Add or update the root brand selector whenever a new brand report is added.
- Include `brandSlug` and `sitePath` in `summary.json` when publishing a static site so the entry page can link reports without hardcoding internal assumptions.

When producing an HTML report, use a dashboard-first layout:

1. Brand store overview: official store count, GMB-found count, GMB-not-found count, Google-found count, third-party-found count, Taiwan map, region filter, and city ranking. Do not label Google Order pending reviews as GMB coverage gaps.
2. All-source ordering overview: any ordering-system count, adoption rate, unknown count, main systems, region matrix, and city table.
3. Google Order provider/link overview: GMB-found count, Google Order provider count, Google Order provider coverage rate, Google Order pending-review count, Google Order provider/link chart that includes visible `gmbOrderLinks`, and region matrix.
4. All-source vs Google Order provider comparison: system name, all-source count/rate, Google Order provider count/rate, and gap.
5. Store details: searchable and filterable table with store, city, region group, address, official source, GMB status, all-source systems, Google Order provider evidence plus Google Order panel links in the same visible cell, evidence links, and review status.

HTML visual requirements:

- Use a clean product-dashboard style: white cards, soft green-tinted page background, thin borders, subtle shadows, and mobile-first spacing.
- Do not use saturated blue/purple dashboard chrome or decorative AI-style gradients.
- For platform/provider labels, use small logo-like badges rather than full-row colored backgrounds.
- Platform badge and platform progress colors:
  - Nidin: blue `#0098ff`, white text.
  - Uber Eats: black badge with white text; use Uber Eats green `#06c167` for progress bars.
  - foodpanda: pink `#ff2b85`, white text.
  - LINE: LINE Green `#06c755`, white text.
  - QuickClick / 快一點: yellow `#fcb900`, black text.
- Apply platform colors to provider badges, provider progress bars, and provider counts only. Keep row backgrounds, table cells, and chart containers neutral.

## Taiwan Geography Defaults

For Taiwan reports, support all 22 cities/counties and show `0` where the brand has no stores. Use these default region groups:

- `北部`: 基隆市、台北市、新北市、桃園市、新竹市、新竹縣、宜蘭縣
- `中部`: 苗栗縣、台中市、彰化縣、南投縣、雲林縣
- `南部`: 嘉義市、嘉義縣、台南市、高雄市、屏東縣
- `東部`: 花蓮縣、台東縣
- `離島`: 澎湖縣、金門縣、連江縣

The report filter should support 全台 -> region group -> city/county. The same active filter must update KPI cards, map counts, charts, comparison table, and store details.

## Updating This Skill

When updating this skill directly:

- Update this file for trigger wording, top-level workflow, source policy, output requirements, or HTML report structure.
- Update `references/workflow.md` for detailed execution steps, source comparison flow, dashboard sections, and publishing checks.
- Update `references/data-model.md` for schemas, fields, status values, adoption-rate formulas, source coverage, ordering-system evidence, and validation rules.
- Add scripts only when a repeated cross-brand operation becomes stable enough to automate.
- Update `agents/openai.yaml` when the UI display name, short description, or default prompt changes.

After editing, remind the user to restart Codex so the updated skill is reloaded.

## Validation

Before calling the work complete:

- Verify generated JSON files parse successfully.
- Confirm official store count equals the number of store records.
- Confirm permanently closed, closed, or moved stores are excluded from the active store records and denominator unless historical coverage was explicitly requested.
- Confirm all-source adoption rate equals stores with any ordering system divided by official store count.
- Confirm Google Order provider coverage rate equals stores with `sourceType: gmb` provider evidence divided by official store count.
- Confirm GMB profile missing stores and blocked Google Order checks are counted as coverage gaps, not as non-adoption.
- Confirm `button_confirmed_provider_pending` stores count as Google Order entry coverage, but do not affect `gmbSystemCounts` until panel providers are confirmed.
- Confirm `gmbOrderLinks` preserve links visible inside the opened Google Order flow while not changing strict `gmbSystemCounts` unless the link is also a visible provider row.
- Confirm Google Order overview charts or provider/link charts include `gmbOrderLinks` by mode so Instagram/LINE/merchant-site order-flow links appear in the summary, while strict provider-row counts remain separately available.
- Confirm any store-detail Google Order provider/evidence column displays `gmbOrderLinks` by mode.
- Confirm city counts and region counts sum to official store count.
- If an HTML report is built, verify that 全台/region/city filters update KPI cards, map, charts, comparison table, and store details together.

