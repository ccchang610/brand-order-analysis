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

Read `references/workflow.md` for the full execution and HTML report structure. Read `references/data-model.md` for fields, statuses, adoption-rate rules, Taiwan geography rules, and validation requirements. For large store-by-store audits that use subagents, also read `references/subagent-batch-protocol.md` before splitting work.

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
14. For large brands, preserve the low-resource batch-reading core: split stores into small batches, checkpoint after every store, and use subagents only for store-level evidence extraction or QA while the main agent owns final merge and report calculations.

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

All-source evidence is the superset view. Google Order provider evidence is a strict subset view. A system found in Google Order should also appear in all-source counts, but a system found from official sites, platform-direct checks, LINE, marketplace pages, Google snippets, or brand-level portals must not be copied into Google Order counts. Re-running a strict Google Order audit must never clear, shrink, or overwrite all-source evidence unless the source itself was proven wrong. Keep the two write paths separate in code and in merge reviews.

## Google Order Audit Rule

For Google Business Profile / Google Order, keep these principles in the top-level skill and use `references/workflow.md` for the detailed re-check protocol.

- Use a low-resource GMB audit profile by default for large brands: headless browser, single-store sequential checks unless explicitly overridden, small batches with per-store checkpointing, temporary browser profiles outside synced workspaces, and conservative request blocking for image/font/media/analytics resources while preserving JS and CSS.
- GMB checks remain required even when platform-direct sources find foodpanda, Uber Eats, Nidin, PB Order, LINE, QuickClick, or another ordering system. Platform-direct evidence may prioritize and seed provider patterns, but it must not be used to skip Google Order/GMB provider-panel review.
- First verify the correct named GMB profile. Official Maps links and address-only pages are leads, not confirmed profiles.
- If a profile is missing, re-search Google by `brand + store name` and, when useful, `brand + store name + address`; accept a highly similar, non-duplicate GMB result and record why it matched.
- Use Google Maps direct search as a GMB identity-resolution aid when Google Search cards are ambiguous, especially for nearby or similarly named stores. Do not treat Maps as a replacement for Google Order provider extraction; provider claims still require rows visible inside the opened Google Order panel/searchviewer flow.
- Separate Google Order entry coverage from provider evidence. A blue order button confirms entry only; provider claims require visible provider rows inside the opened panel.
- First successful Google Order panel reads must be mode-aware: inspect pickup and delivery before writing provider evidence. Record the state of each mode separately and never copy providers from delivery into pickup, from pickup into delivery, or from one store into another.
- Scope provider extraction to the visible Google Order panel/dialog containing the online-order provider list. Do not parse provider names from the background Google results page, Knowledge Panel website row, snippets, ads, or generic `網站` links.
- Provider extraction must be row-scoped. Count a provider only when an actual visible provider row/card inside the opened Google Order panel names that provider for the active mode. Do not count full-panel text, ancestor containers, hidden DOM text, link URLs, provider names from previous stores, or combined containers that mention multiple providers unless each provider has its own visible row/card.
- Treat merchant-site rows such as `ocard.co` as valid Google Order provider evidence only when the row is visible inside the active Google Order pickup/delivery panel; outside that panel they remain all-source evidence.
- For one-button Google Order flows, read the active/pressed/disabled state of the inner mode controls. Treat `自取` and `取貨` as `pickup`; treat `外送` and `運送` as `delivery`. Count only the active or successfully selected mode; if the mode cannot be determined, use `unknown` instead of copying providers into both modes.
- Preserve visible post-click order-flow links in `gmbOrderLinks`, but keep strict `gmbSystemCounts` limited to visible provider rows.
- LINE, Nidin, eathere, QuickClick, Uber Eats, foodpanda, official merchant sites, or any other provider may be Google Order evidence only if it appears as a visible provider row after opening the correct store's blue Google Order flow for the active mode. Known platform presence outside that flow is all-source evidence only.
- Blocked, timed-out, ambiguous, provider-pending, or no-button checks stay reviewable with `gmbSignals`; do not treat them as no ordering system. When possible, classify unresolved checks with a precise `gmbSignals.unresolvedReason`, such as `gmb_profile_found_panel_timeout`, `button_visible_click_failed`, `button_confirmed_provider_pending`, `google_blocked`, `wrong_or_ambiguous_profile`, or `no_gmb_order_button_after_recheck`.
- A weaker later automated result, such as `no_gmb_order_button`, timeout, mobile mismatch, or provider-pending, must not overwrite prior confirmed Google Order provider claims or user-screenshot-confirmed provider rows. Preserve confirmed evidence and mark the re-check as weaker or unreproduced in `gmbSignals`.
- Record mode-read metadata in `gmbSignals.modeReadStates` when possible, for example `{ "pickupProviders": "active_no_provider", "deliveryProviders": "active" }`, so reviewers can tell whether pickup and delivery were actually selected/read. Preferred values are `active`, `active_no_provider`, `disabled`, `not_found`, `blocked`, and `unknown`.
- Preserve short row-level snippets in `gmbSignals.providerRowTexts` when feasible. These snippets are audit evidence for why each strict provider was counted and make it easier to catch false positives caused by parsing the whole panel.
## Subagent-Assisted Batch Rule

