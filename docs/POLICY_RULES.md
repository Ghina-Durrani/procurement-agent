# Policy Rules (Q-007 draft)

**Status: PROPOSED.** This is a draft for team review. Nothing in this file is DECIDED until Ghina and Haya approve it. Every number in it is a demo value. Labels follow `CLAUDE.md` §6.

**Author:** Maira · **Created:** 2026-11-05 · **Answers:** Q-007 in `DECISIONS.md`

## 1. What this document is for

This document defines the rules the **policy engine** applies to a procurement request. The policy engine is plain Python code (not the LLM, not a human). For every evaluation it returns exactly one **policy outcome**: `CONTINUE`, `BLOCK` or `HUMAN_REVIEW`, plus the IDs of the rules that fired and a reason for each.

The rules are modelled on standard controls found in real procurement policies (approval tiers, competitive quotations, approved supplier lists, budget checks, emergency procedures, segregation of duties). Section 9 lists the sources. The **structure** of each rule follows real practice; the **amounts and lists** are demo values that each organization replaces with its own.

Part B (the code in `backend/app/policy/`) starts only after this document is approved.

## 2. Design rules for the engine (CONFIRMED by existing docs)

1. **Pure functions.** The engine imports nothing from the database, the API or any LLM library (`BACKEND_GUIDE.md` §3). Other modules collect the data and pass it in.
2. **Configuration is input.** Thresholds and lists come from a versioned `PolicyConfig` passed to the engine, never from constants in code. The `policy_version` is returned with every result, so any decision can be reproduced later.
3. **No clock inside the engine.** Time-based rules use timestamps passed in (`submitted_at`), so the same input always gives the same result.
4. **Money is `Decimal`,** never float. Amounts are compared in one currency only; the engine never converts currencies.
5. **Urgency is not permission.** A priority of `EMERGENCY` can make the result stricter, never looser. No rule returns `CONTINUE` because of urgency (D-007, D-028).
6. **LLM output is untrusted.** Fields such as `item_category` come from the extraction agent and are checked against configured lists. Supplier and budget status come from the database and the finance check, never from the LLM.
7. **Rule IDs are permanent.** Once published, a rule ID is never reused or renumbered. A retired rule keeps its ID.

## 3. When the engine runs: checkpoints

A request passes through the engine more than once. Each run has a **checkpoint**, and each rule says at which checkpoints it applies.

| Checkpoint | When | Rules that apply |
|---|---|---|
| `INTAKE` | After extraction and the clarification loop (D-029), before any supplier or quotation work | POL-001, POL-002, POL-004, POL-005, POL-006, POL-007, POL-008, POL-900 |
| `PRE_PO` | After quotations are collected and a supplier is selected, before a purchase order is prepared | POL-003, POL-005, POL-900 |
| `APPROVAL` | When a reviewer tries to approve a request | POL-009, POL-900 |

Why: quotations do not exist when a request first arrives, so the quotation rule can only run at `PRE_PO`. The supplier rule runs twice because the supplier may only be chosen after sourcing.

## 4. Outcome rules

**Precedence.** Every applicable rule is evaluated, even after one has fired. The final outcome is the strictest one: `BLOCK` beats `HUMAN_REVIEW`, which beats `CONTINUE`. All triggered rule IDs and reasons are returned, not only the strictest.

**CONTINUE** is returned only when no rule fired **and** every input the applicable rules need was present and valid.

**Fail closed (POL-900).** If an input is invalid, a required input is missing, the configuration is invalid, or a rule raises an error, POL-900 fires with `HUMAN_REVIEW`. The other rules still run, so a `BLOCK` from another rule still wins. The engine never returns `CONTINUE` after an error.

**Missing inputs.** A rule never guesses a missing value. Unless the rule's own definition says how a missing value is handled (for example POL-005 at `INTAKE`), a missing input makes POL-900 fire.

## 5. Input and output contract (PROPOSED)

These are plain Python types (Pydantic models in Part B). Field names are `snake_case`; enum values are uppercase strings, as in the Engineering Handbook §3.

### 5.1 `PolicyInput`

