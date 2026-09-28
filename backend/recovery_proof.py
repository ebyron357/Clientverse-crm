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

from typing import Any, Optional

import attribution
import conversations as conversation_service
import recovery_case as recovery_case_service
import recovery_strategy as recovery_strategy_service

APPROVALS = "approvals"

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
    attributed = [entry for entry in entries
                  if entry.get("claim") == attribution.CLAIM_ATTRIBUTED]

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

    return {
        "case": {
            "id": case["id"],
            "title": case.get("title"),
            "state": case.get("state"),
            "owner": (case.get("evidence") or {}).get("owner"),
            "source": case.get("source"),
            "source_event_id": case.get("source_event_id"),
            "source_is_internal": case.get("source_is_internal"),
            "detected_at": case.get("occurred_at") or case.get("created_at"),
            "reason_detected": case.get("reason"),
            "external_identity": case.get("external_identity"),
            "created_at": case.get("created_at"),
            "updated_at": case.get("updated_at"),
        },
        "source_record": source_record,
        # Named at length, and never combined. A figure called "value" would be read as
        # whichever of the two flatters the report.
        "value": {
            "currency": case.get("currency") or recovery_case_service.DEFAULT_CURRENCY,
            "potential_value": case.get("potential_value"),
            "potential_value_basis": (case.get("evidence") or {}).get("value_basis"),
            "confirmed_recovered_value": case.get("confirmed_value"),
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
            "recovered": case.get("state") == recovery_case_service.RECOVERED,
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
        {"tenant_id": tenant_id}, {"_id": 0}).to_list(20000)

    by_state: dict[str, int] = {}
    potential_open: dict[str, float] = {}
    for case in cases:
        state = case.get("state") or recovery_case_service.DETECTED
        by_state[state] = by_state.get(state, 0) + 1
        if state in recovery_case_service.OPEN_STATES and isinstance(
                case.get("potential_value"), (int, float)):
            currency = case.get("currency") or recovery_case_service.DEFAULT_CURRENCY
            potential_open[currency] = round(
                potential_open.get(currency, 0.0) + float(case["potential_value"]), 2)

    case_ids = [case["id"] for case in cases]
    conversations = await db[conversation_service.CONVERSATIONS].find(
        {"tenant_id": tenant_id, "recovery_case_id": {"$in": case_ids}},
        {"_id": 0, "id": 1}).to_list(20000) if case_ids else []
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

    awaiting_approval = await db[APPROVALS].count_documents(
        {"tenant_id": tenant_id, "status": "pending"})

    attribution_totals = await attribution.totals(db, tenant_id)
    timing = await attribution.time_to_recovery(db, tenant_id)

    detected = len(cases)
    worked = sum(by_state.get(state, 0) for state in
                 (recovery_case_service.PLANNED, recovery_case_service.AWAITING_APPROVAL,
                  recovery_case_service.APPROVED, recovery_case_service.EXECUTING,
                  recovery_case_service.ENGAGED, recovery_case_service.RECOVERED,
                  recovery_case_service.CLOSED, recovery_case_service.FAILED))

    return {
        "tenant_id": tenant_id,
        "cases": {
            "detected": detected,
            # "Worked" means something was planned for it. A case sitting in `detected`
            # has been found and nothing more, and counting it as worked would be the
            # easiest lie on this page.
            "worked": worked,
            "not_yet_worked": by_state.get(recovery_case_service.DETECTED, 0),
            "awaiting_approval": by_state.get(recovery_case_service.AWAITING_APPROVAL, 0),
            "executing": by_state.get(recovery_case_service.EXECUTING, 0),
            "engaged": by_state.get(recovery_case_service.ENGAGED, 0),
            "recovered": by_state.get(recovery_case_service.RECOVERED, 0),
            "closed": by_state.get(recovery_case_service.CLOSED, 0),
            "failed": by_state.get(recovery_case_service.FAILED, 0),
            "by_state": by_state,
        },
        "approvals": {"pending": awaiting_approval},
        "messages": {
            "drafted": drafted,
            "actually_sent": sent,
            "blocked_or_failed": blocked,
            "outcome_unknown": unknown,
            "replies_received": replies,
            "note": ("Drafted counts every outbound message this system composed. "
                     "Actually sent counts only those a provider accepted."),
        },
        "revenue": {
            # Three separate figures that are never combined.
            "potential_value_open_by_currency": potential_open,
            "attributed_recovered_value_by_currency":
                attribution_totals["attributed_recovered_value_by_currency"],
            "unattributed_outcome_value_by_currency":
                attribution_totals["unattributed_outcome_value_by_currency"],
            "currencies": sorted(set(potential_open)
                                 | set(attribution_totals["attributed_recovered_value_by_currency"])
                                 | set(attribution_totals["unattributed_outcome_value_by_currency"])),
            "note": ("Open potential is an estimate of what un-recovered cases might be "
                     "worth. Attributed recovered value is money a record says arrived "
                     "on a case where outreach demonstrably reached the client. "
                     "Unattributed outcomes are real revenue this system does not claim "
                     "to have caused."),
        },
        "attribution": {
            "entries": attribution_totals["entries"],
            "attributed": attribution_totals["attributed_entries"],
            "unattributed": attribution_totals["unattributed_entries"],
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
                         f"'{recovery_case_service.DETECTED}'"),
        "approvals.pending": f"{APPROVALS} where status = 'pending'",
        "messages.drafted": (f"{conversation_service.MESSAGES} where direction = "
                             f"'{conversation_service.OUTBOUND}' on a conversation "
                             "linked to a recovery case"),
        "messages.actually_sent": (f"the same, restricted to status in "
                                   f"{list(SENT_STATES)}"),
        "messages.replies_received": (f"{conversation_service.MESSAGES} where direction "
                                      f"= '{conversation_service.INBOUND}'"),
        "revenue.potential_value_open_by_currency": (
            f"sum of potential_value over {recovery_case_service.COLLECTION} in an open "
            "state, grouped by currency"),
        "revenue.attributed_recovered_value_by_currency": (
            f"sum of outcome.amount over {attribution.COLLECTION} where claim = "
            f"'{attribution.CLAIM_ATTRIBUTED}', grouped by currency"),
        "revenue.unattributed_outcome_value_by_currency": (
            f"the same where claim = '{attribution.CLAIM_UNATTRIBUTED}'"),
        "time_to_recovery": (
            "days between a case's detection and the outcome date on its attributed "
            f"{attribution.COLLECTION} entry, over entries carrying both dates"),
    }
