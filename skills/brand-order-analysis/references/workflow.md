# Brand Order Analysis Workflow

## Purpose

Use this workflow to build a brand ordering-system overview. The output should combine store population, geographic distribution, all-source ordering-system adoption, GMB-only ordering-system adoption, and store-level evidence into a dashboard-ready dataset or static HTML report.

## Intake

Clarify or infer these inputs:

- brand name
- target market and geography
- official store locator, official store API, or user-provided store source
- known official ordering sites, ordering APIs, or provider domains
- target output: dataset, HTML report, GitHub Pages site, CSV, or all of these
- geography requirement, with Taiwan defaulting to ?? -> region group -> city/county
- whether the user wants a current live audit or an update from existing `data/` files

If the user does not provide sources, search for official brand sources first. Treat third-party directories as supporting evidence, not as the store population source, unless the user explicitly asks for a market-wide discovery exercise.

## Source Priority

Use public sources in this order:

1. official brand store locator or official store API
2. official online ordering site or official ordering API
3. official store pages with embedded Google Maps links
4. Google search results and Google Maps pages
5. GMB / Google Business Profile ordering links or buttons, when accessible
6. marketplace or aggregator pages such as foodpanda, Uber Eats, DoorDash, GrabFood, Nidin, or local equivalents
7. LINE, messaging, reservation, or ordering short links
8. user-supplied manual evidence

Record evidence URLs and source types. Do not collapse official, Google, GMB, and third-party claims into one opaque provider list.

## Execution Steps

1. Build the official store population and deduplicate stores.
2. Normalize store identity and geography: store ID, store name, address, phone, city/county, district, and region group.
3. For Taiwan, assign every store to one of ??, ??, ??, ??, ?? when possible.
4. Add `sourceCoverage` for each store:
   - `officialListed`
   - `gmbFound`
   - `googleFound`
   - `thirdPartyFound`
5. Add public source URLs, including official source URL, official store URL, Google/GMB URL, and provider evidence URLs.
6. Audit ordering systems from all available sources.
7. Add each ordering-system claim to `orderingSystems` with:
   - `system`
   - `sourceType`
   - `orderMode`
   - `evidenceUrl`
   - `confidence`
8. Compute per-store booleans:
   - `hasAnyOrderingSystem`
   - `hasGmbOrderingSystem`
9. Compute GMB status fields:
   - `gmbStatus`
   - `gmbOrderingStatus`
   - `manualReviewReason` when blocked, ambiguous, or unresolved
10. Generate `data/stores.json`, `data/summary.json`, and CSV if useful.
11. Build the dashboard HTML only after the dataset and summary formulas are stable.

## Adoption and Counting Rules

Use official store count as the denominator for adoption rates.

- Overall adoption rate = stores where `hasAnyOrderingSystem` is true / official store count.
- GMB adoption rate = stores where `hasGmbOrderingSystem` is true / official store count. In Google Order audits, this means stores where the blue Google Order entry is confirmed, even if provider names are still pending.
- GMB coverage gap = stores where GMB was not found, Google was blocked or timed out, matches were ambiguous, or the blue Google Order entry could not be confirmed after human-paced re-check. Stores with `button_confirmed_provider_pending` are not gaps.
- GMB coverage gaps are not non-adoption. Keep them separate from stores confirmed to have no ordering system.
- Provider counts count a system once per store, even if multiple evidence URLs mention it.

## Google Order Re-Check Protocol

Use this protocol whenever GMB / Google ordering coverage matters.

1. First pass: open the known GMB / Maps URL or the strongest Google result and look for a blue Google Order entry.
2. If no entry is found by a quick pass, do not finalize `no_gmb_order_button`. Run a human-paced re-check before deciding:
   - use a persistent browser profile when possible
   - use Taiwan locale and local timezone for Taiwan brands
   - open the page normally instead of jumping directly to hidden dynamic URLs
   - wait for render, move the pointer, scroll, pause, then inspect visible buttons
   - click one-button online order flows or separate pickup and delivery buttons when present
   - button visibility alone is not a provider signal; after clicking, wait for the Google Order panel/searchviewer flow and read only that panel
   - pickup/delivery visibility alone is not mode evidence; count a mode only if its control can be selected or is already active
   - parse provider names only from visible rows inside the Google Order dialog/panel, not from the background Google result page or knowledge panel
3. For stores that are `button_confirmed_provider_pending`, blocked, timed out, or otherwise unresolved, run bounded multi-attempt re-checks before finalizing:
   - default to at least 3 attempts per store when time permits
   - try the Google Search business card for the store name and address first, then the stored Google Order panel URL and known GMB/Maps URL
   - prefer the Google Search business card for unresolved stores because it may expose blue pickup/delivery buttons while the Maps place page only shows a website row
   - retry both one-button and two-button flows because Google may expose pickup and delivery differently by store
   - click visible controls again on each attempt; do not treat stale button text from the full page as a completed provider check
   - if a stored Google Order panel URL exists, re-open it and re-check active pickup/delivery modes before relying on older mode claims
   - use short natural waits between attempts to reduce transient panel failures
   - if a persistent browser profile is blocked or stale, retry the unresolved stores in a fresh browser profile/session before finalizing
   - stop immediately when provider names are visible in the Google Order panel
   - never run an infinite loop; if fresh repeated attempts see no blue order entry, set `no_gmb_order_button`; if attempts are blocked or unstable, keep the store pending or blocked with `manualReviewReason`
