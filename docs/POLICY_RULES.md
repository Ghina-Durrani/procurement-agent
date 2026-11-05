# Policy Rules (draft)

**Status: PROPOSED.** Draft for team review; nothing here is final until Ghina and Haya agree. All amounts are demo values, not real company limits.

**Author:** Maira · **Created:** 2026-11-05 · **Answers:** Q-007 in `DECISIONS.md`

## 1. What this is

The policy engine is plain Python code that checks a purchase request against the company's rules. It does not use AI and does not talk to the database: other parts of the system collect the information and hand it over.

The rules are based on standard checks used in real procurement policies (sources in section 9). Each organization can change the numbers and lists.

## 2. The three answers

For every request the engine gives exactly one answer:

| Answer | Meaning |
|---|---|
| `CONTINUE` | No rule has a problem; the request can move on |
| `HUMAN_REVIEW` | A person must look at it (the engine says who) |
| `BLOCK` | A rule forbids it |

**How the final answer is chosen:** every rule is checked. If any rule says `BLOCK`, the answer is `BLOCK`. Otherwise, if any rule says `HUMAN_REVIEW`, the answer is `HUMAN_REVIEW`. Only if no rule fires is the answer `CONTINUE`. The engine always lists every rule that fired and why.

**When in doubt, never CONTINUE.** If information is missing or broken, or the engine hits an error, the answer is `HUMAN_REVIEW` (rule POL-900).

## 3. When the rules run

The engine runs at three moments. Not every rule runs every time.

| Moment | Code name | Rules checked |
|---|---|---|
| A request arrives (after the AI has read it and asked the requester about missing details) | `INTAKE` | POL-001, 002, 004, 005, 006, 007, 008 |
| Quotations are collected and a supplier is chosen, before the purchase order | `PRE_PO` | POL-003, 005 |
| Someone clicks approve | `APPROVAL` | POL-009 |

POL-900 can fire at any moment.

## 4. Information the engine needs

The engine does not collect any of this itself. Each item is given to it by another part of the system.

| Field | What it means | Example | Who provides it |
|---|---|---|---|
| `checkpoint` | Which moment this is (section 3) | `INTAKE` | Workflow |
| `estimated_total` | Total amount of the request (or of the chosen quotation at `PRE_PO`) | `120000.00` | AI reading the message / quotation |
| `currency` | Currency of the amount | `PKR` | AI reading the message / quotation |
| `item_category` | Type of item | `IT_HARDWARE` | AI reading the message (checked against a list, never trusted blindly) |
| `missing_fields` | Required details still missing after asking the requester | `["quantity"]` | Validation step |
| `extraction_status` | Did the AI read the message properly? | `VALID`, `INVALID` or `FAILED` | AI reading step |
| `supplier_name` | Supplier mentioned or chosen | `TechZone` | AI reading the message / supplier choice |
| `supplier_status` | Is the supplier approved? | `APPROVED`, `NOT_APPROVED` or `BLOCKED` | Database (supplier list) |
| `budget_status` | Is there money for it? | `AVAILABLE`, `NEEDS_FINANCE_APPROVAL` or `INSUFFICIENT` | Finance check |
| `proposed_priority` | How urgent it seems | `NORMAL`, `HIGH_PRIORITY` or `EMERGENCY` | Urgency check |
| `quotation_count` | How many supplier quotes were collected | `3` | Quotation step (only at `PRE_PO`) |
| `requester_user_id` | Who made the request | user ID | Login system |
| `acting_user_id` | Who is clicking approve | user ID | Login system (only at `APPROVAL`) |
| `submitted_at` | When the request was made | `2026-11-05 10:00` | Request record |
| `recent_requests` | The same person's requests from the last 30 days (date, amount, supplier, category, status) | list | Database |

Amounts are always exact decimals (`Decimal`), never rounded numbers.

**What the engine gives back:** the final answer, the list of rules that fired with a reason for each, which roles must approve, and the version of the settings used (so any old decision can be checked again later).

**Where the numbers live:** all limits and lists (section 6) are kept in a settings file per organization, not written into the code. When a number changes, a new version is saved.

## 5. The rules

### POL-001: Is anything missing?
- **When:** request arrives
- **Needs:** `missing_fields`
- **Rule:** if a required detail (item, quantity, amount, currency, reason for buying) is still missing after the requester was asked up to 2 times → `HUMAN_REVIEW` by a Procurement Officer.
- **Reason shown:** "Required detail still missing: quantity."
- **Based on:** a request cannot be approved without these basics.

### POL-002: Does it need a boss's approval?
- **When:** request arrives
- **Needs:** `estimated_total`
- **Rule:** up to 50,000 → no approval needed. 50,000.01 to 500,000 → `HUMAN_REVIEW` by a Manager. Above 500,000 → `HUMAN_REVIEW` by Senior Management.
- **Reason shown:** "Amount 1,200,000 PKR needs Senior Management approval."
- **Based on:** approval limits by seniority (delegation of authority).

