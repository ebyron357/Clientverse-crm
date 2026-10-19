"""Proof: what was recovered, and the records that say so.

A recovery product's hardest problem is not detecting opportunities or sending
messages. It is being believed. The buyer's question is never "how many cases did you
open?" -- it is "show me the money you say you got back, and show me why it was you."

So this module assembles two views, and both are built to be checked rather than
admired:

* **Case proof** -- one recovery, end to end. What was detected and why, what record it
  came from, what was planned, who approved what, which messages were drafted, which
  were actually sent, what came back, what the outcome was, and on what basis (if any)
  this system claims credit. Every figure names the record it came from.
* **Portfolio** -- the same thing in aggregate, with the counts that make the headline
  numbers interpretable: how many cases were detected versus worked, how many messages
  were drafted versus sent, how many outcomes were attributed versus not.

Three rules the surface never bends:

1. **Potential and confirmed are never one figure.** Potential value is what a case
   might be worth. Confirmed value is money a record says arrived. They are reported
   under different names, and no arithmetic here ever adds one to the other.
2. **Drafted is not sent.** Both are counted, separately, always. A product that
   reports "messages sent" and quietly means "messages composed" is not reporting.
3. **Nothing is computed that cannot be traced.** Every number on the portfolio view
   resolves to a query over records the buyer can open.

Currency is never summed across currencies. £40,000 plus $40,000 is not 80,000 of
anything.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import approval_queue
import attribution
import conversations as conversation_service
import crm_core
import recovery_case as recovery_case_service
import recovery_strategy as recovery_strategy_service

APPROVALS = "approvals"

# The portfolio reads at most this many cases. Past it the report says it is truncated
# rather than presenting a partial count as the whole.
PORTFOLIO_SCAN_LIMIT = int(os.environ.get("RECOVERY_PORTFOLIO_SCAN_LIMIT", "20000"))

# Message states, grouped by what they actually mean for a buyer reading a report.
DRAFTED_STATES = (conversation_service.DRAFT, conversation_service.PENDING_APPROVAL,
                  conversation_service.APPROVED, conversation_service.SENDING)
SENT_STATES = (conversation_service.SENT, conversation_service.DELIVERED)
UNSENT_STATES = (conversation_service.BLOCKED, conversation_service.FAILED)
UNKNOWN_STATES = (conversation_service.OUTCOME_UNKNOWN,)


def _public(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


async def case_proof(db: Any, tenant_id: str, case_id: str) -> Optional[dict]:
    """Everything behind one recovery case, with the records each claim rests on."""
    case = await db[recovery_case_service.COLLECTION].find_one(
        {"tenant_id": tenant_id, "id": case_id}, {"_id": 0})
    if not case:
        return None

    # The case's own plan first. Strategies did not carry `recovery_case_id` until it was
    # added, so a lookup on that field alone found no plan for any older case.
    strategy = None
    if case.get("plan_reference"):
        strategy = await db[recovery_strategy_service.COLLECTION].find_one(
            {"tenant_id": tenant_id, "id": case["plan_reference"]}, {"_id": 0})
    if strategy is None:
        strategy = await db[recovery_strategy_service.COLLECTION].find_one(
            {"tenant_id": tenant_id, "recovery_case_id": case_id}, {"_id": 0},
            sort=[("created_at", -1)])

    conversations = await db[conversation_service.CONVERSATIONS].find(
        {"tenant_id": tenant_id, "recovery_case_id": case_id}, {"_id": 0}).to_list(50)
    conversation_ids = [conversation["id"] for conversation in conversations]

    messages = []
    if conversation_ids:
        messages = await db[conversation_service.MESSAGES].find(
            {"tenant_id": tenant_id, "conversation_id": {"$in": conversation_ids}},
            {"_id": 0}).sort("created_at", 1).to_list(500)

    outbound = [m for m in messages if m.get("direction") == conversation_service.OUTBOUND]
    inbound = [m for m in messages if m.get("direction") == conversation_service.INBOUND]
    sent = [m for m in outbound if m.get("status") in SENT_STATES]

    approvals = await db[APPROVALS].find(
        {"tenant_id": tenant_id,
         "$or": [{"subject_id": case_id},
                 {"subject_id": {"$in": [m["id"] for m in outbound]}} if outbound
                 else {"subject_id": case_id}]},
        {"_id": 0}).sort("created_at", 1).to_list(200)

    tasks = await db.tasks.find(
        {"tenant_id": tenant_id, "recovery_case_id": case_id}, {"_id": 0}).to_list(200)

    entries = await attribution.list_entries(db, tenant_id, case_id=case_id, limit=100)
    # A claim the case never accepted is not a claim (see `is_counted_as_attributed`).
    attributed = [entry for entry in entries if attribution.is_counted_as_attributed(entry)]

    meetings = []
    if case.get("contact_id"):
        meetings = await db.crm_meetings.find(
            {"tenant_id": tenant_id, "contact_ids": case["contact_id"]},
            {"_id": 0}).sort("ts", -1).to_list(50)

    source_record = None
    for field, collection in recovery_case_service.REFERENCE_COLLECTIONS.items():
        if case.get(field):
            source_record = {
                "field": field, "collection": collection, "id": case[field],
                "record": _public(await db[collection].find_one(
                    {"tenant_id": tenant_id, "id": case[field]}, {"_id": 0})),
            }
            break

    owner = (case.get("evidence") or {}).get("owner")
    owner_names = await crm_core.display_names(db, tenant_id, [owner]) if owner else {}

    return {
        "case": {
            "id": case["id"],
            "title": case.get("title"),
            "state": case.get("state"),
            "owner": owner,
            # The teammate's name for a person reading the case; the address stays the key.
            "owner_name": owner_names.get(owner) if owner else None,
            "source": case.get("source"),
            "source_event_id": case.get("source_event_id"),
            "source_is_internal": case.get("source_is_internal"),
            "detected_at": case.get("occurred_at") or case.get("created_at"),
            "reason_detected": case.get("reason"),
            "external_identity": case.get("external_identity"),
            "created_at": case.get("created_at"),
            "updated_at": case.get("updated_at"),
            # Why a closed case closed, and who closed it -- "answered elsewhere", "gave
            # up" and "test lead" all leave open potential and must not look alike.
            "close_reason": case.get("close_reason"),
            "close_note": case.get("close_note"),
            "closed_at": case.get("closed_at"),
            "closed_by": case.get("closed_by"),
        },
        "source_record": source_record,
        # Named at length, and never combined. A figure called "value" would be read as
        # whichever of the two flatters the report.
        "value": {
            "currency": case.get("currency") or recovery_case_service.DEFAULT_CURRENCY,
            "potential_value": case.get("potential_value"),
            # Where the estimate came from, in words ("opportunity value on record", "web
            # form estimate"), recorded on the case when the value was set.
            "potential_value_basis": (case.get("potential_value_basis")
                                      or (case.get("evidence") or {}).get("value_basis")),
            "potential_value_note": (case.get("evidence") or {}).get("value_rejected"),
            "confirmed_recovered_value": case.get("confirmed_value"),
            # The money's own currency: a missed call (no value, so USD by default) can
            # lead to a deal won in pounds.
            "confirmed_currency": (recovery_case_service.confirmed_currency_of(case)
                                   if case.get("confirmed_value") is not None else None),
            "confirmed_recovered_value_evidence": case.get("confirmed_value_evidence"),
            "note": ("Potential value is what this opportunity might be worth. Confirmed "
                     "recovered value is money a record says arrived. They are different "
                     "figures and are never added together."),
        },
        "strategy": _public(strategy),
        "actions_taken": {
            "internal_tasks": tasks,
            "steps": (strategy or {}).get("steps") or [],
        },
        "approvals": approvals,
        "communications": {
            "conversations": conversations,
            "messages_drafted": len(outbound),
            "messages_actually_sent": len(sent),
            "messages_blocked_or_failed": len(
                [m for m in outbound if m.get("status") in UNSENT_STATES]),
            "messages_outcome_unknown": len(
                [m for m in outbound if m.get("status") in UNKNOWN_STATES]),
            "replies_received": len(inbound),
            # The full records, so a reader can open any one of them.
            "outbound": outbound,
            "inbound": inbound,
        },
        "meetings": meetings,
        "outcome": {
            "final_state": case.get("state"),
            "is_terminal": case.get("state") in recovery_case_service.TERMINAL_STATES,
            # Recovered whenever a confirmed value is included -- a recovered case that
            # was later closed is still a recovery.
            "recovered": isinstance(case.get("confirmed_value"), (int, float)),
            "close_reason": case.get("close_reason"),
        },
        "attribution": {
            "entries": entries,
            "claimed": bool(attributed),
            "basis": attributed[0]["basis"] if attributed else None,
            "evidence": attributed[0]["evidence"] if attributed else [],
            "reason": (attributed[0]["reason"] if attributed
                       else (entries[0]["reason"] if entries else
                             "No outcome has been recorded against this case.")),
        },
        "history": case.get("history") or [],
    }


async def portfolio(db: Any, tenant_id: str) -> dict:
    """The aggregate view, with the denominators that make the headline honest."""
    cases = await db[recovery_case_service.COLLECTION].find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "state": 1, "close_reason": 1, "plan_reference": 1},
    ).to_list(PORTFOLIO_SCAN_LIMIT + 1)
    cases_truncated = len(cases) > PORTFOLIO_SCAN_LIMIT
    cases = cases[:PORTFOLIO_SCAN_LIMIT]

    by_state: dict[str, int] = {}
    closed_by_reason: dict[str, int] = {}
    for case in cases:
        state = case.get("state") or recovery_case_service.DETECTED
        by_state[state] = by_state.get(state, 0) + 1
        if state == recovery_case_service.CLOSED:
            reason = case.get("close_reason") or "unspecified"
            closed_by_reason[reason] = closed_by_reason.get(reason, 0) + 1
    # Each underlying opportunity once, however many cases point at it.
    potential = await recovery_case_service.open_potential(db, tenant_id)
    confirmed = await recovery_case_service.confirmed_totals(db, tenant_id)

    case_ids = [case["id"] for case in cases]
    conversations = await db[conversation_service.CONVERSATIONS].find(
        {"tenant_id": tenant_id, "recovery_case_id": {"$in": case_ids}},
        {"_id": 0, "id": 1}).to_list(PORTFOLIO_SCAN_LIMIT + 1) if case_ids else []
    conversations_truncated = len(conversations) > PORTFOLIO_SCAN_LIMIT
    conversation_ids = [conversation["id"] for conversation in conversations]

    drafted = sent = blocked = unknown = replies = 0
    if conversation_ids:
        scope = {"tenant_id": tenant_id, "conversation_id": {"$in": conversation_ids}}
        drafted = await db[conversation_service.MESSAGES].count_documents(
            {**scope, "direction": conversation_service.OUTBOUND})
        sent = await db[conversation_service.MESSAGES].count_documents(
            {**scope, "direction": conversation_service.OUTBOUND,
             "status": {"$in": list(SENT_STATES)}})
        blocked = await db[conversation_service.MESSAGES].count_documents(
            {**scope, "direction": conversation_service.OUTBOUND,
             "status": {"$in": list(UNSENT_STATES)}})
        unknown = await db[conversation_service.MESSAGES].count_documents(
            {**scope, "direction": conversation_service.OUTBOUND,
             "status": {"$in": list(UNKNOWN_STATES)}})
        replies = await db[conversation_service.MESSAGES].count_documents(
            {**scope, "direction": conversation_service.INBOUND})

    # Approval requests are `requested` while undecided; the old count looked for
    # "pending", which the approval queue never writes, and so always read zero. Counted
    # here: undecided requests for recovery strategies, and for messages drafted on a
    # recovery case.
    pending_messages = await db[conversation_service.MESSAGES].find(
        {"tenant_id": tenant_id, "conversation_id": {"$in": conversation_ids},
         "status": conversation_service.PENDING_APPROVAL},
        {"_id": 0, "id": 1}).to_list(5000) if conversation_ids else []
    awaiting_approval = await db[APPROVALS].count_documents(
        {"tenant_id": tenant_id, "status": approval_queue.REQUESTED,
         "$and": [
             {"$or": [{"subject_type": "recovery_strategy"},
                      {"subject_type": "communication_message",
                       "subject_id": {"$in": [m["id"] for m in pending_messages]}}]},
             # A request past its expiry can no longer be decided, so it is not awaiting.
             approval_queue._not_lapsed_criteria(),
         ]})

    attribution_totals = await attribution.totals(db, tenant_id)
    timing = await attribution.time_to_recovery(db, tenant_id)

    detected = len(cases)
    # "Worked" means something was planned for it. A case closed by reconciliation before
    # anything was planned -- the enquiry was answered by someone else -- was found and
    # closed, not worked, so a closed or failed case only counts if it had a plan.
    worked = sum(1 for case in cases
                 if case.get("state") not in (None, recovery_case_service.DETECTED)
                 and (case.get("state") not in (recovery_case_service.CLOSED,
                                                recovery_case_service.FAILED)
                      or case.get("plan_reference")))

    return {
        "tenant_id": tenant_id,
        "cases": {
            "detected": detected,
            # A case sitting in `detected` has been found and nothing more, and counting
            # it as worked would be the easiest lie on this page.
            "worked": worked,
            "not_yet_worked": by_state.get(recovery_case_service.DETECTED, 0),
            "awaiting_approval": by_state.get(recovery_case_service.AWAITING_APPROVAL, 0),
            "executing": by_state.get(recovery_case_service.EXECUTING, 0),
            "engaged": by_state.get(recovery_case_service.ENGAGED, 0),
            # Every case whose confirmed value is included in the recovered figure:
            # `recovered`, and `recovered` then `closed`, alike -- once per sale.
            "recovered": confirmed["recovered_cases"],
            "closed": by_state.get(recovery_case_service.CLOSED, 0),
            "closed_by_reason": closed_by_reason,
            "failed": by_state.get(recovery_case_service.FAILED, 0),
            "by_state": by_state,
            "truncated": cases_truncated,
            "scan_limit": PORTFOLIO_SCAN_LIMIT,
        },
        "approvals": {"pending": awaiting_approval},
        "messages": {
            "drafted": drafted,
            "actually_sent": sent,
            "blocked_or_failed": blocked,
            "outcome_unknown": unknown,
            "replies_received": replies,
            "truncated": conversations_truncated,
            "note": ("Drafted counts every outbound message this system composed. "
                     "Actually sent counts only those a provider accepted."),
        },
        "revenue": {
            # Three separate figures that are never combined.
            "potential_value_open_by_currency": potential["by_currency"],
            "attributed_recovered_value_by_currency":
                attribution_totals["attributed_recovered_value_by_currency"],
            "unattributed_outcome_value_by_currency":
                attribution_totals["unattributed_outcome_value_by_currency"],
            "currencies": sorted(set(potential["by_currency"])
                                 | set(attribution_totals["attributed_recovered_value_by_currency"])
                                 | set(attribution_totals["unattributed_outcome_value_by_currency"])),
            # What open potential is made of, so a reader can see what it leaves out.
            "open_cases": potential["open_cases"],
            "open_cases_without_value": potential["cases_without_value"],
            "open_opportunity_groups": potential["opportunity_groups"],
            "open_cases_collapsed": potential["cases_collapsed"],
            "potential_truncated": potential["truncated"],
            "outcomes_truncated": attribution_totals["truncated"],
            "note": ("Open potential is an estimate of what un-recovered cases might be "
                     "worth, counting each underlying opportunity once however many cases "
                     "point at it; cases with no value yet (a missed call, say) add "
                     "nothing to it and are counted separately. Attributed recovered value "
                     "is money a record says arrived on a case where outreach demonstrably "
                     "reached the client and the case confirmed it. Unattributed outcomes "
                     "are real revenue this system does not claim to have caused. Each "
                     "sale is counted once."),
        },
        "attribution": {
            "entries": attribution_totals["entries"],
            "attributed": attribution_totals["attributed_entries"],
            "unattributed": attribution_totals["unattributed_entries"],
            "attributed_but_unconfirmed": attribution_totals["attributed_but_unconfirmed_entries"],
            "duplicate_entries_excluded": attribution_totals["duplicate_entries_excluded"],
            "by_basis": attribution_totals["by_basis"],
        },
        "time_to_recovery": timing,
    }


async def traceability(db: Any, tenant_id: str) -> dict:
    """Where each portfolio figure comes from.

    Shipped as part of the API rather than kept in documentation, because a metric a
    buyer cannot resolve to a query is a metric they have to take on trust -- and trust
    is the thing this surface is supposed to be earning.
    """
    return {
        "cases.detected": f"{recovery_case_service.COLLECTION} where tenant_id matches",
        "cases.worked": (f"{recovery_case_service.COLLECTION} in any state past "
                         f"'{recovery_case_service.DETECTED}', counting a closed or failed "
                         "case only if it had a plan_reference"),
        "cases.recovered": (f"{recovery_case_service.COLLECTION} with a numeric "
                            "confirmed_value, once per sale named in its confirmation "
                            "evidence"),
        "cases.closed_by_reason": (f"{recovery_case_service.COLLECTION} in state "
                                   f"'{recovery_case_service.CLOSED}', grouped by "
                                   "close_reason"),
        "approvals.pending": (f"{APPROVALS} where status = '{approval_queue.REQUESTED}', not "
                              "past expires_at, for a recovery strategy or for a message "
                              "awaiting approval on a recovery conversation"),
        "messages.drafted": (f"{conversation_service.MESSAGES} where direction = "
                             f"'{conversation_service.OUTBOUND}' on a conversation "
                             "linked to a recovery case"),
        "messages.actually_sent": (f"the same, restricted to status in "
                                   f"{list(SENT_STATES)}"),
        "messages.replies_received": (f"{conversation_service.MESSAGES} where direction "
                                      f"= '{conversation_service.INBOUND}'"),
        "revenue.potential_value_open_by_currency": (
            f"potential_value over {recovery_case_service.COLLECTION} in an open state, "
            "grouped into opportunities (by opportunity_id; else by contact_id, joined to "
            "that contact's deal when the contact is on exactly one open deal; else the case "
            "itself -- an unresolved phone number or email is not a grouping key) and taking "
            "ONE value per opportunity -- the most authoritative, most recent -- then summed "
            "per currency"),
        "revenue.open_cases_without_value": (
            "open cases with no usable potential_value; they add nothing to open potential"),
        "revenue.open_cases_collapsed": (
            "open cases whose value was not added because another case in the same "
            "opportunity group already represents it"),
        "revenue.attributed_recovered_value_by_currency": (
            f"sum of outcome.amount over {attribution.COLLECTION} where claim = "
            f"'{attribution.CLAIM_ATTRIBUTED}' and the case accepted the confirmation, "
            "one entry per sale_key, grouped by currency"),
        "revenue.unattributed_outcome_value_by_currency": (
            f"the same over every other entry (claim = '{attribution.CLAIM_UNATTRIBUTED}', "
            "or a claim the case never confirmed)"),
        "time_to_recovery": (
            "days between a case's detection and the outcome date on its attributed "
            f"{attribution.COLLECTION} entry, over entries carrying both dates"),
    }
