# Brand Order Analysis Workflow

## Purpose

Use this workflow to build a brand ordering-system overview. The output should combine store population, geographic distribution, all-source ordering-system adoption, Google Order provider evidence coverage, and store-level evidence into a dashboard-ready dataset or static HTML report.

## Intake

Clarify or infer these inputs:

- brand name
- target market and geography
- official store locator, official store API, or user-provided store source
- known official ordering sites, ordering APIs, or provider domains
- target output: dataset, HTML report, GitHub Pages site, CSV, or all of these
- geography requirement, with Taiwan defaulting to 全台 -> region group -> city/county
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

## Platform Direct Audit Protocol

Use this protocol before finalizing all-source adoption counts whenever any ordering platform is requested or discovered.

1. Build a candidate platform list from the user request, official site links, store pages, Google snippets, GMB website rows, known local providers, and prior evidence. For Taiwan beverage and restaurant brands this usually includes Nidin, QuickClick, LINE ordering, foodpanda, Uber Eats, official ordering domains, and brand-specific subdomains.
2. For each candidate platform, find the strongest direct source: official ordering portal, platform brand page, platform API, store locator/search endpoint, LINE OA/order URL, or marketplace chain page.
3. Query that platform directly for the brand and then match against every active official store by normalized store name, address, phone, city/district, or platform store ID.
4. Write confirmed matches as normal `orderingSystems` evidence with `sourceType: official`, `marketplace`, `line`, or `third_party`; use `sourceType: gmb` only for visible provider rows inside Google Order.
5. Write non-matches or blocked platform checks to `platformAudit` / `manualReviewReason` instead of assuming the store has no platform ordering.
6. Do not infer all stores are on a platform from one matched store. Use brand-level portal/API coverage when available, and otherwise mark unverified stores as platform-direct gaps or needs manual review.
7. Only after platform-direct checks and Google Order checks are both represented should the report compare all-source adoption against Google Order provider evidence.

## Execution Steps

1. Build the official store population and deduplicate stores.
2. Classify the active store population before computing the report denominator:
   - exclude stores whose matching Google Maps/GMB profile, official source, or user-provided evidence clearly shows permanent closure, closed, or moved status
   - keep ambiguous, blocked, or unverified stores in active data with review status until closure is confirmed
   - preserve excluded closed-store evidence in notes or an auxiliary audit trail when useful, but do not include excluded stores in `stores.json`, CSV, KPI cards, maps, charts, or store details unless the user asks for historical coverage
3. Normalize active store identity and geography: store ID, store name, address, phone, city/county, district, and region group.
3. For Taiwan, assign every store to one of 北部, 中部, 南部, 東部, 離島 when possible.
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
8. For Google Order checks, open the Google Order panel/searchviewer once per store and classify providers by `pickup` and `delivery` in that first pass whenever the mode controls are available. Write provider claims with mode-specific `orderMode` values immediately instead of creating provider-only claims that require a later mode pass.
9. For Google Order checks, also preserve every visible link inside the opened order flow in `gmbOrderLinks`.
   - Include marketplace, LINE, Instagram, merchant-site, and other links only when they are visible after opening the Google Order button/panel.
   - Keep these links separate from strict provider evidence. Do not count them in `gmbSystemCounts` unless the item is also a visible provider row in the active pickup/delivery panel. For Google Order overview charts that show the user's post-click options, compute a separate provider/link view that includes both strict provider rows and `gmbOrderLinks` by mode.
10. Compute per-store booleans:
   - `hasAnyOrderingSystem`
   - `hasGmbOrderingSystem`
11. Compute GMB/Google Order status fields:
   - `gmbStatus`
   - `gmbOrderingStatus`
   - `manualReviewReason` when blocked, ambiguous, or unresolved
12. Generate `data/stores.json`, `data/summary.json`, and CSV if useful.
13. Build the dashboard HTML only after the dataset and summary formulas are stable.

## Adoption and Counting Rules

Use active official store count as the denominator for adoption rates. Active official store count excludes stores clearly confirmed as permanently closed, closed, or moved unless historical coverage was explicitly requested.