### POL-003: Did we compare prices?
- **When:** before the purchase order
- **Needs:** `estimated_total`, `quotation_count`
- **Rule:** up to 100,000 needs 1 quote; above 100,000 needs 3. Fewer → `HUMAN_REVIEW` by a Procurement Officer, who must record why.
- **Reason shown:** "3 quotations required, 1 received."
- **Based on:** minimum quotation rules in procurement policies.

### POL-004: Is one big purchase being split into small ones?
- **When:** request arrives
- **Needs:** `estimated_total`, `supplier_name`, `item_category`, `submitted_at`, `recent_requests`
- **Rule:** take the same person's requests from the last 30 days with the same supplier (or the same category, if no supplier is named). Ignore rejected or withdrawn ones. If this request alone is under a limit (50,000, 100,000 or 500,000) but together with those requests it goes over → `HUMAN_REVIEW` by a Procurement Officer.
- **Reason shown:** "Possible split purchase: combined total 75,000 PKR is over the 50,000 limit."
- **Based on:** splitting orders to avoid limits is forbidden and is a common audit finding. An AI reading one message cannot see past requests; this rule can.

### POL-005: Do we trust this supplier?
- **When:** request arrives, and again before the purchase order
- **Needs:** `supplier_name`, `supplier_status`
- **Rule:** blocked supplier → `BLOCK`. Supplier not on the approved list (or not found) → `HUMAN_REVIEW` by a Procurement Officer. Approved → fine. No supplier named yet when the request arrives → fine. No supplier chosen before the purchase order → `HUMAN_REVIEW` (POL-900).
- **Reason shown:** "Supplier 'X' is on the blocked list."
- **Based on:** approved and blocked supplier lists.

### POL-006: Are we allowed to buy this item?
- **When:** request arrives
- **Needs:** `item_category`
- **Rule:** prohibited (weapons, alcohol, personal items, gift cards) → `BLOCK`. Needs an expert's sign-off (software → IT, chemicals → Health & Safety, vehicles → Senior Management) → `HUMAN_REVIEW` by that person. Normal categories → fine. Unknown or missing category → `HUMAN_REVIEW` by a Procurement Officer.
- **Reason shown:** "Category 'SOFTWARE' needs IT sign-off."
- **Based on:** lists of purchases that need extra approval or are not allowed.

### POL-007: Is there money in the budget?
- **When:** request arrives
- **Needs:** `budget_status`
- **Rule:** not enough budget → `BLOCK`. Finance must approve, or the budget could not be checked → `HUMAN_REVIEW` by Finance. Budget available → fine.
- **Reason shown:** "Insufficient budget for this request."
- **Based on:** spending must come from an approved budget. Being within budget does not cancel the other rules.

### POL-008: Is it an emergency?
- **When:** request arrives
- **Needs:** `proposed_priority`
- **Rule:** emergency → `HUMAN_REVIEW` by Senior Management, who confirm it is a real emergency. Normal or high priority → fine. An emergency never skips any other rule and never makes the answer `CONTINUE`.
- **Reason shown:** "Emergency request; Senior Management must confirm."
- **Based on:** emergency purchases still need a named approver; poor planning is not an emergency.

### POL-009: Is someone approving their own request?
- **When:** someone clicks approve
- **Needs:** `requester_user_id`, `acting_user_id`
- **Rule:** if they are the same person → `BLOCK` that approval. The request stays waiting for someone else.
- **Reason shown:** "You cannot approve your own request."
- **Based on:** segregation of duties: the requester and the approver must be different people.

### POL-900: Did something go wrong?
- **When:** any time
- **Rule:** → `HUMAN_REVIEW` by a Procurement Officer if any of these happen:
  - the AI failed to read the message (`extraction_status` is not `VALID`)
  - the currency is not PKR
  - the amount is zero or negative
  - information a rule needs is missing (and the rule does not say what to do without it)
  - the settings are missing or broken, or a rule crashes
- **Reason shown:** names the problem, e.g. "Currency 'USD' is not accepted."
- **Based on:** the project rule "fail closed": never continue when unsure.

## 6. Demo numbers and lists

**Demo values only.** Used for testing and the demo; each organization sets its own.

| Setting | Demo value |
|---|---|
| Currency | PKR only |
| Required details | item description, quantity, amount, currency, reason for buying |
| Approval limits (POL-002) | up to 50,000: none · up to 500,000: Manager · above: Senior Management |
| Quotations (POL-003) | up to 100,000: 1 · above: 3 |
| Split-purchase window (POL-004) | 30 days; limits watched: 50,000, 100,000, 500,000 |
| Normal categories (POL-006) | office supplies, IT hardware, furniture, maintenance services, cleaning supplies, printing, travel |
| Need sign-off (POL-006) | software (IT), hazardous chemicals (Health & Safety), vehicles (Senior Management) |
| Prohibited (POL-006) | weapons, alcohol, personal items, gift cards |
| Roles | Procurement Officer, Manager, Senior Management, Finance, IT, Health & Safety (names to be fixed with the login/roles design) |

