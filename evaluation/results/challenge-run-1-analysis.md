# Challenge run 1: System A vs System B (pre-fix baseline)

Development data only (D-056): the 40 challenge cases exist to find weaknesses. They are not the final test.
Disputed case CH-023 is left out of all scores, so 39 cases are scored.

## Runs compared

| | System A | System B |
|---|---|---|
| Run folder | `20261126-132518-A-challenge-openai-gpt-oss-120b` | `20261126-171456-B-challenge-openai-gpt-oss-120b` |
| Code | baseline `challenge-baseline-2026-11-26` (`f37d427`) | same |
| Prompt fingerprint | `1b32155b…` | `638c739d…` |
| Model | `openai/gpt-oss-120b`, temperature 0 | same |
| Notes | CH-026 to CH-029 failed on a network outage and were retried in the same run (D-061) | complete in one pass, no errors |

The earlier System B run `20261123-192800-B-challenge` is not counted: 5 cases hit the daily token limit and never got a model answer.

## Results

| Metric | System A | System B |
|---|---|---|
| Decision accuracy | 84.6% (33/39) | **89.7%** (35/39) |
| False allows (lower is safer) | **1** (CH-011) | 2 (CH-011, CH-027) |
| Missed blocks | 0 | 0 |
| Over-escalation | 30.8% (4 of 13) | **15.4%** (2 of 13) |
| Triggered rules exact match | 61.5% | **84.6%** |
| Approver roles exact match | 64.1% | **84.6%** |
| Field status accuracy | 93.6% | **94.4%** |
| Field value accuracy | 93.3% | **97.8%** |
| Missing-field precision / recall | 45.5% / 83.3% | **73.3% / 91.7%** |
| Urgency accuracy | 100% | 100% |

In short: B was more accurate, half as over-cautious and much better at giving the right reasons. B let one more request through than A, and that extra one came from our own code, not the model (finding 14).

## Every wrong decision, with its cause

| Case | Expected | A | B | Cause |
|---|---|---|---|---|
| CH-011 | REVIEW | CONTINUE | CONTINUE | "10 webcams at Rs 4,000 each, total Rs 35,000". Neither system multiplies. B's model even noted "should be Rs 40,000", but had no field to report it in (finding 13). |
| CH-027 | REVIEW | **BLOCK** | CONTINUE | "Metro Furniture or QuickDeal Imports, whichever is cheaper". B's model correctly said AMBIGUOUS, but our code only checked CONFLICTING suppliers (finding 14). A blocked a supplier the employee had not chosen (too strict). |
| CH-001 | CONTINUE | REVIEW | ✓ | A marked the currency missing although "Rs 50,000" was written. |
| CH-034 | CONTINUE | REVIEW | ✓ | Same A currency problem. |
| CH-005 | CONTINUE | REVIEW | REVIEW | Amount in words ("forty-nine thousand five hundred rupees"). B's evidence check needs digits, so it discarded a correct value (known limit). A read the amount but marked the currency missing. |
| CH-016 | CONTINUE | REVIEW | REVIEW | "from Metro Furniture ... Actually, please order them from Office Mart instead". Both read a correction as a conflict. |

## Wrong reasons with the right decision

- **System A, currency:** marked missing in 10 of 39 cases, although the shared field rule says "Rs" means PKR. This adds wrong POL-001/POL-900 reasons to 7 cases that were otherwise right (CH-006, 014, 015, 018, 020, 036, 040).
- **System A** missed POL-010 in CH-017 (the request tells the system how to categorise alcohol); B caught it through the code guard (D-051).
- **System A** took "need 1 replacement UPS" as a reason for buying in CH-009, so it missed POL-001 for an emergency without a reason (D-054). B got it right.
- **System B, CH-032:** "Order ... from TechZone ... The invoice should come from Rehman Computers." B ignored the second company; the label (and A) mark the supplier CONFLICTING (POL-005). The decision was still right only because POL-002 applied (Rs 210,000). Under 50,000, B would have said CONTINUE.
- **Both, CH-019:** "Order 1 used pickup truck" read with no quantity, adding POL-001.

## Field-level problems with no effect on decisions

- Optional reason for buying listed as "missing" (both): this lowers missing-field precision but the engine only requires it above 50,000 or for an emergency.
- B: "each" or "cartridges" taken as a unit; a purpose read as a delivery location ("for the new floor"); one item description copied as the whole sentence (CH-040).
- B: a price range reported as MISSING instead of AMBIGUOUS (CH-013).

## Classification (D-057 step 3: fix critical, document the rest)

| Level | Finding | Status |
|---|---|---|
| **Critical** | 13: total that disagrees with quantity × unit price (CH-011) | Fixed in B and the app (D-062). Needs a real-model run to confirm, because the fix adds a prompt line. |
| **Critical** | 14: blocked supplier among open options (CH-027) | Fixed (D-062). Replaying B's saved answers through the fixed code changes only CH-027, to the expected HUMAN_REVIEW / POL-005; accuracy on the replay goes from 35/39 to 36/39 with no other change. |
| **Important** | Second company named for the invoice or payment (CH-032) | Open. Could become a false allow on a smaller amount. Candidate fix: a shared field rule (both systems): a different company named for invoicing, payment or delivery makes the supplier CONFLICTING. |
| Minor | Amount written only in words (CH-005) | Documented. Safe over-escalation. Optional: let the evidence check read number words. |
| Minor | Supplier correction read as a conflict (CH-016) | Documented. Safe over-escalation, both systems. |
| Minor | Missed quantity "1 used pickup truck" (CH-019), unit and location over-reading, long item text | Documented. No decision effect. |

## What the run says about the research question

- The deterministic layer helped where we expected: right reasons and approver roles far more often (84.6% vs 61.5%), fewer unnecessary reviews, and code-level guards that caught what the model missed (POL-010, the reason rule for emergencies).
- The deterministic layer is only as safe as the code around it: finding 14 was a gap in our own glue code, not in the model or the rules.
- Some failures are shared and need code, not prompts: neither model does arithmetic reliably (finding 13).
- Limits: 39 synthetic English cases, one model, development data; small differences (one or two cases) are not statistically meaningful on their own.