- Overall adoption rate = stores where `hasAnyOrderingSystem` is true / official store count.
- Google Order provider coverage rate = stores with `sourceType: gmb` provider evidence / official store count.
- Google Order provider evidence gap = stores where GMB was not found, Google was blocked or timed out, matches were ambiguous, or the blue Google Order entry/provider panel could not be confirmed after human-paced re-check. Stores with `button_confirmed_provider_pending` are not gaps.
- Google Order provider evidence gaps are not non-adoption. Keep them separate from stores confirmed to have no ordering system.
- Provider counts count a system once per store, even if multiple evidence URLs mention it.
- `gmbOrderLinks` are not strict provider counts. They preserve clicked-flow destinations visible inside Google Order, including social or merchant-site links, and should not change adoption rates by themselves. They should be included in Google Order provider/link summary charts when the chart is meant to show what appears after clicking the Google Order flow.

## Google Order Re-Check Protocol

Use this protocol whenever Google Order provider evidence matters.

1. First pass: open the known GMB / Maps URL or the strongest Google result and look for a blue Google Order entry.
2. If no entry is found by a quick pass, do not finalize `no_gmb_order_button`. Run a human-paced re-check before deciding:
   - use a persistent browser profile when possible
   - use Taiwan locale and local timezone for Taiwan brands
   - use Google Maps direct search as a profile-resolution aid when Google Search cards are ambiguous, but keep provider extraction scoped to the opened Google Order panel/searchviewer flow
   - search Google by brand name, store name, and address before trusting an official Maps link
   - if the official Maps link or address search does not produce a named GMB profile, search Google with `brand name + store name`; when a highly similar named result appears and there is no competing duplicate for that store, recognize it as the GMB profile, update `gmbUrl`, set `sourceCoverage.gmbFound: true`, and record the query/result basis in `gmbSignals`
   - verify the GMB profile name, address, phone, and photos match the intended store; official locator links may resolve to address-only pages or the wrong profile
   - require a highly similar store name before setting `sourceCoverage.gmbFound: true`; a Google Maps address-only page, map pin, or generic place page is not a matching GMB profile
   - when an address-only page shows a "located in this place" / store-card section, click the named store card and audit only that named profile
   - open the page normally instead of jumping directly to hidden dynamic URLs
   - wait for render, move the pointer, scroll, pause, then inspect visible buttons
   - click one-button online order flows or separate pickup and delivery buttons when present
   - button visibility alone is not a provider signal; after clicking, wait for the Google Order panel/searchviewer flow and read only that panel
   - first successful panel/searchviewer open must read pickup and delivery modes in the same pass; click/select `pickup` and `delivery`, parse provider rows per mode, and write `orderMode`, `gmbPickupProviders`, `gmbDeliveryProviders`, and mode-specific `gmbOrderLinks` immediately
   - provider extraction must be scoped to the smallest visible Google Order panel/dialog that contains both the online-order heading and provider-list text such as `選擇下單對象`; ignore background Google Search results, Knowledge Panel website rows, snippets, ads, and generic `網站` links
   - merchant-site rows such as `ocard.co` or `order.ocard.co` are valid Google Order provider rows when they appear inside that scoped panel, including when Google marks them as merchant preferred; the same links outside the panel remain all-source evidence only
   - do not perform a provider-only Google Order sweep and then run a second mode-classification sweep by default; a second pass is only for blocked, timed-out, stale, or mode-control-missing panels
   - pickup/delivery visibility alone is not mode evidence; count a mode only if its control can be selected or is already active/pressed
   - in one-button flows, inspect the inner mode controls after the panel opens; map `自取` and `取貨` to `pickup`, and map `外送` and `運送` to `delivery`; if only delivery is active, write delivery only, and if mode state is unreadable, use `unknown` rather than copying provider rows into both modes
   - parse provider names only from visible rows inside the Google Order dialog/panel, not from the background Google result page or knowledge panel
   - record every visible href/link inside the opened Google Order flow in `gmbOrderLinks`, including Instagram, LINE, marketplace, merchant website, and similar order-flow destinations
