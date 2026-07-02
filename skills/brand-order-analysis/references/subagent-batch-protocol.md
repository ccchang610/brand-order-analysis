# Subagent Batch Protocol

## Purpose

Use this protocol when a brand has enough stores that one-at-a-time manual review is slow, but the core low-resource GMB / Google Order audit must remain batch-safe and resumable.

The goal is to parallelize store-level evidence extraction without letting workers change the source of truth. Workers produce evidence rows. The main agent owns the official store population, active denominator, final merge, conflict resolution, summary formulas, and report output.

## When To Use Subagents

Use subagents when:

- Stores can be split into independent batches of roughly 20-30 records.
- The worker task has a fixed output shape, such as GMB identity candidates, platform-direct evidence, marketplace matches, LINE/order links, or unresolved-store QA.
- A worker can stop after producing evidence without deciding final adoption rates.
- The main agent can review conflicts before data is merged.

Do not use subagents to:

- Rebuild the official store population independently.
- Decide active denominator, closed-store exclusion, or final summary rates.
- Run high-concurrency Google / Maps / GMB browser checks.
- Convert official, marketplace, Maps website, or organic search links into `sourceType: gmb`.
- Rewrite `storeId`, provider canonical names, dashboard formulas, or report structure.

## Roles

### Main Agent

- Builds or approves the official active store population.
- Creates batch files from the canonical `stores.json`.
- Defines allowed task types and source rules for each batch.
- Owns the low-resource GMB / Google Order browser worker.
- Validates worker output before merge.
- Resolves conflicts, preserves prior confirmed evidence, regenerates summary/report output, and runs publishing validation.

### Worker / Subagent

- Receives one batch file and one task type.
- Checks only the assigned stores.
- Returns JSONL evidence rows using the schema below.
- Does not edit `stores.json`, `summary.json`, HTML, or source skill files directly.
- Does not compute adoption rates or final provider counts.

## Batch Input Shape

Batch files should be JSON:

```json
{
  "batchId": "teamagichand-gmb-identity-001",
  "brand": "Tea Magic Hand",
  "brandSlug": "teamagichand",
  "taskType": "gmb_identity",
  "createdAt": "2026-07-03T00:00:00Z",
  "sourceRules": {
    "gmbProviderRule": "sourceType:gmb only when provider row is visible inside opened Google Order panel",
    "doNotInferPlatformAbsenceFromGoogleOrder": true,
    "googleOrderConcurrency": 1
  },
  "stores": []
}
```

Keep batch files small enough that a failed run can be retried without losing much progress. The default target is 20-30 stores per batch.

## Worker Output Schema

Workers write one JSON object per line:

```json
{
  "batchId": "teamagichand-gmb-identity-001",
  "workerId": "agent-a",
  "taskType": "gmb_identity",
  "storeId": "teamagichand-tw-001",
  "status": "confirmed",
  "proposedPatch": {},
  "evidence": [
    {
      "sourceType": "google",
      "system": "",
      "orderMode": ["unknown"],
      "evidenceUrl": "https://www.google.com/search?q=...",
      "confidence": "confirmed",
      "matchedBy": ["storeName", "address"],
      "notes": "Named GMB profile matched store name and address."
    }
  ],
  "conflicts": [],
  "manualReviewReason": "",
  "checkedAt": "2026-07-03T00:00:00Z",
  "notes": ""
}
```

Required fields: `batchId`, `workerId`, `taskType`, `storeId`, `status`, `evidence`, `checkedAt`.

Allowed `taskType` values:

- `platform_direct`
- `gmb_identity`
- `gmb_order_panel`
- `unresolved_recheck`
- `qa_sample`

Allowed `status` values:

- `confirmed`
- `partially_confirmed`
- `not_found`
- `blocked`
- `ambiguous`
- `needs_manual_review`

## Google Order Rules For Workers

- Preserve the existing low-resource pattern: one Google / Maps / GMB browser worker by default, small batches, per-store checkpointing, and disposable browser profiles outside synced folders.
- Subagents may prepare GMB identity candidates, but strict provider extraction still requires visible rows inside the opened Google Order panel/searchviewer flow.
- Do not run many workers against Google simultaneously. More browser workers can increase blocking, timeouts, and CPU pressure.
- If a worker only sees a blue order button but cannot read provider rows, return `button_confirmed_provider_pending` evidence and do not guess providers.
- If a current check is weaker than prior confirmed provider evidence, report the weaker result as a conflict. Do not overwrite the confirmed evidence.

## Merge Rules

- Validate every worker JSONL file before applying it.
- Merge only by stable `storeId`.
- Apply platform-direct evidence into `platformAudit` and non-GMB `orderingSystems`.
- Apply GMB provider evidence only when the worker evidence proves the provider row was visible inside the opened Google Order flow.
- Put ambiguous or conflicting rows into a conflict ledger instead of silently overwriting canonical data.
- Regenerate `summary.json`, CSV, `data-inline.js`, and HTML only after the canonical store data is stable.

## Recommended Workflow

1. Main agent builds canonical stores and writes batch files.
2. Workers run platform-direct and GMB identity batches in parallel.
3. Main agent validates worker output and merges low-risk evidence.
4. One low-resource GMB browser worker runs Google Order panel batches sequentially.
5. Workers can QA unresolved or sampled stores, but final conflict resolution stays with the main agent.
6. Main agent regenerates outputs and verifies JSON, counts, city/region totals, all-source adoption, strict GMB provider counts, and Google Order provider/link charts.
