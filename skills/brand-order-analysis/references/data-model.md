# Brand Order Analysis Data Model

## Store Fields

Each store record should keep at least:

- `brand`
- `storeId`
- `storeName`
- `country`
- `market`
- `regionGroup`
- `city`
- `county`
- `district`
- `address`
- `latitude`
- `longitude`
- `phone`
- `hours`
- `officialSourceUrl`
- `officialStoreUrl`
- `officialMapUrl`
- `googleSearchUrl`
- `gmbUrl`
- `gmbStatus`
- `gmbOrderingStatus`
- `sourceCoverage`
- `orderingSystems`
- `hasAnyOrderingSystem`
- `hasGmbOrderingSystem`
- `manualReviewReason`
- `evidenceNotes`
- `checkedAt`

Legacy fields such as `takeoutAvailable`, `deliveryAvailable`, `takeoutProviders`, `deliveryProviders`, `otherProviders`, and `providerEvidenceUrls` may be kept for compatibility, but new work should use `orderingSystems` as the canonical evidence model.

## Source Coverage

Use `sourceCoverage` to separate store discovery from ordering-system evidence:

```json
{
  "officialListed": true,
  "gmbFound": true,
  "googleFound": true,
  "thirdPartyFound": true
}
```

Field meanings:

- `officialListed`: store exists in the official brand source or user-approved official dataset.
- `gmbFound`: a matching GMB / Google Maps profile was found.
- `googleFound`: store was found by Google search or Google Maps search, even if GMB ordering evidence is not available.
- `thirdPartyFound`: store appears on marketplace, aggregator, ordering, or directory sources.

## Google Order Entry Fields

Use these fields when a brand analysis includes Google / GMB ordering.

- `hasGmbOrderingSystem`: true when the blue Google Order entry is confirmed for the store. This may be true even when provider names are still pending.
- `gmbOrderingStatus`: status of the Google Order entry and provider-panel audit.
- `gmbOrderModesConfirmed`: optional array such as `pickup`, `delivery`, or `unknown` when the entry exists but providers are pending.
- `gmbPickupProviders`: providers confirmed from the pickup panel only.
- `gmbDeliveryProviders`: providers confirmed from the delivery panel only.
- `gmbOrderPanelUrl`: URL observed after opening the Google Order flow when available.
- `gmbSignals`: audit metadata for the Google Order check, especially when the store is pending or blocked.
- `manualReviewReason`: required when status is pending, blocked, timed out, ambiguous, or no button was found after human-paced re-check.

Do not use `orderingSystems` with `sourceType: gmb` for a provider unless the provider name was visible inside the opened Google Order panel. A confirmed blue order entry without readable providers should use `button_confirmed_provider_pending` instead of a guessed provider claim. Visible button text alone is entry evidence, not provider evidence; the audit must click the visible one-button or pickup/delivery control and wait for the Google Order panel/searchviewer flow before parsing providers.

For `orderMode`, count `pickup` or `delivery` only when that mode is active or can be selected in the Google Order panel. A greyed or disabled mode label does not count. Provider rows must be visible inside the Google Order dialog/panel; ignore provider names from background Google results, knowledge-panel snippets, official-site snippets, review widgets, or hidden text.

`nidin.shop` or `order.nidin.shop` counts as `Nidin` only when it is a visible provider row inside the opened Google Order panel. The same domain in official ordering links, organic Google results, or Maps website rows is not GMB evidence.

Example `gmbSignals`:

```json
{
  "buttonDetected": true,
  "providersParsed": false,
  "attemptCount": 6,
  "maxAttempts": 3,
  "attemptHistory": [
    {
      "attempt": 1,
      "target": "gmbUrl",
      "status": "button_confirmed_provider_pending",
      "buttonDetected": true,
      "providersParsed": false
    },
    {
      "attempt": 2,
      "target": "googleSearch",
      "status": "confirmed",
      "buttonDetected": true,
      "providersParsed": true
    }
  ],
  "panelUrl": "https://www.google.com/search?...",
  "checkedAt": "2026-05-31",
  "checkMethod": "human_paced_gmb_recheck_multi_attempt",
  "notes": "Blue Google Order entry confirmed, but provider names were not readable after bounded retries."
}
```