3. Before accepting `no_gmb_order_button`, classify the store context:
   - street-front stores should get at least one extra fresh-profile re-check; if still unresolved, also try Google Search business-card and mobile viewport/user-agent checks
   - department-store counters, mall stores, hospital/campus stores, airports, transport hubs, staff-only stores, restricted-access venues, and special production-site stores can remain `no_gmb_order_button` after a bounded check if no blue order entry is visible
   - record the context decision in `manualReviewReason` or `gmbSignals.notes` so the gap is auditable
4. For stores that are `button_confirmed_provider_pending`, blocked, timed out, suspicious street-front `no_gmb_order_button`, or otherwise unresolved, run bounded multi-attempt re-checks before finalizing:
   - for existing brand reports in this repository, use `scripts/recheck_named_gmb_match.py` with `--brand-root`, `--brand-query`, and brand aliases to reject address-only/wrong-name GMB leads before checking Google Order
   - default to at least 3 attempts per store when time permits
   - try the Google Search business card for the store name and address first, then Google Maps direct search or the known GMB/Maps URL for profile disambiguation, then any stored Google Order panel URL
   - prefer the target that exposes the correct named profile and a visible order entry; Google Search business cards may expose blue pickup/delivery buttons while Maps may be better for selecting the correct store among nearby duplicates
   - for stored Google Maps URLs whose visible title is only an address, re-search by brand + store name + address and update `gmbUrl` to the named business profile or Google Search business card before checking buttons
   - if desktop checks disagree with user evidence or store context, retry with a mobile viewport and mobile user agent
   - retry both one-button and two-button flows because Google may expose pickup and delivery differently by store
   - click visible controls again on each attempt; do not treat stale button text from the full page as a completed provider check
   - if a stored Google Order panel URL exists, re-open it and re-check active pickup/delivery modes before relying on older mode claims
   - if a current matching result card has no online-order entry, do not rely on a stale stored `searchviewer` URL; clear stale provider claims and `gmbOrderLinks` unless the current check is blocked and prior evidence is explicitly preserved
   - use short natural waits between attempts to reduce transient panel failures
   - if a persistent browser profile is blocked or stale, retry the unresolved stores in a fresh browser profile/session before finalizing
   - stop immediately when provider names are visible in the Google Order panel
   - never run an infinite loop; if fresh repeated attempts see no blue order entry, set `no_gmb_order_button`; if attempts are blocked or unstable, keep the store pending or blocked with `manualReviewReason`
5. Record entry coverage separately from provider evidence:
   - blue order entry confirmed, providers unreadable: `button_confirmed_provider_pending`, `hasGmbOrderingSystem: true`
   - provider names visible in the order panel and the mode is active/clickable: add `sourceType: gmb` claims by mode
   - links visible in the order panel or searchviewer flow: add `gmbOrderLinks` rows by mode, even when the link is Instagram, LINE, or a merchant site
   - blocked, timeout, bot-check, or page instability: `unavailable_or_blocked`, manual review
   - human-paced re-check completed and no blue order entry is visible: `no_gmb_order_button`
   - no highly similar named GMB profile found: `no_gmb_profile_match`, `sourceCoverage.gmbFound: false`
6. Use user-provided screenshots carefully:
   - if a screenshot shows the correct GMB profile and a visible online-order button, treat entry coverage as confirmed
   - if provider rows are not visible, set `button_confirmed_provider_pending`; do not infer providers from the button or surrounding page
   - if provider rows are visible, record only those visible row providers and preserve the screenshot/source note in `gmbSignals`
