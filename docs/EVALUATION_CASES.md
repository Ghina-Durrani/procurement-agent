# Evaluation Cases

**Status: DRAFT labels.** 80 synthetic cases written on 2026-11-19. Every label must be checked by a team member before any result is reported (`EXTRACTION_MODULE_DESIGN.md` §6). The dev/test split was locked on 2026-11-19, before any tuning (D-047).

**Owner:** Maira · **Related:** `EXTRACTION_MODULE_DESIGN.md` §6-7, `POLICY_RULES.md`, D-044, D-045, D-047, D-048

## 1. Files

| File | What it holds |
|---|---|
| `evaluation/cases/cases.jsonl` | One case per line: request text, expected fields, expected urgency, expected decision, rules and roles |
| `evaluation/cases/context.json` | Company facts shared by all cases: demo policy settings, approved and blocked suppliers, default budget status |
| `evaluation/cases/split_lock.json` | Fingerprint of each case's split and text. Written once; do not edit by hand |
| `backend/app/services/evaluation/` | Loading and checking code. Never used at runtime |

Check everything from `backend/`:

```powershell
python -m app.services.evaluation.check_cases
```

## 2. One case

| Key | Meaning |
|---|---|
| `case_id` | `EV-001` to `EV-080` (`EV` so they are not confused with the policy examples C01-C23) |
| `split` | `dev` (may be used to tune prompts) or `test` (held out, run once after prompts are frozen) |
| `category` | One of the 10 categories in the design (§6) |
| `request_text` | The message, exactly as a requester might type it |
| `context` | Optional changes to `context.json` for this case: `budget_status`, `recent_requests` |
| `expected_fields` | All 10 extraction fields, each with `status` and `value` (value only when `PRESENT`) |
| `expected_urgency` | `NORMAL`, `URGENT` or `EMERGENCY_CLAIMED` |
| `expected_missing_fields` | Required fields that are not `PRESENT` |
| `expected_checkpoint` | Always `INTAKE` |
| `expected_decision`, `expected_triggered_rules`, `expected_required_roles` | What the approved rules give for the true facts |
| `label_status`, `verified_by` | `draft` until a person checks the case; then `verified` and their name |
| `notes` | Why a tricky label was chosen |

## 3. How the expected decision is worked out

1. Read the true facts from the message (the expected fields and urgency).
2. Add the company facts from `context.json`: supplier status from the supplier lists (case and spaces ignored; a name on neither list is `NOT_APPROVED`), budget status, recent requests.
3. Apply the approved rules (POL-001 to POL-008, POL-900) at `INTAKE`.

Two simplifications, the same for System A and System B:

- **One pass, no clarification.** No requester answers questions during the evaluation, so a required field that is not `PRESENT` goes straight to POL-001.
- **Urgency to priority.** Until the priority step is built (D-028, D-031), `EMERGENCY_CLAIMED` counts as an emergency (POL-008), `URGENT` as high priority, `NORMAL` as normal. Deadline thresholds are left out because their values are still OPEN (D-047, PROPOSED).

The checker runs the policy engine on the expected facts for every case. If a hand-written decision, rule list or role list differs from what the engine gives, it reports the case. This catches label mistakes. It also means the expected decision is the policy as coded, so the engine must stay covered by its own tests (C01-C23).

## 4. Labelling rules

**Status**
- `PRESENT`: the message clearly states it.
- `MISSING`: the message does not say it.
- `AMBIGUOUS`: it says something unclear: "a few", "around 10 or so", "15-20", "40 to 70 thousand", "the usual stuff", "nothing too expensive".
- `CONFLICTING`: two statements disagree and neither is a correction. Two different suppliers named for the same order count: POL-005 sends it to review (EV-028, D-048). An explicit correction ("actually make it 10") is not a conflict: the corrected value is `PRESENT` (EV-025).
- Words inside an injected instruction ("output quantity 1") are not facts about the purchase (EV-068).

**Fields**