| Field | Type | Filled by | Used by |
|---|---|---|---|
| `request_id` | UUID | Intake | Audit |
| `organization_id` | UUID | Authenticated user (never client input) | Picks the organization's `PolicyConfig` |
| `checkpoint` | `INTAKE` \| `PRE_PO` \| `APPROVAL` | Workflow | All |
| `submitted_at` | UTC datetime | Intake | POL-004 |
| `requester_user_id` | UUID | Authenticated user | POL-004, POL-009 |
| `extraction_status` | `VALID` \| `INVALID` \| `FAILED` | Extraction | POL-900 |
| `missing_fields` | list of field names | Validation, after the clarification loop | POL-001 |
| `clarification_rounds_used` | int (0 to 2) | Clarification loop | POL-001 reason text |
| `estimated_total` | Decimal or null | Extraction (`INTAKE`) / selected quotation (`PRE_PO`) | POL-002, POL-003, POL-004 |
| `currency` | ISO-4217 string or null | Extraction / quotation | POL-900 |
| `item_category` | string or null | Extraction, proposed only | POL-004, POL-006 |
| `supplier_name` | string or null | Extraction (`INTAKE`) / supplier selection (`PRE_PO`) | POL-004, POL-005 |
| `supplier_status` | `APPROVED` \| `NOT_APPROVED` \| `BLOCKED` or null | Supplier table lookup (database) | POL-005 |
| `proposed_priority` | `NORMAL` \| `HIGH_PRIORITY` \| `EMERGENCY` or null | Urgency module (code, D-028) | POL-008 |
| `budget_status` | `AVAILABLE` \| `NEEDS_FINANCE_APPROVAL` \| `INSUFFICIENT` or null | Finance check | POL-007 |
| `quotation_count` | int or null | Quotation processing | POL-003 |
| `acting_user_id` | UUID or null | Authenticated reviewer (`APPROVAL` only) | POL-009 |
| `recent_requests` | list of `RecentRequest` | Service layer, from the database | POL-004 |

`RecentRequest` holds: `request_id`, `submitted_at`, `supplier_name`, `item_category`, `estimated_total`, `currency`, `status`. The service layer passes only the same requester's requests from the same organization within the look-back window.

> The exact enum strings for priority depend on the schema (Q-006, D-028). `NORMAL`, `HIGH_PRIORITY`, `EMERGENCY` are placeholders.

### 5.2 `PolicyResult`

| Field | Type | Meaning |
|---|---|---|
| `outcome` | `CONTINUE` \| `BLOCK` \| `HUMAN_REVIEW` | Final outcome after precedence |
| `checkpoint` | as input | Which checkpoint was evaluated |
| `triggered_rules` | list of `TriggeredRule` | Every rule that fired, in rule-ID order |
| `required_approver_roles` | list of role names | Roles that must act, collected from triggered rules (may be empty) |
| `policy_version` | string | Version of the `PolicyConfig` used |