7. Do not parse provider names from the whole Google results page as Google Order providers. Page text can include official Nidin results, marketplace snippets, ads, or knowledge-panel links that are not the opened Google Order panel.
8. Treat `nidin.shop` or `order.nidin.shop` as `Nidin` only when it is a visible provider row inside the opened Google Order panel. Do not count official Nidin links, organic results, or Maps website rows as Google Order evidence.
9. Preserve prior confirmed Google Order provider claims when a later re-check is blocked.
10. Store retry evidence in `gmbSignals`: `buttonDetected`, `providersParsed`, `attemptCount`, `maxAttempts`, `attemptHistory`, `panelUrl`, `checkedAt`, `checkMethod`, `unresolvedReason`, and notes. Use this in the HTML details table so "pending" stores show why they are pending and how many attempts were made. Prefer precise unresolved reasons such as `gmb_profile_found_panel_timeout`, `button_visible_click_failed`, `button_confirmed_provider_pending`, `google_blocked`, `wrong_or_ambiguous_profile`, or `no_gmb_order_button_after_recheck`.
11. Store Google Order panel links in `gmbOrderLinks`: `platform`, `kind`, `sourceType: gmb_order_panel`, `orderMode`, `label`, `href`, `panelUrl`, `observedAt`, and `confidence`.
## Provider Interpretation

- `all-source ordering systems`: all confirmed ordering systems from official, Google, GMB, third-party, marketplace, LINE, or local platform evidence.
- `Google Order provider evidence`: only systems where `sourceType` is `gmb`.
- `Google Order panel links`: links visible after opening the Google Order button flow. Keep them in `gmbOrderLinks`, show them in store details, and include them in Google Order provider/link overview charts. Do not count them as strict provider rows unless they are visible provider rows.
- A claim may use `sourceType: gmb` only if it was observed inside the Google Business Profile blue online-order button flow. The button may appear as one `線上點餐` button or as separate `點餐外帶` and `點餐外送` buttons. Open the button, read the pickup or delivery panel, then record only the providers visible there. Official Nidin links, marketplace URLs, embedded Maps links, Google search snippets, or known provider pages must remain `official`, `marketplace`, `third_party`, or `google`; never backfill them as Google Order.
- Google Order panel rows labelled `nidin.shop` / `order.nidin.shop`, `ocard.co` / `order.ocard.co`, or another merchant ordering domain are valid Google Order provider rows only when visible inside the opened panel. The same domains outside the opened panel are not valid Google Order evidence.
- `orderMode` may include `pickup`, `delivery`, `dine_in`, `reservation`, or `unknown`.
- Put messaging, loyalty, menu-only, or reservation links in ordering evidence only when they support ordering or the user asks to track them.
- Keep official ordering providers separate from marketplace providers through `sourceType`.

## Manual Review

Do not guess for:

- GMB pages hidden behind dynamic buttons or scripts
- Google Order blue online-order entries that cannot be opened or whose pickup/delivery panel cannot be read
- Google bot-check or `sorry` pages during re-checks; preserve prior confirmed blue-button evidence when available and note the block
- stores with multiple possible Google Maps matches
- closed, moved, duplicate, or temporarily closed stores
- mall counters, hospital stores, campus stores, airports, venue stores, or restricted-access stores
- stores absent from official ordering APIs
- provider pages blocked by region gates, app-only pages, bot protection, or login

Keep these stores in the dataset and mark `manualReviewReason`.

## HTML Dashboard Structure

Use a high-level dashboard layout. The first viewport should be the actual report, not a landing page.

### Visual System

Use a product-dashboard visual style suitable for internal analysis:

- Page background: white or a very light green-gray wash.
- Cards and tables: white surfaces, thin low-contrast borders, subtle shadows, and at least comfortable dashboard spacing.
- Primary interaction color: a calm green for geography filters, city map emphasis, and non-platform progress bars.
- Avoid saturated blue/purple UI chrome, large decorative gradients, heavy shadows, and full-row platform color blocks.
- Keep the Taiwan map readable: county names and counts should remain visible, selected counties should be highlighted, and non-selected counties should fade instead of showing confusing zero states.
- Mobile layout should stack controls and KPI cards cleanly. Avoid horizontal scrolling except for dense details tables.

Provider/platform styling:

- Render provider names as compact logo-like badges.
- Use provider colors only on provider badges, provider progress bars, and provider counts. Keep chart rows, table cells, and containers neutral.
- Nidin: blue `#0098ff`, white badge text.
- Uber Eats: black badge with white text; use Uber Eats green `#06c167` for progress bars.
- foodpanda: pink `#ff2b85`, white badge text.
- LINE: LINE Green `#06c755`, white badge text.
- QuickClick / 快一點: yellow `#fcb900`, black badge text.
- Unknown, pending, or non-platform claims should use neutral or soft-warning badges, not platform colors.