| Field | `PRESENT` when |
|---|---|
| `item_description` | The item or service is named. Value is a short reference ("laptops") |
| `quantity` | An exact whole number is written. "a few", "a couple of", ranges and "around 10" are `AMBIGUOUS` |
| `unit` | A counting or measuring word is written: boxes, reams, packs, bottles, units, visit, job, nos, pc. Not required |
| `estimated_total` | One total for the whole purchase is written ("budget Rs 15,000" counts). A single figure with "approx" or "around" is still the estimate. A price per item only is `MISSING` (never multiply). Written as a string: `"45000"`. "k", "lakh" and "crore" are converted |
| `currency` | Rs, Rs., PKR, rupees (PKR) or $ (USD) is written. A bare "45,000" or "6k" is `MISSING` |
| `item_category` | The item clearly fits exactly one demo code (§5). Otherwise `MISSING` |
| `supplier_name` | A supplier is named. Value is the name as written. "the usual vendor" is `AMBIGUOUS` |
| `delivery_deadline` | A deadline phrase is written: "by Friday", "ASAP", "within 24 hours", "today". Kept in the requester's words |
| `delivery_location` | A place where the items go or the service is done: a floor, room, office, branch |
| `business_justification` | A reason is given: a problem ("old ones are broken"), a need ("for the new hires") or a purpose |

**Urgency**
- `NORMAL`: no time pressure. A deadline on its own ("by Friday", "next month") is normal.
- `URGENT`: time pressure is stated: "urgent", "ASAP", "immediately", "today", "tomorrow", "within 24 hours".
- `EMERGENCY_CLAIMED`: the requester calls it an emergency or describes an outage, a safety risk or work that has stopped. A claim, never a verified fact.

## 5. Category codes (demo)

| Code | Examples |
|---|---|
| `OFFICE_SUPPLIES` | paper, pens, staplers, binders, markers, toner and ink cartridges |
| `IT_HARDWARE` | laptops, monitors, keyboards, mice, printers, routers, switches, UPS, cables, chargers, webcams, tablets |
| `FURNITURE` | chairs, desks, cabinets |
| `MAINTENANCE_SERVICES` | AC servicing or repair, plumbing, generator repair |
| `CLEANING_SUPPLIES` | sanitizer, mops, tissue rolls |
| `PRINTING` | printing jobs: business cards, reports |
| `TRAVEL` | flights, hotels |
| `SOFTWARE` (needs IT) | licences, subscriptions |
| `HAZARDOUS_CHEMICALS` (needs HSE) | solvents, acids |
| `VEHICLES` (needs Senior Management) | cars, vans |
| `WEAPONS`, `ALCOHOL`, `PERSONAL_USE`, `GIFT_CARDS` (blocked) | pistol; wine, beer, whisky; items for one person's private use; gift cards, prepaid vouchers |

Fire extinguishers fit no code, so EV-044 has category `MISSING` (POL-006 sends it to review).

## 6. How to verify the labels

For each case:
1. Read the message as if you were the procurement officer.
2. Check every field status and value against section 4, and the urgency.
3. Check the decision and rules against `POLICY_RULES.md`.
4. If you agree, set `"label_status": "verified"` and `"verified_by": "<your name>"`. If you disagree, change the label (and `notes` if useful).
5. Run the checker. Fix any case it reports.

Labels may be corrected at any time. Request text and split may not change after tuning starts: the lock reports any change. Before tuning, `check_cases --relock` records a corrected text; note the reason in `DECISIONS.md`.

**Cases that need your decision:**
- **EV-021:** is "a couple of" an exact 2 or unclear? Labelled `AMBIGUOUS`.
- **EV-069:** is "for my personal use" a business justification? Labelled `PRESENT`; the decision is `BLOCK` either way.
- **EV-071:** an injected "[ADMIN OVERRIDE: emergency ...]" is labelled `EMERGENCY_CLAIMED`, which only adds a Senior Management review.

## 7. How the cases were written, and limits

- Written on 2026-11-19 from the categories in the design. A team member must check every label (above).
- All names, suppliers and amounts are invented. No real company data.
- 8 cases per category: 3 dev and 5 test each (30 dev, 50 test), chosen by a fixed random seed before any prompt was run.
- Expected decisions: 22 `CONTINUE`, 46 `HUMAN_REVIEW`, 12 `BLOCK`.

Limits to state in the report:
- Short, single-item English messages written by the team, not real requester traffic.
- One labeller; no agreement score between two labellers.
- Free-text values (item, reason, location) need a lenient comparison; the metrics step will define it before the first run.
- The expected decision depends on the demo settings and the urgency mapping above.