## 7. Example cases

These become the tests when the rules are written in code.

**Starting request** (each case changes only what is listed): request arrives, AI read it fine, nothing missing, 30,000 PKR, office supplies, approved supplier, normal priority, budget available, no recent requests.

| Case | What changes | Answer | Rules fired | Who reviews |
|---|---|---|---|---|
| C01 | nothing | `CONTINUE` | none | none |
| C02 | quantity still missing after 2 tries | `HUMAN_REVIEW` | POL-001 | Procurement Officer |
| C03 | amount exactly 50,000.00 | `CONTINUE` | none | none |
| C04 | amount 50,000.01 | `HUMAN_REVIEW` | POL-002 | Manager |
| C05 | amount 1,200,000 | `HUMAN_REVIEW` | POL-002 | Senior Management |
| C06 | amount 40,000; same person, same supplier, 35,000 twenty days ago | `HUMAN_REVIEW` | POL-004 | Procurement Officer |
| C07 | same as C06 but 45 days ago | `CONTINUE` | none | none |
| C08 | supplier blocked | `BLOCK` | POL-005 | none |
| C09 | supplier not approved | `HUMAN_REVIEW` | POL-005 | Procurement Officer |
| C10 | no supplier named | `CONTINUE` | none | none |
| C11 | category weapons | `BLOCK` | POL-006 | none |
| C12 | category software | `HUMAN_REVIEW` | POL-006 | IT |
| C13 | budget insufficient | `BLOCK` | POL-007 | none |
| C14 | budget needs finance approval | `HUMAN_REVIEW` | POL-007 | Finance |
| C15 | budget could not be checked | `HUMAN_REVIEW` | POL-007 | Finance |
| C16 | emergency | `HUMAN_REVIEW` | POL-008 | Senior Management |
| C17 | 1,200,000 + blocked supplier + emergency | `BLOCK` | POL-002, POL-005, POL-008 | (Senior Management listed, but BLOCK wins) |
| C18 | before purchase order: 300,000 with 1 quote | `HUMAN_REVIEW` | POL-003 | Procurement Officer |
| C19 | AI failed to read the message | `HUMAN_REVIEW` | POL-900 | Procurement Officer |
| C20 | requester tries to approve own request | `BLOCK` | POL-009 | none |

## 8. Questions for the team

1. **Not enough budget (POL-007):** `BLOCK` (this draft) or `HUMAN_REVIEW` so a budget transfer can be considered?
2. **Emergencies and quotes:** real policies often let emergencies skip the 3-quote rule if the reason is recorded later. This draft does not allow that. Keep it strict?
3. **AI reliability:** the first brief suggested an AI "confidence" score. Project docs say that score cannot be trusted unless tested, so this draft only checks whether the AI's output passed validation (`extraction_status`). Agreed?
4. **Required details:** is quantity required for services (e.g. a one-off repair)?

Things that depend on other work (no decision needed from this document): exact value names like `HIGH_PRIORITY` will follow the database design (Q-006); role names will follow the login/roles design (Q-004).

## 9. Sources

- Approval limits: [Mid and East Antrim Borough Council](https://www.midandeastantrim.gov.uk/council/policies-and-documents/policies/procurement-strategy-policy/procurement-strategy-policy-page-5)
- Quotations: [Antrim and Newtownabbey Borough Council](https://antrimandnewtownabbey.gov.uk/getmedia/2c0e390e-8167-4518-a5b5-99d5da09fe29/Procurement-Thresholds-2022.docx.aspx); [University of Newcastle](https://policies.newcastle.edu.au/document/view-current.php?id=84)
- Split purchases: [University of Utah](https://fbs.admin.utah.edu/download/bpag/BPAG_purchaing.pdf); [Carolina Journal audit report](https://www.carolinajournal.com/?p=72227)
- Restricted categories: [LSU Special Authorizations List](https://wct.lsu.edu/administration/ofa/procurement/a-z-policies-procedures/notexceed.php)
- Emergencies: [Hawaii State Procurement Office](https://spo.hawaii.gov/wp-content/uploads/2021/08/HI-SPO-110_E-ModuleTranscript.pdf); [Austin Peay State University](https://www.apsu.edu/procurement/employees/Emergency_Purchases_Formatted.pdf)
- Segregation of duties: [CSU San Bernardino](https://www.csusb.edu/sites/csusb/files/Requisition_Approval_Authorization_Delegation_20180215_0.pdf)
- Commercial practice: [Coupa workflow](https://startupik.com/coupa-workflow-explained-procurement-process-step-by-step/); [SAP Ariba intake agent](https://erp.today/sap-joule-agents-ariba-fieldglass-procurement-automation-2026/)