Use subagents only where the work is store-level and evidence-shaped. The main agent owns the source of truth: official store population, active denominator, closed-store exclusion, provider canonicalization, final merge, summary formulas, and report output.

- Preserve the existing low-resource GMB pattern: headless by default, Google / Maps / GMB concurrency `1` unless explicitly approved, batches of about 20-30 stores, disposable browser profiles outside synced folders, and checkpointing after every store.
- If the user explicitly approves parallel Google Order work, split stores into independent shards and keep concurrency `1` inside each shard worker. Prefer 4-6 workers only after a small pilot confirms Google is not blocking, CPU is stable, and JSONL checkpointing is append/resumable. Record elapsed time and rows/minute so the team can compare subagent speed against the single-worker baseline.
- Good subagent tasks: platform-direct checks, GMB identity candidates, marketplace / LINE / ordering-link evidence, unresolved-store QA, and fixed-schema evidence extraction.
- Avoid subagent tasks that compute final adoption rates, rewrite `stores.json` directly, decide denominator changes, or run many Google Order panel browsers in parallel.
- Worker output must follow `references/subagent-batch-protocol.md`; validate worker JSONL before merge.
- Strict Google Order provider evidence still requires visible provider rows inside the opened Google Order panel/searchviewer flow. Subagent findings outside that flow remain official, marketplace, third-party, LINE, Google, or manual evidence, not `sourceType: gmb`.
- Workers must write shard JSONL only. They must not edit `stores.json`, `summary.json`, CSV, `data-inline.js`, HTML, shared scripts, or skill files. The main agent performs the only canonical merge and must preserve all-source evidence independently from strict GMB evidence.
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
- Update `references/subagent-batch-protocol.md` when batch/subagent roles, worker output shape, or merge safety rules change.
- Add scripts only when a repeated cross-brand operation becomes stable enough to automate. Batch splitting and worker-output validation are stable cross-brand helpers; automatic merge should stay conservative and review-gated.
- Update `agents/openai.yaml` when the UI display name, short description, or default prompt changes.

After editing, remind the user to restart Codex so the updated skill is reloaded.

## Validation

Before calling the work complete:

- Verify generated JSON files parse successfully.
- Confirm official store count equals the number of store records.
- Confirm permanently closed, closed, or moved stores are excluded from the active store records and denominator unless historical coverage was explicitly requested.
- Confirm all-source adoption rate equals stores with any ordering system divided by official store count.
- Confirm Google Order provider coverage rate equals stores with `sourceType: gmb` provider evidence divided by official store count.
- Confirm `allSourceSystemCounts` is computed from all eligible non-GMB and GMB ordering evidence, while `gmbSystemCounts` is computed only from strict `sourceType: gmb` provider rows. A Google Order rerun must not erase platform-direct all-source evidence such as eathere, LINE, Nidin, QuickClick, official portals, foodpanda, or Uber Eats.
- Confirm GMB profile missing stores and blocked Google Order checks are counted as coverage gaps, not as non-adoption.
- Confirm `button_confirmed_provider_pending` stores count as Google Order entry coverage, but do not affect `gmbSystemCounts` until panel providers are confirmed.
- Confirm `gmbOrderLinks` preserve links visible inside the opened Google Order flow while not changing strict `gmbSystemCounts` unless the link is also a visible provider row.
- Spot-check user screenshots or manual samples against strict GMB rows. If a screenshot shows only foodpanda or only Uber Eats in the opened panel for a mode, remove any other strict GMB providers for that store/mode unless stronger current panel-row evidence exists.
- Confirm pickup and delivery were both attempted when controls exist. Empty pickup is valid only when the pickup state is recorded as `active_no_provider`, `disabled`, `not_found`, `blocked`, or another explicit non-provider state; it is not valid when delivery was the only mode parsed.
- Confirm Google Order overview charts or provider/link charts include `gmbOrderLinks` by mode so Instagram/LINE/merchant-site order-flow links appear in the summary, while strict provider-row counts remain separately available.
- Confirm any store-detail Google Order provider/evidence column displays `gmbOrderLinks` by mode.
- Confirm city counts and region counts sum to official store count.
- If an HTML report is built, verify that 全台/region/city filters update KPI cards, map, charts, comparison table, and store details together.