For `attemptCount`, count total tries across the Google Search business-card target, stored panel URL, and GMB/Maps URL. For `maxAttempts`, record the per-target maximum. Stop retries early when providers are parsed. If a persistent profile is blocked or stale, rerun unresolved pending stores with a fresh browser profile/session; repeated fresh checks with no blue Google Order entry can resolve stale pending records as `no_gmb_order_button`.
## Ordering Systems

Use `orderingSystems` as an array of evidence-backed claims:

```json
{
  "system": "Nidin",
  "sourceType": "official",
  "orderMode": ["pickup", "delivery"],
  "evidenceUrl": "https://example.com/order/store-1",
  "confidence": "confirmed"
}
```

Allowed `sourceType` values:

- `official`
- `google`
- `gmb`
- `marketplace`
- `third_party`
- `line`
- `manual`

Use `sourceType: gmb` only for providers observed inside the Google Business Profile blue online-order button flow. The button may be one `????` button or separate `????` / `????` buttons. Do not convert official ordering URLs, marketplace URLs, embedded Maps links, Google search results, or known provider pages into GMB claims. A `nidin.shop` provider row inside the opened Google Order panel is valid `Nidin` GMB evidence; the same URL outside the panel is not.

Allowed `orderMode` values:

- `pickup`
- `delivery`
- `dine_in`
- `reservation`
- `unknown`

Allowed `confidence` values:

- `confirmed`
- `partial`
- `ambiguous`
- `blocked`
- `needs_manual_review`

## Summary Fields

`data/summary.json` should include:

- `generatedAt`
- `brand`
- `market`
- `officialStoreCount`
- `gmbFoundCount`
- `googleFoundCount`
- `thirdPartyFoundCount`
- `verificationGapCount`
- `anyOrderingSystemCount`
- `anyOrderingSystemAdoptionRate`
- `gmbOrderingSystemCount`
- `gmbOrderingSystemAdoptionRate`
- `gmbCoverageGapCount`
- `unknownOrderingSystemCount`
- `cityCounts`
- `regionCounts`
- `allSourceSystemCounts`
- `gmbSystemCounts`
- `allSourceSystemAdoptionRates`
- `gmbSystemAdoptionRates`
- `systemComparison`
- `gmbStatusCounts`
- `gmbOrderingStatusCounts`
- `sourceCoverageCounts`
- `source`
- `notes`

Example:

```json
{
  "officialStoreCount": 120,
  "gmbFoundCount": 105,
  "googleFoundCount": 112,
  "thirdPartyFoundCount": 90,
  "anyOrderingSystemCount": 98,
  "anyOrderingSystemAdoptionRate": 0.817,
  "gmbOrderingSystemCount": 76,
  "gmbOrderingSystemAdoptionRate": 0.633,
  "gmbCoverageGapCount": 15,
  "cityCounts": {
    "???": 20,
    "???": 18
  },
  "regionCounts": {
    "??": 48,
    "??": 28,
    "??": 36,
    "??": 5,
    "??": 3
  },
  "allSourceSystemCounts": {
    "Nidin": 80,
    "Uber Eats": 60,
    "foodpanda": 52
  },
  "gmbSystemCounts": {
    "Uber Eats": 55,
    "foodpanda": 45
  }
}
```

## Status Values

GMB status:

- `confirmed`
- `not_found`
- `closed_or_moved`
- `duplicate_or_ambiguous`
- `unavailable_or_blocked`
- `needs_manual_review`

GMB ordering status:

- `confirmed`
- `no_gmb_order_button` (use only after human-paced checks, preferably including a fresh profile/session when resolving stale pending records, find no blue Google Order entry)
- `button_confirmed_provider_pending`
- `panel_without_known_provider`
- `no_ordering_system_found`
- `not_found`
- `unavailable_or_blocked`
- `duplicate_or_ambiguous`
- `needs_manual_review`

