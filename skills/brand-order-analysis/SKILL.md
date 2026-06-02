---
name: brand-order-analysis
description: Build or update reusable brand ordering-system overview analyses. Use when the user wants to analyze a brand's official store population, Taiwan city or region store distribution, Google Business Profile / Google Maps / GMB store coverage, ordering-system adoption from official sites, Google search, GMB, marketplaces, LINE links, or local ordering platforms, generate stores.json / summary.json / CSV datasets, compare all-source ordering systems against Google Order provider evidence, create Taiwan maps with region and city filters, build an internal dashboard-style HTML report, or publish the analysis as a static site such as GitHub Pages.
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
3. Normalize store name, address, phone, city/county, district, and Taiwan region group when applicable.
4. Capture source coverage for each store:
   - official listed
   - Google search found
   - GMB / Google Maps found
   - third-party or marketplace found
5. Audit ordering systems from all available public sources: official ordering, store pages, Google results, GMB, marketplace pages, LINE/order links, and local ordering platforms.
6. Store each ordering-system claim as structured evidence with `system`, `sourceType`, `orderMode`, `evidenceUrl`, and `confidence`.
7. Compute two separate ordering views:
   - all-source ordering systems
   - Google Order provider evidence
8. Calculate adoption rates using official store count as the denominator.
9. Treat missing or blocked Google Order provider evidence as a coverage gap, not as proof that the store has no ordering system.
10. Generate `data/stores.json`, `data/summary.json`, and optionally `data/stores.csv`.
11. If the user asks for an HTML output, build a dashboard-style report with store overview, all-source ordering overview, Google Order provider overview, comparison table, and store details.
12. For multi-brand static sites, keep the repository root as the brand selector and place each brand report in its own stable slug directory.

## Source Rules

- Prefer official brand sources for store population counts.
- Prefer official ordering sites or APIs for official ordering availability.
- Use Google search, GMB, marketplaces, aggregators, and LINE/order links as evidence sources, and keep their source type explicit.
- Count a provider as `sourceType: gmb` only when it is read from the Google Business Profile blue online-order button flow, such as `線上點餐`, `點餐外帶`, or `點餐外送`, after opening the pickup or delivery panel. Do not infer Google Order providers from official ordering links, marketplace links, embedded Maps links, or search results.
- Preserve evidence URLs for ordering-system claims when possible.
- Do not merge all sources into one untraceable provider list; keep all-source ordering systems and Google Order provider evidence separate.
- Do not infer unavailable dynamic Google Order entries. Mark them as `no_gmb_order_button`, `unavailable_or_blocked`, or `needs_manual_review`. If Google blocks a re-check but prior confirmed blue-button evidence exists, preserve the confirmed evidence and note the block.
- Do not rely only on an official-site Maps link. Official links may open an address page or the wrong GMB profile. When a GMB result does not match the store name/address, search again by brand, store name, and address, then update `gmbUrl` or record the mismatch in `manualReviewReason`.
- Keep uncertain stores in the dataset instead of deleting them.

## Google Order Audit Rule

For Google Business Profile / Google Order, always separate entry coverage from provider evidence.