`TriggeredRule` holds: `rule_id`, `outcome` (the rule's own outcome), `reason` (human-readable), `required_approver_role` (or null).

### 5.3 `PolicyConfig`

One per organization, versioned. A new version is created whenever a value changes; old versions are kept so past decisions stay reproducible. Its shape is shown in section 6.

## 6. Demo configuration

> **OPEN: demo values only.** These numbers and lists are placeholders for testing and the demo. They are not real company limits and must not be presented as such (D-031 style).

```text
policy_version:          "demo-2026-11-05.1"
accepted_currencies:     ["PKR"]

required_fields:         ["item_description", "quantity", "estimated_total",
                          "currency", "business_justification"]

approval_tiers (POL-002):
  up to and including        50,000.00   -> no approval needed
  50,000.01 to          500,000.00       -> MANAGER
  above                     500,000.00   -> SENIOR_MANAGER

quotation_bands (POL-003):
  up to and including       100,000.00   -> minimum 1 quotation
  above                     100,000.00   -> minimum 3 quotations

split_purchase (POL-004):
  window_days:              30
  watched_thresholds:       50,000.00 ; 100,000.00 ; 500,000.00
                            (the approval tier limits and the quotation limit)

categories (POL-006):
  allowed:      OFFICE_SUPPLIES, IT_HARDWARE, FURNITURE, MAINTENANCE_SERVICES,
                CLEANING_SUPPLIES, PRINTING, TRAVEL
  controlled:   SOFTWARE -> IT_APPROVER ; HAZARDOUS_CHEMICALS -> HSE_APPROVER ;
                VEHICLES -> SENIOR_MANAGER
  prohibited:   WEAPONS, ALCOHOL, PERSONAL_USE, GIFT_CARDS

budget (POL-007):
  NEEDS_FINANCE_APPROVAL    -> FINANCE_APPROVER

emergency (POL-008):
  approver_role:            SENIOR_MANAGER
```

Roles (`PROCUREMENT_OFFICER`, `MANAGER`, `SENIOR_MANAGER`, `FINANCE_APPROVER`, `IT_APPROVER`, `HSE_APPROVER`) are placeholders; the role model is OPEN (Q-004).

## 7. The rules

Each rule lists: checkpoint, inputs it reads, logic, outcome, reason message, and the real-world practice it is based on.

---

### POL-001: Completeness

- **Checkpoints:** `INTAKE`
- **Inputs:** `missing_fields`, `clarification_rounds_used`
- **Logic:** fires if `missing_fields` contains any field from `required_fields`. By the time the engine runs, the clarification loop (D-029) has already asked the requester up to 2 times, so anything still missing is sent to a person.
- **Outcome:** `HUMAN_REVIEW` (role: `PROCUREMENT_OFFICER`)
- **Reason:** "Required field(s) still missing after {n} clarification round(s): {fields}."
- **Real-world basis:** standard requisition practice. A request must carry the item, quantity, amount and business purpose before anyone can approve it.

---

### POL-002: Approval tiers (delegation of authority)

- **Checkpoints:** `INTAKE`
- **Inputs:** `estimated_total`
- **Logic:** finds the tier that contains `estimated_total`. If that tier names an approver role, the rule fires.
- **Outcome:** `HUMAN_REVIEW` with the tier's role (`MANAGER` or `SENIOR_MANAGER`)
- **Reason:** "Amount {amount} {currency} requires {role} approval."
- **Missing input:** `estimated_total` missing → POL-900 (POL-001 will also fire, since it is a required field).
- **Real-world basis:** delegation of authority. Organizations assign higher spending limits to more senior roles; public bodies and platforms such as Coupa route requests by spend threshold.

---

### POL-003: Competitive quotations

- **Checkpoints:** `PRE_PO`
- **Inputs:** `estimated_total` (the selected quotation's amount), `quotation_count`
- **Logic:** finds the minimum number of quotations for the amount band. Fires if `quotation_count` is below that minimum.
- **Outcome:** `HUMAN_REVIEW` (role: `PROCUREMENT_OFFICER`)
- **Reason:** "{required} quotation(s) required for {amount} {currency}; {received} received. A documented justification is needed."
- **Missing input:** `quotation_count` missing at `PRE_PO` → POL-900.
- **Real-world basis:** most procurement policies require a minimum number of written quotations above a value, and require the reason to be documented when fewer are obtained.

---

### POL-004: Split-purchase detection

- **Checkpoints:** `INTAKE`
- **Inputs:** `estimated_total`, `submitted_at`, `supplier_name`, `item_category`, `recent_requests`
- **Logic:**
  1. From `recent_requests`, keep those submitted within `window_days` before `submitted_at`, in the same currency, not rejected or withdrawn (status names fixed with Q-006), and **related** to this request: same supplier (compared case-insensitively, trimmed), or, if either request has no supplier, the same `item_category`.
  2. `combined = estimated_total + sum of their estimated_total`.
  3. Fires if, for any watched threshold `T`, `estimated_total <= T < combined`. In words: this request alone stays under a limit, but together with related recent requests it crosses that limit.
- **Outcome:** `HUMAN_REVIEW` (role: `PROCUREMENT_OFFICER`)
- **Reason:** "Possible split purchase: {k} related request(s) in the last {window_days} days bring the combined total to {combined} {currency}, above the {T} limit."
- **Real-world basis:** splitting one need into smaller orders to stay below approval or quotation limits is prohibited in procurement policies and is a common audit finding.
- **Why it matters for the research:** an LLM reading one message cannot see past requests. This rule shows what deterministic checks over request history add.

---

### POL-005: Approved supplier list

- **Checkpoints:** `INTAKE`, `PRE_PO`
- **Inputs:** `supplier_name`, `supplier_status`
- **Logic:**
  - `BLOCKED` → fires with `BLOCK`.
  - `NOT_APPROVED`, or a supplier name that the lookup could not match (`supplier_status` null while `supplier_name` is set) → fires with `HUMAN_REVIEW`.
  - `APPROVED` → does not fire.
  - At `INTAKE` only: no supplier named → does not fire (sourcing will choose one).
  - At `PRE_PO`: no supplier selected → POL-900.
- **Outcome:** `BLOCK` or `HUMAN_REVIEW` (role: `PROCUREMENT_OFFICER`)
- **Reasons:** "Supplier '{name}' is on the blocked list." / "Supplier '{name}' is not on the approved supplier list."
- **Real-world basis:** approved / preferred supplier lists and blocked (debarred) supplier checks are standard pre-approval controls in procurement platforms.

---

### POL-006: Restricted categories

- **Checkpoints:** `INTAKE`
- **Inputs:** `item_category`
- **Logic:**
  - In `prohibited` → fires with `BLOCK`.
  - In `controlled` → fires with `HUMAN_REVIEW` and that category's role.
  - In `allowed` → does not fire.
  - Missing, or not in any list → fires with `HUMAN_REVIEW` (role: `PROCUREMENT_OFFICER`; the category comes from the LLM and is untrusted, so an unknown value is never treated as allowed).
- **Outcome:** `BLOCK` or `HUMAN_REVIEW`
- **Reasons:** "Category '{category}' is not allowed." / "Category '{category}' requires {role} sign-off." / "Category could not be matched to the approved list."
- **Real-world basis:** organizations keep lists of purchase types that need extra authorization regardless of amount, and lists of items that may not be bought at all.

---

### POL-007: Budget availability

- **Checkpoints:** `INTAKE`
- **Inputs:** `budget_status`
- **Logic:**
  - `INSUFFICIENT` → fires with `BLOCK`.
  - `NEEDS_FINANCE_APPROVAL` → fires with `HUMAN_REVIEW` (role: `FINANCE_APPROVER`).
  - Missing → fires with `HUMAN_REVIEW` (role: `FINANCE_APPROVER`; fail closed, the budget could not be confirmed).
  - `AVAILABLE` → does not fire.
- **Reasons:** "Insufficient budget for this request." / "Budget requires finance approval." / "Budget availability could not be confirmed."
- **Note:** a request within budget can still be blocked or reviewed by other rules (`FYP_MASTER_CONTEXT.md` §4).
- **Real-world basis:** purchases must be approved within an approved source of funds; procurement platforms check budget availability before approval.

---

### POL-008: Emergency path

- **Checkpoints:** `INTAKE`
- **Inputs:** `proposed_priority`
- **Logic:** `EMERGENCY` → fires. `NORMAL` and `HIGH_PRIORITY` → do not fire. Missing → does not fire (priority is optional; the absence of urgency evidence is normal).
- **Outcome:** `HUMAN_REVIEW` (role: `SENIOR_MANAGER`, the named emergency approver)
- **Reason:** "Emergency priority proposed; a named emergency approver must confirm this is a genuine emergency."
- **What it does not do:** it never waives another rule and never returns `CONTINUE`. An emergency request that also has a blocked supplier is still `BLOCK`.
- **Real-world basis:** emergency procurement procedures let organizations move faster, but every emergency purchase still needs approval from a designated authority, and poor planning does not count as an emergency.

---

### POL-009: Segregation of duties

- **Checkpoints:** `APPROVAL`
- **Inputs:** `requester_user_id`, `acting_user_id`
- **Logic:** fires if `acting_user_id` equals `requester_user_id`. If `acting_user_id` is missing → POL-900.
- **Outcome:** `BLOCK` (the approval action is refused; the request itself stays in the review queue for another approver)
- **Reason:** "The requester cannot approve their own request."
- **Real-world basis:** segregation of duties. The person who requests a purchase must not be the one who approves it.

---

### POL-900: Fail closed

- **Checkpoints:** all
- **Fires when any of these is true:**
  - `extraction_status` is `INVALID` or `FAILED` (at `INTAKE`).
  - `currency` is not in `accepted_currencies`.
  - `estimated_total` is zero or negative.
  - A required input of an applicable rule is missing, and that rule does not define how to handle it.
  - The `checkpoint` value is unknown, or the `PolicyConfig` is missing or invalid.
  - A rule raises an error.
- **Outcome:** `HUMAN_REVIEW` (role: `PROCUREMENT_OFFICER`)
- **Reason:** names the specific problem, for example "Currency 'USD' is not accepted by this policy." or "Rule POL-004 could not be evaluated."
- **Basis:** the project's own fail-closed rule (`CLAUDE.md` §2.2).

## 8. Example cases

These cases become the tests in Part B (`backend/tests/policy/`).

**Base request** (used unless a case changes a field): checkpoint `INTAKE`, `extraction_status = VALID`, nothing missing, `estimated_total = 30,000.00 PKR`, `item_category = OFFICE_SUPPLIES`, `supplier_status = APPROVED`, `proposed_priority = NORMAL`, `budget_status = AVAILABLE`, no recent requests.

| Case | Change from the base request | Expected outcome | Expected rule IDs | Roles |
|---|---|---|---|---|
| C01 | none | `CONTINUE` | none | none |
| C02 | `missing_fields = [quantity]` after 2 rounds | `HUMAN_REVIEW` | POL-001 | PROCUREMENT_OFFICER |
| C03 | total `50,000.00` (tier boundary) | `CONTINUE` | none | none |
| C04 | total `50,000.01` | `HUMAN_REVIEW` | POL-002 | MANAGER |
| C05 | total `1,200,000.00` | `HUMAN_REVIEW` | POL-002 | SENIOR_MANAGER |
| C06 | total `40,000.00`; one related request (same supplier) 20 days earlier for `35,000.00` | `HUMAN_REVIEW` | POL-004 | PROCUREMENT_OFFICER |
| C07 | same as C06, but the earlier request was 45 days ago | `CONTINUE` | none | none |
| C08 | `supplier_status = BLOCKED` | `BLOCK` | POL-005 | none |
| C09 | `supplier_status = NOT_APPROVED` | `HUMAN_REVIEW` | POL-005 | PROCUREMENT_OFFICER |
| C10 | no supplier named (`supplier_name` and `supplier_status` null) | `CONTINUE` | none | none |
| C11 | `item_category = WEAPONS` | `BLOCK` | POL-006 | none |
| C12 | `item_category = SOFTWARE` | `HUMAN_REVIEW` | POL-006 | IT_APPROVER |
| C13 | `budget_status = INSUFFICIENT` | `BLOCK` | POL-007 | none |
| C14 | `budget_status = NEEDS_FINANCE_APPROVAL` | `HUMAN_REVIEW` | POL-007 | FINANCE_APPROVER |
| C15 | `budget_status` missing | `HUMAN_REVIEW` | POL-007 | FINANCE_APPROVER |
| C16 | `proposed_priority = EMERGENCY` | `HUMAN_REVIEW` | POL-008 | SENIOR_MANAGER |
| C17 | total `1,200,000.00`, `supplier_status = BLOCKED`, `proposed_priority = EMERGENCY` | `BLOCK` | POL-002, POL-005, POL-008 | SENIOR_MANAGER (BLOCK still wins) |
| C18 | checkpoint `PRE_PO`, total `300,000.00`, `quotation_count = 1`, supplier `APPROVED` | `HUMAN_REVIEW` | POL-003 | PROCUREMENT_OFFICER |
| C19 | `extraction_status = FAILED` | `HUMAN_REVIEW` | POL-900 | PROCUREMENT_OFFICER |
| C20 | checkpoint `APPROVAL`, `acting_user_id = requester_user_id` | `BLOCK` | POL-009 | none |

Notes on specific cases:
- **C06:** 40,000 alone is under the 50,000 tier, but 40,000 + 35,000 = 75,000 crosses it. This is the split-purchase pattern.
- **C15:** `budget_status` missing is handled inside POL-007 (it defines its own missing-value behaviour), so POL-900 does not also fire.
- **C17:** the result lists all three rules so a reviewer sees every problem, but the outcome is `BLOCK` because of the blocked supplier. `required_approver_roles` = `SENIOR_MANAGER` (from POL-002 and POL-008, listed once); no role can override a `BLOCK`.

## 9. Open questions for the team

1. **Extraction reliability.** The original brief listed `extraction_confidence`. The project docs say a model's self-reported confidence is not calibrated unless evaluated, so this draft uses `extraction_status` (`VALID` / `INVALID` / `FAILED`) from schema validation instead, handled by POL-900. Should we add a check that every required field has quoted evidence from the request text?
2. **POL-007:** should `INSUFFICIENT` budget be `BLOCK` (this draft) or `HUMAN_REVIEW` (some organizations allow a budget transfer)?
3. **POL-008:** real emergency procedures often waive the quotation requirement with after-the-fact documentation. This draft waives nothing. Keep it that way for FYP-I?
4. **Price changes at `PRE_PO`:** if the selected quotation is higher than the amount approved at `INTAKE`, should POL-002 run again? Real systems usually re-approve above a tolerance (for example 10%).
5. **Required fields:** is `quantity` required for services (for example a one-off repair)? Should `needed_by_date` be required, given that the urgency module uses it?
6. **POL-004 history:** who builds `recent_requests` (the service layer, from Ghina's schema), and which request statuses count?
7. **Approver roles and the clarification loop:** the role names depend on the auth/role model (Q-004). A reviewer can also request clarification; does that count toward the 2-round limit (D-029)?
8. **Currency:** PKR only for the demo. Is that acceptable?

## 10. Notes for other modules (not policy engine work)

- **Ghina (extraction, workflow):** the engine expects `missing_fields` after the clarification loop, so the order should be extract → validate → clarify → urgency → policy engine. The engine also needs `submitted_at`, `requester_user_id` and `recent_requests` from the service layer.
- **Review service:** must call the engine at `APPROVAL` before recording an approval, so POL-009 is enforced on the server.
- **Evaluation (System A vs B):** the labelled cases in `FYP_MASTER_CONTEXT.md` §7 already have `expected_policy_decision` and `expected_triggered_rules`. Adding `expected_checkpoint` and `expected_required_roles` would let us score these too.

## 11. Sources (real-world basis)

- Approval tiers: [Mid and East Antrim Borough Council, Procurement Thresholds and Approval Limits](https://www.midandeastantrim.gov.uk/council/policies-and-documents/policies/procurement-strategy-policy/procurement-strategy-policy-page-5)
- Quotation bands: [Antrim and Newtownabbey Borough Council, Procurement Thresholds](https://antrimandnewtownabbey.gov.uk/getmedia/2c0e390e-8167-4518-a5b5-99d5da09fe29/Procurement-Thresholds-2022.docx.aspx); [University of Newcastle, Quotation Procedure](https://policies.newcastle.edu.au/document/view-current.php?id=84); [Fiji Ministry of Finance, Procurement up to $50,000](https://www.finance.gov.fj/procurement-of-purchases-up-to-50000-policy-2014)
- Split purchases: [University of Utah, Small Purchase Policy](https://fbs.admin.utah.edu/download/bpag/BPAG_purchaing.pdf); [NationGraph, Procurement Threshold](https://www.nationgraph.com/glossary/procurement-threshold); [Carolina Journal, audit report on split purchases](https://www.carolinajournal.com/?p=72227)
- Restricted categories: [LSU, Purchases Not Exceeding $10,000 (Special Authorizations List)](https://wct.lsu.edu/administration/ofa/procurement/a-z-policies-procedures/notexceed.php)
- Emergency procurement: [Hawaii State Procurement Office, Emergency Procurement](https://spo.hawaii.gov/wp-content/uploads/2021/08/HI-SPO-110_E-ModuleTranscript.pdf); [Austin Peay State University, Emergency Purchases](https://www.apsu.edu/procurement/employees/Emergency_Purchases_Formatted.pdf)
- Segregation of duties: [CSU San Bernardino, Requisition Approval Authorization](https://www.csusb.edu/sites/csusb/files/Requisition_Approval_Authorization_Delegation_20180215_0.pdf); [Lapasar, Segregation of Duties](https://lapasar.com/glossary/segregation-of-duties)
- Commercial platform practice (approval routing, budget, preferred supplier and category checks): [Coupa workflow explained](https://startupik.com/coupa-workflow-explained-procurement-process-step-by-step/); [SAP Joule agent for Ariba Intake Management](https://erp.today/sap-joule-agents-ariba-fieldglass-procurement-automation-2026/)