Order audit status, when a separate field is needed:

- `confirmed`
- `partially_confirmed`
- `not_found`
- `unavailable_or_blocked`
- `needs_manual_review`

## Counting Rules

- `officialStoreCount`: total records in the official store population after deduplication.
- `gmbFoundCount`: stores where `sourceCoverage.gmbFound` is true or `gmbStatus` is `confirmed`.
- `googleFoundCount`: stores where `sourceCoverage.googleFound` is true.
- `thirdPartyFoundCount`: stores where `sourceCoverage.thirdPartyFound` is true.
- `verificationGapCount`: stores missing enough source evidence to confidently verify store or ordering-system status.
- `anyOrderingSystemCount`: stores where `hasAnyOrderingSystem` is true.
- `anyOrderingSystemAdoptionRate`: `anyOrderingSystemCount / officialStoreCount`.
- `gmbOrderingSystemCount`: stores where `hasGmbOrderingSystem` is true, including stores with confirmed blue Google Order entry and pending provider names.
- `gmbOrderingSystemAdoptionRate`: `gmbOrderingSystemCount / officialStoreCount`.
- `gmbCoverageGapCount`: stores where GMB is not found, Google is blocked or timed out, matches are ambiguous, or the blue Google Order entry cannot be confirmed after human-paced re-check. Do not count `button_confirmed_provider_pending` as a gap.
- `unknownOrderingSystemCount`: stores where all-source ordering status remains unknown or needs manual review.

Provider counts:

- `allSourceSystemCounts`: count each `system` once per store across all source types.
- `gmbSystemCounts`: count each `system` once per store only where `sourceType` is `gmb`. Do not count provider-pending Google Order entries here.
- Adoption rates for individual systems use official store count as the denominator.
- Do not count duplicate evidence URLs as additional stores.

## Taiwan Geography Rules

For Taiwan reports, include all 22 cities/counties:

- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???
- ???

Default `regionGroup` mapping:

- `??`: ???????????????????????????
- `??`: ???????????????????
- `??`: ???????????????????
- `??`: ???????
- `??`: ???????????

Rules:

- Keep city counts for all 22 cities/counties, even when the count is `0`.
- Region counts should sum to official store count.
- The active HTML filter should support ??, one region group, or one city/county.
- If a city cannot be parsed, keep the store and set `manualReviewReason`.

## System Comparison

`systemComparison` should support the all-source vs GMB table:

```json
[
  {
    "system": "Uber Eats",
    "allSourceStoreCount": 60,
    "allSourceAdoptionRate": 0.5,
    "gmbStoreCount": 55,
    "gmbAdoptionRate": 0.458,
    "countGap": 5,
    "percentagePointGap": 0.042
  }
]
```

`countGap` is `allSourceStoreCount - gmbStoreCount`. `percentagePointGap` is `allSourceAdoptionRate - gmbAdoptionRate`.

## Evidence Rules

Prefer evidence URLs in this order:

1. official ordering URL or official ordering API result
2. official store URL
3. GMB ordering link or Google Maps URL
4. provider/marketplace evidence URL
5. Google search result URL
6. official store-list source URL
7. user-supplied manual evidence

If evidence conflicts, keep the conflict in `evidenceNotes`, keep both source types when useful, and avoid overwriting confirmed fields silently.

## Validation Rules

Before publishing or handing off:

- `officialStoreCount` equals the number of store records.
- `cityCounts` sums to `officialStoreCount`.
- `regionCounts` sums to `officialStoreCount`.
- `anyOrderingSystemAdoptionRate` equals `anyOrderingSystemCount / officialStoreCount`.
- `gmbOrderingSystemAdoptionRate` equals `gmbOrderingSystemCount / officialStoreCount`.
- GMB coverage gaps are counted separately from confirmed no-ordering-system stores.
- `allSourceSystemCounts` and `gmbSystemCounts` count unique stores per system, not evidence links.