### 1. Brand Store Overview

Answer: how many stores exist and where are they distributed?

Include:

- official store count
- GMB-found store count
- Google-found store count
- third-party-found store count
- verification gap count
- Taiwan map with 22 city/county counts when market is Taiwan
- region filter: 全台, 北部, 中部, 南部, 東部, 離島
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

### 3. Google Order Provider Overview

Answer: which providers and order-flow links are visible inside Google Order and where are strict Google Order provider evidence gaps?

Include:

- GMB-found store count
- Google Order provider store count
- Google Order provider coverage rate
- Google Order provider evidence gap count
- Google Order provider/link ranking chart that includes visible `gmbOrderLinks` such as Instagram, LINE, and merchant-site links
- Google Order provider region coverage matrix
- clear note that Google Order provider evidence gaps are unknown/coverage gaps, not proof of no ordering system

### 4. All-Source vs Google Order Provider Comparison

Answer: does Google Order provider evidence underrepresent any ordering systems?

Include a table with:

- system name
- all-source store count
- all-source adoption rate
- Google Order provider store count
- Google Order provider coverage rate
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
- Google Order provider evidence
- evidence links
- review status or manual review reason

Filters should include:

- 全台 / region group / city
- system
- source type
- GMB status
- manual-review status

## Static Site Checklist


- Fixed HTML output means the brand report is generated into `<brand-slug>/index.html` with matching `<brand-slug>/data-inline.js` and `<brand-slug>/data/` exports, and it reuses shared root assets when the repository already has them. Do not create only a root-level standalone HTML for a new brand in a multi-brand report site.
For a static report site:

- If the site is intended to hold more than one brand, keep the repository root as the brand selector and put each brand report in a sibling slug directory.
- Use stable lowercase brand slugs such as `daming`, `chage`, or another user-approved slug. Avoid spaces, mixed casing, and provider names in brand slugs.
- Keep each brand report self-contained under `<brand-slug>/`, including that brand's `index.html`, `data/stores.json`, `data/summary.json`, and optional CSV/export files.
- Keep shared frontend files in a root-level shared directory such as `assets/` when multiple brand reports use the same dashboard code.
- Update the root `index.html` brand selector whenever a new brand directory is added.
- The GitHub Pages base path should be the reusable project name, such as `/brand-order-analysis/`; do not use the first analyzed brand as the site base path if more brands are expected.
- Single-brand throwaway reports may keep `index.html`, `styles.css`, `app.js`, and `data/` at the project root only when the user clearly wants a one-brand site.
- Keep the report usable from GitHub Pages without a server.
- Use one active geography filter state to update KPI cards, map, charts, comparison table, and store details.
- Keep all-source ordering-system charts, strict Google Order provider counts, and Google Order provider/link charts conceptually separate.
- Ensure evidence links remain reachable from store details.
- Show `gmbOrderLinks` distinctly from strict Google Order provider evidence so social or merchant-site order-flow links remain auditable without changing strict provider statistics.
- In store details and Google Order overview charts, include `gmbOrderLinks` by pickup/delivery mode. This keeps links such as Instagram visible where reviewers expect Google Order options, while strict provider-row counts remain separately available.
- On mobile, avoid horizontal scrolling in the map and KPI areas.

## Publishing Checklist

Before publishing:

- Generated JSON files parse.
- `officialStoreCount` equals the number of store records.
- Permanently closed, closed, or moved stores are excluded from active store records and denominator unless historical coverage was explicitly requested.
- Overall adoption rate uses official store count as denominator.
- Google Order provider coverage rate uses official store count as denominator.
- Google Order provider evidence gaps are counted separately from confirmed non-adoption.
- City counts sum to official store count.
- Region counts sum to official store count, with 離島 separate for Taiwan.
- Evidence links are present for confirmed ordering-system claims when public evidence exists.
- Google Order panel links visible after opening the order flow are preserved in `gmbOrderLinks`, appear in Google Order provider/link overview charts, and do not alter strict provider-row counts unless they are provider rows.