- Google Order entry coverage means the Google Business Profile or Google result visibly has a blue order entry, including one-button flows such as online order and two-button flows such as pickup and delivery.
- Google Order provider evidence means provider names read only after opening that blue order flow and inspecting the pickup or delivery panel.
- Button text or a visible blue order entry is not enough to parse providers. When a blue order entry is visible, click the visible control, wait for the Google Order panel or searchviewer flow to load, then inspect pickup and delivery separately.
- A pickup or delivery mode counts only when that mode control is clickable/active after selection. Greyed, disabled, or non-switching mode labels are entry context, not mode evidence.
- Provider names count only when they appear as visible provider rows inside the opened Google Order dialog/panel. Do not parse provider names from the surrounding Google result page, knowledge panel, official website snippets, review widgets, or hidden/background text.
- A `nidin.shop` or `order.nidin.shop` row can count as `Nidin` only when it is a visible provider row inside the opened Google Order panel. The same Nidin URL in an official website link, organic Google result, Maps website row, or background page text must not count as Google Order provider evidence.
- Never mark a store as a Google Order gap from a fast DOM check alone. If a quick check finds no button, run a human-paced browser re-check: search Google by brand + store name + address, confirm the matched GMB profile is the actual store, click the blue order entry if present, then inspect the panel.
- Before finalizing `no_gmb_order_button`, classify store context. Street-front stores need an extra fresh-profile re-check because they commonly have marketplace delivery. Mall counters, department stores, hospitals, campuses, airports, transit hubs, staff-only stores, and other restricted-access venues can remain `no_gmb_order_button` after a bounded check if no entry is visible.
- If desktop Google does not show an order entry but user evidence or store context suggests one exists, retry with a mobile viewport/user agent because Google may expose order buttons differently on mobile.
- User-provided screenshots can confirm Google Order entry coverage only when the blue order entry is visibly shown for the correct GMB profile. Unless provider rows are visible in the screenshot, set `button_confirmed_provider_pending` and do not add `sourceType: gmb` provider claims.
- For `button_confirmed_provider_pending`, blocked checks, and suspicious `no_gmb_order_button` street-front stores, run bounded multi-attempt re-checks before finalizing the status. Default to at least 3 attempts per store when time permits, using Taiwan locale/timezone for Taiwan brands, natural pauses, Google Search business-card checks, and known GMB/Maps URLs. Stop early as soon as provider names are confirmed.
- If the persistent browser profile is blocked or stale, retry unresolved pending stores with a fresh browser profile/session. A fresh re-check that repeatedly sees no blue Google Order entry can downgrade stale `button_confirmed_provider_pending` records to `no_gmb_order_button`; blocked or timed-out checks should remain reviewable instead of being treated as no button.
- If the blue Google Order entry is confirmed but providers cannot be safely read, set `gmbOrderingStatus` to `button_confirmed_provider_pending`, set `hasGmbOrderingSystem` to true, and do not add `sourceType: gmb` provider claims.
- If Google blocks, times out, or shows a bot-check page, set `gmbOrderingStatus` to `unavailable_or_blocked` and keep the store in manual review. Do not treat the blocked result as proof that no Google Order entry exists.
- Only create `sourceType: gmb` provider claims after provider names are visible inside the opened Google Order panel and the associated pickup/delivery mode is active. Do not backfill Google Order providers from official links, marketplace links, Google snippets, review widgets, or full-page text outside the panel.
- Store retry metadata in `gmbSignals`, including `buttonDetected`, `providersParsed`, `attemptCount`, `maxAttempts`, `attemptHistory`, `panelUrl`, `checkedAt`, and `checkMethod`, so unresolved stores remain auditable.
## Output Requirements

When producing datasets, include:

- `data/stores.json`: store-level records with source coverage and ordering-system evidence.
- `data/summary.json`: overall counts, region/city counts, all-source system counts, Google Order provider counts, adoption rates, and coverage gaps.
- `data/stores.csv`: spreadsheet-friendly store export when useful.

For GitHub Pages or other reusable multi-brand static sites:

- Use the repository or site root as the brand entry page, such as `/brand-order-analysis/`.
- Put every brand in a sibling slug directory, such as `/brand-order-analysis/daming/`, `/brand-order-analysis/chage/`, and `/brand-order-analysis/<brand-slug>/`.
- Do not nest a new brand under an existing brand directory.
- Do not let the first analyzed brand name become the repository or site base path when the intent is a reusable multi-brand analysis site.
- Keep shared frontend assets in a shared root-level directory when multiple brand reports use the same dashboard code.
- Add or update the root brand selector whenever a new brand report is added.
- Include `brandSlug` and `sitePath` in `summary.json` when publishing a static site so the entry page can link reports without hardcoding internal assumptions.

When producing an HTML report, use a dashboard-first layout:

1. Brand store overview: official store count, GMB-found count, Google-found count, third-party-found count, verification gap, Taiwan map, region filter, and city ranking.
2. All-source ordering overview: any ordering-system count, adoption rate, unknown count, main systems, region matrix, and city table.
3. Google Order provider overview: GMB-found count, Google Order provider count, Google Order provider coverage rate, Google Order provider evidence gap, Google Order provider chart, and region matrix.
4. All-source vs Google Order provider comparison: system name, all-source count/rate, Google Order provider count/rate, and gap.
5. Store details: searchable and filterable table with store, city, region group, address, official source, GMB status, all-source systems, Google Order provider evidence, evidence links, and review status.

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
- Confirm all-source adoption rate equals stores with any ordering system divided by official store count.
- Confirm Google Order provider coverage rate equals stores with `sourceType: gmb` provider evidence divided by official store count.
- Confirm GMB profile missing stores and blocked Google Order checks are counted as coverage gaps, not as non-adoption.
- Confirm `button_confirmed_provider_pending` stores count as Google Order entry coverage, but do not affect `gmbSystemCounts` until panel providers are confirmed.
- Confirm city counts and region counts sum to official store count.
- If an HTML report is built, verify that 全台/region/city filters update KPI cards, map, charts, comparison table, and store details together.