4. Record entry coverage separately from provider evidence:
   - blue order entry confirmed, providers unreadable: `button_confirmed_provider_pending`, `hasGmbOrderingSystem: true`
   - provider names visible in the order panel and the mode is active/clickable: add `sourceType: gmb` claims by mode
   - blocked, timeout, bot-check, or page instability: `unavailable_or_blocked`, manual review
   - human-paced re-check completed and no blue order entry is visible: `no_gmb_order_button`
5. Do not parse provider names from the whole Google results page as GMB providers. Page text can include official Nidin results, marketplace snippets, ads, or knowledge-panel links that are not the opened Google Order panel.
6. Treat `nidin.shop` or `order.nidin.shop` as `Nidin` only when it is a visible provider row inside the opened Google Order panel. Do not count official Nidin links, organic results, or Maps website rows as GMB evidence.
7. Preserve prior confirmed GMB provider claims when a later re-check is blocked.
8. Store retry evidence in `gmbSignals`: `buttonDetected`, `providersParsed`, `attemptCount`, `maxAttempts`, `attemptHistory`, `panelUrl`, `checkedAt`, `checkMethod`, and notes. Use this in the HTML details table so "pending" stores show why they are pending and how many attempts were made.
## Provider Interpretation

- `all-source ordering systems`: all confirmed ordering systems from official, Google, GMB, third-party, marketplace, LINE, or local platform evidence.
- `GMB ordering systems`: only systems where `sourceType` is `gmb`.
- A claim may use `sourceType: gmb` only if it was observed inside the Google Business Profile blue online-order button flow. The button may appear as one `????` button or as separate `????` and `????` buttons. Open the button, read the pickup or delivery panel, then record only the providers visible there. Official Nidin links, marketplace URLs, embedded Maps links, Google search snippets, or known provider pages must remain `official`, `marketplace`, `third_party`, or `google`; never backfill them as GMB.
- A Google Order panel row labelled `nidin.shop` / `order.nidin.shop` is a valid `Nidin` GMB provider row. The same domain outside the opened panel is not valid GMB evidence.
- `orderMode` may include `pickup`, `delivery`, `dine_in`, `reservation`, or `unknown`.
- Put messaging, loyalty, menu-only, or reservation links in ordering evidence only when they support ordering or the user asks to track them.
- Keep official ordering providers separate from marketplace providers through `sourceType`.

## Manual Review

Do not guess for:

- GMB pages hidden behind dynamic buttons or scripts
- GMB blue online-order buttons that cannot be opened or whose pickup/delivery panel cannot be read
- Google bot-check or `sorry` pages during re-checks; preserve prior confirmed blue-button evidence when available and note the block
- stores with multiple possible Google Maps matches
- closed, moved, duplicate, or temporarily closed stores
- mall counters, hospital stores, campus stores, airports, venue stores, or restricted-access stores
- stores absent from official ordering APIs
- provider pages blocked by region gates, app-only pages, bot protection, or login

Keep these stores in the dataset and mark `manualReviewReason`.

## HTML Dashboard Structure

Use a high-level dashboard layout. The first viewport should be the actual report, not a landing page.

### 1. Brand Store Overview

Answer: how many stores exist and where are they distributed?

Include:

- official store count
- GMB-found store count
- Google-found store count
- third-party-found store count
- verification gap count
- Taiwan map with 22 city/county counts when market is Taiwan
- region filter: ??, ??, ??, ??, ??, ??
- city ranking chart

### 2. All-Source Ordering Overview

Answer: which ordering systems does the brand use overall?

Include:

- any ordering-system store count
- overall adoption rate
- unknown or needs-review count
- main ordering-system count
- all-source system ranking chart
- region-by-system adoption matrix
- city table with store count, ordering-system count, adoption rate, and main systems

### 3. GMB Ordering Overview

Answer: which ordering systems appear on GMB and where are GMB gaps?

Include:

- GMB-found store count
- GMB ordering-system store count
- GMB adoption rate
- GMB coverage gap count
- GMB-only system ranking chart
- GMB region coverage matrix
- clear note that GMB gaps are unknown/coverage gaps, not proof of no ordering system

### 4. All-Source vs GMB Comparison

Answer: does GMB underrepresent any ordering systems?

Include a table with:

- system name
- all-source store count
- all-source adoption rate
- GMB store count
- GMB adoption rate
- count gap
- percentage-point gap

### 5. Store Details

Include a searchable, filterable table with:

- store name
- city/county
- region group
- address
- official source
- GMB status
- all-source ordering systems
- GMB ordering systems
- evidence links
- review status or manual review reason

Filters should include:

- ?? / region group / city
- system
- source type
- GMB status
- manual-review status

## Static Site Checklist

For a static report site:

- Keep `index.html`, `styles.css`, `app.js`, and `data/` at the project root unless the repo already has another structure.
- Keep the report usable from GitHub Pages without a server.
- Use one active geography filter state to update KPI cards, map, charts, comparison table, and store details.
- Keep all-source and GMB-only charts visually separate.
- Ensure evidence links remain reachable from store details.
- On mobile, avoid horizontal scrolling in the map and KPI areas.

## Publishing Checklist

Before publishing:

- Generated JSON files parse.
- `officialStoreCount` equals the number of store records.
- Overall adoption rate uses official store count as denominator.
- GMB adoption rate uses official store count as denominator.
- GMB gaps are counted separately from confirmed non-adoption.
- City counts sum to official store count.
- Region counts sum to official store count, with ?? separate for Taiwan.
- Evidence links are present for confirmed ordering-system claims when public evidence exists.

