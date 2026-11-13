"""GENERATED from AgAPI's spec/ by tools/contract/generate.py (CR 186) — DO NOT EDIT. Change spec/, regenerate, bump the release.
kanoe_contract 1.94.0 · AgAPI 1.94.0 · AD door kanoe-ad-door.1. Use OP.X / ERR.X / DOOR.X — never the string."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict, Union  # noqa: F401

CONTRACT_VERSION = "1.94.0"


class OP:
    """Every AgAPI operation name."""
    ACCESS_GET = "access.get"
    ACTIVITIES_SUGGEST = "activities.suggest"
    ACTIVITIES_VERIFY = "activities.verify"
    ACTIVITY_LIST = "activity.list"
    ACTS_STATUS = "acts.status"
    APPROVALS_IN_APP_TAP = "approvals.in_app_tap"
    APPROVALS_MANDATE = "approvals.mandate"
    APPROVALS_REQUEST = "approvals.request"
    APPROVALS_STATUS = "approvals.status"
    CALENDAR_ADD_EVENT = "calendar.add_event"
    CARDS_ACCIDENT_NOTIFY = "cards.accident_notify"
    CARDS_ACCIDENT_PHOTO = "cards.accident_photo"
    CARDS_ACCIDENT_START = "cards.accident_start"
    CARDS_ACCIDENT_STEP = "cards.accident_step"
    CARDS_ASK = "cards.ask"
    CARDS_CLAIM_ATTACH = "cards.claim_attach"
    CARDS_CLAIM_FILE = "cards.claim_file"
    CARDS_CLAIM_SIMULATE_REPLY = "cards.claim_simulate_reply"
    CARDS_CLAIM_START = "cards.claim_start"
    CARDS_CLAIM_STATUS = "cards.claim_status"
    CARDS_INTAKE = "cards.intake"
    CARDS_MINE = "cards.mine"
    CARDS_MOMENT = "cards.moment"
    CARDS_MOMENT_SETTINGS = "cards.moment_settings"
    CARDS_PRODUCTS = "cards.products"
    CARDS_RENTAL_COVER = "cards.rental_cover"
    CARDS_RENTAL_DISPUTE = "cards.rental_dispute"
    CARDS_TERMS = "cards.terms"
    CARDS_WHICH = "cards.which"
    DIVE_ONBOARD = "dive.onboard"
    ENTRY_CHECK = "entry.check"
    ENTRY_PREPARE = "entry.prepare"
    EVIDENCE_GET = "evidence.get"
    EVIDENCE_VERIFY = "evidence.verify"
    GROUP_BOOK = "group.book"
    GROUP_BOOKINGS = "group.bookings"
    GROUP_CANCEL = "group.cancel"
    GROUP_SWAP = "group.swap"
    KEEP_ACTIVITY = "keep.activity"
    KEEP_DELETE = "keep.delete"
    KEEP_LIST = "keep.list"
    KEEP_PUT = "keep.put"
    KEEP_USE = "keep.use"
    MAGELLAN_READ_SITE = "magellan.read_site"
    MESSAGES_AD_CASES = "messages.ad_cases"
    MESSAGES_REPLIES = "messages.replies"
    MESSAGES_SEND_EMAIL = "messages.send_email"
    MESSAGES_SEND_WHATSAPP = "messages.send_whatsapp"
    MESSAGES_TYPING = "messages.typing"
    MESSAGES_WHATSAPP_INBOUND = "messages.whatsapp_inbound"
    MESSAGES_WHATSAPP_SWITCH = "messages.whatsapp_switch"
    MONEY_BAG_CHECK = "money.bag_check"
    MONEY_BAG_CLAIM = "money.bag_claim"
    MONEY_CLAIM_SIMULATE_REPLY = "money.claim_simulate_reply"
    MONEY_CLAIM_STATUS = "money.claim_status"
    MONEY_FLIGHT_CHECK = "money.flight_check"
    MONEY_FLIGHT_CLAIM = "money.flight_claim"
    OUTCOMES_LIST = "outcomes.list"
    OUTCOMES_MARK_TEST = "outcomes.mark_test"
    OUTCOMES_RECORD = "outcomes.record"
    OUTCOMES_REPORT = "outcomes.report"
    OUTCOMES_UPDATE = "outcomes.update"
    REGISTRY_CHANGE_LIST = "registry.change_list"
    REGISTRY_COUNTRIES = "registry.countries"
    REGISTRY_DOCUMENTS = "registry.documents"
    REGISTRY_GET = "registry.get"
    REGISTRY_OBTAIN_PLAN = "registry.obtain_plan"
    REGISTRY_ROW_RESULTS = "registry.row_results"
    REGISTRY_VERIFY = "registry.verify"
    REGISTRY_WAVE_RESUME = "registry.wave_resume"
    REGISTRY_WAVE_RUN = "registry.wave_run"
    REGISTRY_WAVE_STATUS = "registry.wave_status"
    SANDBOX_AD_CASE = "sandbox.ad_case"
    SANDBOX_AD_OPEN_CASE = "sandbox.ad_open_case"
    SANDBOX_LINK_PROOF = "sandbox.link_proof"
    SANDBOX_MESSAGES = "sandbox.messages"
    SANDBOX_PLATFORM_PREPARE = "sandbox.platform_prepare"
    SANDBOX_PLATFORM_WALK = "sandbox.platform_walk"
    SANDBOX_SIMULATE_APPROVAL = "sandbox.simulate_approval"
    SANDBOX_SIMULATE_CALL = "sandbox.simulate_call"
    SANDBOX_SIMULATE_REPLY = "sandbox.simulate_reply"
    SANDBOX_WA_TEMPLATE = "sandbox.wa_template"
    SOURCES_GET = "sources.get"
    SUBSCRIPTIONS_CANCEL = "subscriptions.cancel"
    SUBSCRIPTIONS_CANCEL_PLAN = "subscriptions.cancel_plan"
    SUBSCRIPTIONS_FIND = "subscriptions.find"
    TRAVEL_FIND_FLIGHTS = "travel.find_flights"
    TRAVEL_FIND_STAYS = "travel.find_stays"
    TRIP_CANCEL = "trip.cancel"
    TRIP_COMPLETE = "trip.complete"
    TRIP_HOLD = "trip.hold"
    TRIP_PLAN = "trip.plan"
    TRIP_PLAN_GET = "trip.plan_get"
    USAGE_GET = "usage.get"
    USERS_CONFIRM_WHATSAPP = "users.confirm_whatsapp"
    USERS_LINK_WHATSAPP = "users.link_whatsapp"
    USERS_REGISTER = "users.register"
    USERS_VERIFY_DESTINATION = "users.verify_destination"
    VENUE_BOOKING_STATUS = "venue.booking_status"
    VENUE_BOOKINGS = "venue.bookings"
    VENUE_CALL_AGAIN = "venue.call_again"
    VENUE_CALL_ATTEMPT = "venue.call_attempt"
    VENUE_CANCEL_BOOKING = "venue.cancel_booking"
    VENUE_CHANGE_BOOKING = "venue.change_booking"
    VENUE_CONFIRMATION = "venue.confirmation"
    VENUE_DISCOVER = "venue.discover"
    VENUE_HANDED_OVER = "venue.handed_over"
    VENUE_MANAGE_OPTIONS = "venue.manage_options"
    VENUE_PERSON_REPORT = "venue.person_report"
    VENUE_PREPARE_BOOKING = "venue.prepare_booking"
    VENUE_PROFILE = "venue.profile"
    VENUE_RECOGNITION = "venue.recognition"
    VENUE_SUBMIT_BOOKING = "venue.submit_booking"
    VENUE_UNHANDLED = "venue.unhandled"
    VENUES_FIND_VENUES = "venues.find_venues"
    WEBHOOKS_REGISTER = "webhooks.register"
    WEBHOOKS_REVOKE = "webhooks.revoke"


class ERR:
    """Every error code AgAPI answers."""
    ALREADY_COMPLETED = "already_completed"
    APPROVAL_CONSUMED = "approval_consumed"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_NOT_FOUND = "approval_not_found"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_SAME_TURN = "approval_same_turn"
    APPROVAL_UNTRUSTED_ORIGIN = "approval_untrusted_origin"
    APPROVAL_VOID = "approval_void"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DESTINATION_CODE_EXPIRED = "destination_code_expired"
    DESTINATION_CODE_INVALID = "destination_code_invalid"
    EMAIL_NEEDED = "email_needed"
    FORBIDDEN = "forbidden"
    HOLD_EXPIRED = "hold_expired"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    IDEMPOTENCY_IN_FLIGHT = "idempotency_in_flight"
    IDEMPOTENCY_KEY_REQUIRED = "idempotency_key_required"
    INTERNAL = "internal"
    INVALID_INPUT = "invalid_input"
    INVALID_REQUEST = "invalid_request"
    MOBILE_NEEDED = "mobile_needed"
    MODE_NOT_AVAILABLE = "mode_not_available"
    NO_EXPLICIT_YES = "no_explicit_yes"
    NOT_CANCELLABLE = "not_cancellable"
    NOT_FOUND = "not_found"
    OUTCOME_UNKNOWN = "outcome_unknown"
    RATE_LIMITED = "rate_limited"
    TRAVELLERS_MISSING = "travellers_missing"
    UNAUTHENTICATED = "unauthenticated"
    UNKNOWN_OPERATION = "unknown_operation"
    UPSTREAM_FAILED = "upstream_failed"
    UPSTREAM_RATE_LIMITED = "upstream_rate_limited"
    UPSTREAM_REFUSED = "upstream_refused"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    UPSTREAM_UNREACHABLE = "upstream_unreachable"
    VERSION_UNSUPPORTED = "version_unsupported"
    WEBHOOK_LIMIT_REACHED = "webhook_limit_reached"
    WEBHOOK_URL_REFUSED = "webhook_url_refused"


class DOOR:
    """Every kind Applied Diligence's door accepts."""
    ACTIONS = "actions"
    ADD_EVIDENCE = "add_evidence"
    ADD_PARTY = "add_party"
    CANCEL_ORDER = "cancel_order"
    CASE_EVENTS = "case_events"
    CASE_LIST = "case_list"
    CASE_STATUS = "case_status"
    CONVERSATION_ROLE = "conversation_role"
    INTERVIEW = "interview"
    INTERVIEW_DECLINED = "interview_declined"
    INTERVIEW_DUE = "interview_due"
    INTERVIEW_OFFER = "interview_offer"
    INTERVIEW_SENT = "interview_sent"
    INTERVIEW_TRANSCRIPT = "interview_transcript"
    MESSAGE = "message"
    NEXT_STEPS = "next_steps"
    QUESTIONNAIRE = "questionnaire"
    QUESTIONNAIRE_OFFER = "questionnaire_offer"
    REPORT = "report"
    SET_CONTACT = "set_contact"
    SET_PHONE = "set_phone"


OPERATIONS = frozenset(['access.get', 'activities.suggest', 'activities.verify', 'activity.list', 'acts.status', 'approvals.in_app_tap', 'approvals.mandate', 'approvals.request', 'approvals.status', 'calendar.add_event', 'cards.accident_notify', 'cards.accident_photo', 'cards.accident_start', 'cards.accident_step', 'cards.ask', 'cards.claim_attach', 'cards.claim_file', 'cards.claim_simulate_reply', 'cards.claim_start', 'cards.claim_status', 'cards.intake', 'cards.mine', 'cards.moment', 'cards.moment_settings', 'cards.products', 'cards.rental_cover', 'cards.rental_dispute', 'cards.terms', 'cards.which', 'dive.onboard', 'entry.check', 'entry.prepare', 'evidence.get', 'evidence.verify', 'group.book', 'group.bookings', 'group.cancel', 'group.swap', 'keep.activity', 'keep.delete', 'keep.list', 'keep.put', 'keep.use', 'magellan.read_site', 'messages.ad_cases', 'messages.replies', 'messages.send_email', 'messages.send_whatsapp', 'messages.typing', 'messages.whatsapp_inbound', 'messages.whatsapp_switch', 'money.bag_check', 'money.bag_claim', 'money.claim_simulate_reply', 'money.claim_status', 'money.flight_check', 'money.flight_claim', 'outcomes.list', 'outcomes.mark_test', 'outcomes.record', 'outcomes.report', 'outcomes.update', 'registry.change_list', 'registry.countries', 'registry.documents', 'registry.get', 'registry.obtain_plan', 'registry.row_results', 'registry.verify', 'registry.wave_resume', 'registry.wave_run', 'registry.wave_status', 'sandbox.ad_case', 'sandbox.ad_open_case', 'sandbox.link_proof', 'sandbox.messages', 'sandbox.platform_prepare', 'sandbox.platform_walk', 'sandbox.simulate_approval', 'sandbox.simulate_call', 'sandbox.simulate_reply', 'sandbox.wa_template', 'sources.get', 'subscriptions.cancel', 'subscriptions.cancel_plan', 'subscriptions.find', 'travel.find_flights', 'travel.find_stays', 'trip.cancel', 'trip.complete', 'trip.hold', 'trip.plan', 'trip.plan_get', 'usage.get', 'users.confirm_whatsapp', 'users.link_whatsapp', 'users.register', 'users.verify_destination', 'venue.booking_status', 'venue.bookings', 'venue.call_again', 'venue.call_attempt', 'venue.cancel_booking', 'venue.change_booking', 'venue.confirmation', 'venue.discover', 'venue.handed_over', 'venue.manage_options', 'venue.person_report', 'venue.prepare_booking', 'venue.profile', 'venue.recognition', 'venue.submit_booking', 'venue.unhandled', 'venues.find_venues', 'webhooks.register', 'webhooks.revoke'])
ERROR_CODES = frozenset(['already_completed', 'approval_consumed', 'approval_expired', 'approval_not_found', 'approval_required', 'approval_same_turn', 'approval_untrusted_origin', 'approval_void', 'budget_exhausted', 'destination_code_expired', 'destination_code_invalid', 'email_needed', 'forbidden', 'hold_expired', 'idempotency_conflict', 'idempotency_in_flight', 'idempotency_key_required', 'internal', 'invalid_input', 'invalid_request', 'mobile_needed', 'mode_not_available', 'no_explicit_yes', 'not_cancellable', 'not_found', 'outcome_unknown', 'rate_limited', 'travellers_missing', 'unauthenticated', 'unknown_operation', 'upstream_failed', 'upstream_rate_limited', 'upstream_refused', 'upstream_timeout', 'upstream_unreachable', 'version_unsupported', 'webhook_limit_reached', 'webhook_url_refused'])
DOOR_KINDS = frozenset(['actions', 'add_evidence', 'add_party', 'cancel_order', 'case_events', 'case_list', 'case_status', 'conversation_role', 'interview', 'interview_declined', 'interview_due', 'interview_offer', 'interview_sent', 'interview_transcript', 'message', 'next_steps', 'questionnaire', 'questionnaire_offer', 'report', 'set_contact', 'set_phone'])
DOOR_ANSWERS: Dict[str, frozenset] = {
    'actions': frozenset(['actions', 'case_id', 'detail', 'error', 'intent', 'intent_why', 'lines', 'parts', 'reply']),
    'add_evidence': frozenset(['case_id', 'corpus_id', 'detail', 'error', 'intent', 'intent_why', 'parts', 'reply', 'stored_path']),
    'add_party': frozenset(['case_id', 'created', 'detail', 'error', 'intent', 'intent_why', 'parts', 'party_id', 'party_token', 'phone_refused', 'phone_saved', 'reply', 'screened']),
    'cancel_order': frozenset(['case_id', 'charge', 'detail', 'error', 'intent', 'intent_why', 'order_reference', 'parts', 'queue_item', 'reply']),
    'case_events': frozenset(['case_id', 'cases_truncated', 'cursor', 'detail', 'error', 'events', 'from', 'intent', 'intent_why', 'more', 'parts', 'reply']),
    'case_list': frozenset(['case_id', 'cases', 'detail', 'error', 'intent', 'intent_why', 'parts', 'reply', 'truncated']),
    'case_status': frozenset(['as_of', 'case_id', 'checks', 'complete', 'contradictions', 'detail', 'error', 'findings', 'held_checks', 'intent', 'intent_why', 'lists', 'next_steps_token', 'open', 'parties', 'parties_total', 'parts', 'poll_after_seconds', 'ready', 'reply', 'running', 'screened', 'steps', 'stopped', 'stopped_at', 'verdict', 'work_line']),
    'conversation_role': frozenset(['ad_intent', 'ask', 'case_id', 'detail', 'error', 'intent', 'intent_why', 'open', 'parts', 'reason', 'reply', 'resolved', 'role', 'roles', 'why']),
    'interview': frozenset(['case_id', 'created', 'detail', 'error', 'intent', 'intent_why', 'interview_number', 'interview_request', 'interview_token', 'needs', 'parts', 'reply']),
    'interview_declined': frozenset(['case_id', 'detail', 'error', 'intent', 'intent_why', 'parts', 'recorded', 'reply']),
    'interview_due': frozenset(['cannot_invite', 'case_id', 'detail', 'error', 'intent', 'intent_why', 'invite', 'parts', 'remind', 'reply', 'waiting']),
    'interview_offer': frozenset(['case_id', 'created', 'detail', 'error', 'intent', 'intent_why', 'interview_number', 'interview_request', 'interview_token', 'needs', 'parts', 'reply']),
    'interview_sent': frozenset(['case_id', 'detail', 'error', 'intent', 'intent_why', 'interview_number', 'parts', 'recorded', 'reply']),
    'interview_transcript': frozenset(['already_filed', 'case_id', 'corpus_id', 'detail', 'disclosure_problem', 'error', 'intent', 'intent_why', 'interview_number', 'parts', 'recorded', 'reply', 'rescore_failed', 'rescored']),
    'message': frozenset(['actions', 'ad_intent', 'already_filed', 'already_sent', 'approved', 'as_of', 'ask', 'cannot_invite', 'case_id', 'cases', 'cases_truncated', 'charge', 'checks', 'complete', 'contradictions', 'corpus_id', 'created', 'cursor', 'detail', 'disclosure_problem', 'error', 'events', 'findings', 'from', 'held_checks', 'identity_token', 'intent', 'intent_why', 'interview_number', 'interview_request', 'interview_token', 'invite', 'lines', 'lists', 'more', 'needs', 'next_steps_token', 'open', 'order_reference', 'parties', 'parties_total', 'parts', 'party_id', 'party_token', 'person', 'phone_refused', 'phone_saved', 'poll_after_seconds', 'questionnaire_token', 'queue_item', 'quote_token', 'ready', 'reason', 'recorded', 'refused', 'remind', 'replaced', 'reply', 'report', 'rescore_failed', 'rescored', 'resolved', 'role', 'roles', 'round', 'running', 'screened', 'sent', 'steps', 'stopped', 'stopped_at', 'stored_path', 'truncated', 'verdict', 'waiting', 'why', 'work_line']),
    'next_steps': frozenset(['approved', 'case_id', 'created', 'detail', 'error', 'intent', 'intent_why', 'interview_number', 'interview_request', 'next_steps_token', 'parts', 'refused', 'reply']),
    'questionnaire': frozenset(['already_sent', 'case_id', 'detail', 'error', 'intent', 'intent_why', 'needs', 'parts', 'questionnaire_token', 'reply', 'round', 'sent']),
    'questionnaire_offer': frozenset(['already_sent', 'case_id', 'detail', 'error', 'intent', 'intent_why', 'needs', 'parts', 'questionnaire_token', 'reply', 'round', 'sent']),
    'report': frozenset(['case_id', 'detail', 'error', 'intent', 'intent_why', 'parts', 'reply', 'report']),
    'set_contact': frozenset(['case_id', 'detail', 'error', 'intent', 'intent_why', 'next_steps_token', 'parts', 'recorded', 'reply']),
    'set_phone': frozenset(['case_id', 'detail', 'error', 'intent', 'intent_why', 'parts', 'person', 'replaced', 'reply']),
}
# CR 197 · each shaped answer field → the ONLY keys it may carry
DOOR_SHAPES: Dict[str, frozenset] = {
    'report': frozenset(['report_id', 'verdict', 'verdict_label', 'generated_at', 'authorship', 'report_url']),
}
# CR 200 · each kind → the request fields a sender MUST send with it (beyond kind)
DOOR_REQUIRES: Dict[str, tuple] = {
    'actions': (),
    'add_evidence': (),
    'add_party': (),
    'cancel_order': (),
    'case_events': (),
    'case_list': (),
    'case_status': (),
    'conversation_role': ('sender', 'text', 'message_id'),
    'interview': (),
    'interview_declined': (),
    'interview_due': (),
    'interview_offer': (),
    'interview_sent': (),
    'interview_transcript': (),
    'message': ('sender', 'text', 'message_id'),
    'next_steps': (),
    'questionnaire': (),
    'questionnaire_offer': (),
    'report': (),
    'set_contact': (),
    'set_phone': (),
}

DoorReport = TypedDict('DoorReport', {"report_id": Any, "verdict": Any, "verdict_label": Any, "generated_at": Any, "authorship": Any, "report_url": Any}, total=False)


def door_read(kind: str, answer: Dict[str, Any]) -> tuple:
    """CR 197 · THE ONE reader of an Applied Diligence answer: → (the answer with ONLY the fields the contract declares for this kind — a
    shaped field with only its declared keys —, the undeclared paths it dropped). A field nobody declares never reaches the reader's code."""
    allowed = DOOR_ANSWERS.get(kind)
    if allowed is None or not isinstance(answer, dict):
        return ({}, [kind or "?"]) if allowed is None else ({}, [])
    out: Dict[str, Any] = {}
    dropped: List[str] = []
    for f, v in answer.items():
        if f not in allowed:
            dropped.append(f)
            continue
        if f in DOOR_SHAPES and isinstance(v, dict):
            dropped += [f"{f}.{x}" for x in v if x not in DOOR_SHAPES[f]]
            v = {x: y for x, y in v.items() if x in DOOR_SHAPES[f]}
        out[f] = v
    return out, dropped


def door_missing(body: Dict[str, Any]) -> List[str]:
    """CR 200 · → the fields this request must carry for its kind and doesn't (an unknown kind: ["kind"]). A sender checks it before sending."""
    k = body.get("kind")
    if k not in DOOR_REQUIRES:
        return ["kind"]
    return [f for f in DOOR_REQUIRES[k] if body.get(f) is None]


def door_answer(kind: str, **fields: Any) -> Dict[str, Any]:
    """CR 197 · an Applied Diligence answer BUILT from the contract (a test's stand-in uses this, never a hand-made dict): any field —
    or shaped key — the contract doesn't declare for this kind is refused here (ValueError), before anything can read it."""
    out, dropped = door_read(kind, fields)
    if dropped:
        raise ValueError(f"not in the door contract for {kind!r}: {', '.join(dropped)}")
    return out



# access.get — input
AccessGetIn = TypedDict('AccessGetIn', {"end_user": str}, total=False)

# access.get — output
AccessGetOut = TypedDict('AccessGetOut', {"mode": Union[str, bool, int, None], "calls": Union[str, bool, int, None], "real_venue_sends": Union[str, bool, int, None], "mailbox": Union[str, bool, int, None], "demo": Union[str, bool, int, None], "founder": Union[str, bool, int, None], "real_money": Union[str, bool, int, None], "version": Union[str, bool, int, None], "source": Union[str, bool, int, None], "platform_submit": Literal['off', 'beta'], "mailboxes": Any}, total=False)

# activities.suggest — input
ActivitiesSuggestIn = TypedDict('ActivitiesSuggestIn', {"city": str, "country": str, "dates": Dict[str, Any], "interests": List[str], "party": int, "near": str, "limit": int}, total=False)

# activities.suggest — output
ActivitiesSuggestOut = TypedDict('ActivitiesSuggestOut', {"city": str, "dates": Dict[str, Any], "candidates": List[Any], "say": str}, total=False)

# activities.verify — input
ActivitiesVerifyIn = TypedDict('ActivitiesVerifyIn', {"candidate_id": str, "official_url": str, "date": str}, total=False)

# activities.verify — output
ActivitiesVerifyOut = TypedDict('ActivitiesVerifyOut', {"candidate_id": Union[str, None], "name": str, "kind": str, "official_url": str, "date": str, "open": Union[Dict[str, Any], None], "event": Union[Dict[str, Any], None], "no_event": Dict[str, Any], "price": Union[Dict[str, Any], None], "ticket_url": Union[str, None], "photo_url": Union[str, None], "confidence": Literal['verified', 'partial', 'not_read'], "why_not": str, "body_sha256": Union[str, None], "read_at": str, "stale": str, "say": str, "source": Dict[str, Any], "own_site_why_not": Union[str, None], "second_tried": List[Dict[str, Any]], "tried_at": str}, total=False)

# activity.list — input
ActivityListIn = TypedDict('ActivityListIn', {"end_user": str, "since": str, "limit": int}, total=False)

# activity.list — output
ActivityListOut = TypedDict('ActivityListOut', {"items": List[Dict[str, Any]], "coverage": Dict[str, Any]}, total=False)

# acts.status — input
ActsStatusIn = TypedDict('ActsStatusIn', {"act_id": str, "intent_id": str}, total=False)

# acts.status — output
ActsStatusOut = TypedDict('ActsStatusOut', {"acts": List[Dict[str, Any]], "coverage": Dict[str, Any]}, total=False)

# approvals.in_app_tap — input
ApprovalsInAppTapIn = TypedDict('ApprovalsInAppTapIn', {"read_back_id": str, "read_back_sha256": str, "session": Dict[str, Any], "read_backs": List[Dict[str, Any]]}, total=False)

# approvals.in_app_tap — output
ApprovalsInAppTapOut = TypedDict('ApprovalsInAppTapOut', {"approval_id": str, "method": str, "operation": str, "result": Dict[str, Any], "say": Union[str, None], "approvals": List[Dict[str, Any]], "refused": List[Dict[str, Any]]}, total=False)

# approvals.mandate — input
ApprovalsMandateIn = TypedDict('ApprovalsMandateIn', {"end_user": str, "words": str, "scope": Dict[str, Any], "limits": Dict[str, Any], "expires_in_minutes": int, "proof": Dict[str, Any]}, total=False)

# approvals.mandate — output
ApprovalsMandateOut = TypedDict('ApprovalsMandateOut', {"mandate_id": str, "words": str, "scope": Dict[str, Any], "limits": Dict[str, Any], "expires_at": str, "proof": Dict[str, Any]}, total=False)

# approvals.request — input
ApprovalsRequestIn = TypedDict('ApprovalsRequestIn', {"read_back_id": str, "channel": Literal['link_sms', 'link_whatsapp', 'link_email', 'sdk', 'sasha_voice', 'sasha_chat'], "destination": str}, total=False)

# approvals.request — output
ApprovalsRequestOut = TypedDict('ApprovalsRequestOut', {"read_back_id": str, "presentation": Dict[str, Any]}, total=False)

# approvals.status — input
ApprovalsStatusIn = TypedDict('ApprovalsStatusIn', {"read_back_id": str}, total=False)

# approvals.status — output
ApprovalsStatusOut = TypedDict('ApprovalsStatusOut', {"read_back_id": str, "read_back_state": Literal['created', 'presented', 'approved', 'expired', 'void'], "presented_at": Union[None, str], "approval": Union[None, Dict[str, Any]]}, total=False)

# calendar.add_event — input
CalendarAddEventIn = TypedDict('CalendarAddEventIn', {"act_id": str}, total=False)

# calendar.add_event — output
CalendarAddEventOut = TypedDict('CalendarAddEventOut', {"event": Dict[str, Any], "event_sha256": str, "ics": str, "links": Dict[str, Any], "evidence_id": str}, total=False)

# cards.accident_notify — input
CardsAccidentNotifyIn = TypedDict('CardsAccidentNotifyIn', {"end_user": str, "case_id": str}, total=False)

# cards.accident_notify — output
CardsAccidentNotifyOut = TypedDict('CardsAccidentNotifyOut', {"ask_card": Any, "claim_case_id": Any, "clocks": Any, "evidence_id": Any, "outcome": Any, "state": Any, "case_id": Any, "say": Any, "step": Any, "steps": Any}, total=False)

# cards.accident_photo — input
CardsAccidentPhotoIn = TypedDict('CardsAccidentPhotoIn', {"end_user": str, "case_id": str, "shot": Literal['your_car_front', 'your_car_back', 'your_car_left', 'your_car_right', 'the_damage_close_up', 'the_other_car_and_its_plate', 'your_rental_cars_plate', 'the_road_and_signs', 'the_other_drivers_licence_and_insurance'], "media_type": Literal['image/png', 'image/jpeg', 'image/webp', 'image/heic'], "content_base64": str}, total=False)

# cards.accident_photo — output
CardsAccidentPhotoOut = TypedDict('CardsAccidentPhotoOut', {"case_id": str, "step": str, "steps": List[str], "handoff": Any, "say": str, "choices": List[str], "done": bool, "call": Any, "next": str, "lines": List[Any], "quotes": List[Any], "read_at_source": Any, "shots": List[Dict[str, Any]], "advice": Any, "facts": Dict[str, Any], "form": Any, "left_for_you": List[Any], "clocks": List[Any], "ask_card": Dict[str, Any], "claim_case_id": str, "saved": Any}, total=False)

# cards.accident_start — input
CardsAccidentStartIn = TypedDict('CardsAccidentStartIn', {"end_user": str, "country": str, "place": str, "at": str, "rental_company": str, "card_item_id": str, "facts": Dict[str, Any]}, total=False)

# cards.accident_start — output
CardsAccidentStartOut = TypedDict('CardsAccidentStartOut', {"case_id": str, "step": str, "steps": List[str], "handoff": Any, "say": str, "choices": List[str], "done": bool, "call": Any, "next": str, "lines": List[Any], "quotes": List[Any], "read_at_source": Any, "shots": List[Dict[str, Any]], "advice": Any, "facts": Dict[str, Any], "form": Any, "left_for_you": List[Any], "clocks": List[Any], "ask_card": Dict[str, Any], "claim_case_id": str}, total=False)

# cards.accident_step — input
CardsAccidentStepIn = TypedDict('CardsAccidentStepIn', {"end_user": str, "case_id": str, "answer": str, "flags": List[Literal['injuries', 'fault_disputed', 'police_charges', 'claim_against_me']], "facts": Dict[str, Any], "card_item_id": str}, total=False)

# cards.accident_step — output
CardsAccidentStepOut = TypedDict('CardsAccidentStepOut', {"case_id": str, "step": str, "steps": List[str], "handoff": Any, "say": str, "choices": List[str], "done": bool, "call": Any, "next": str, "lines": List[Any], "quotes": List[Any], "read_at_source": Any, "shots": List[Dict[str, Any]], "advice": Any, "facts": Dict[str, Any], "form": Any, "left_for_you": List[Any], "clocks": List[Any], "ask_card": Dict[str, Any], "claim_case_id": str}, total=False)

# cards.ask — input
CardsAskIn = TypedDict('CardsAskIn', {"end_user": str, "card_item_id": str, "product_id": str, "question": str}, total=False)

# cards.ask — output
CardsAskOut = TypedDict('CardsAskOut', {"card": str, "product_id": str, "framing": str, "answer": Literal['yes', 'no', 'partly', 'quoted', 'not_stated', 'no_terms', 'awaiting_check'], "text": str, "quotes": List[Dict[str, Any]], "claims_line": Dict[str, Any], "how": str}, total=False)

# cards.claim_attach — input
CardsClaimAttachIn = TypedDict('CardsClaimAttachIn', {"end_user": str, "case_id": str, "kind": Literal['card_statement_line', 'booking_confirmation', 'airline_delay_report', 'airline_delay_letter', 'receipts', 'photos', 'cancellation_proof', 'medical_certificate', 'rental_agreement', 'damage_report', 'accident_statement', 'repair_invoice', 'police_report'], "name": str, "media_type": str, "content_base64": str}, total=False)

# cards.claim_attach — output
CardsClaimAttachOut = TypedDict('CardsClaimAttachOut', {"case_id": str, "state": Literal['preparing', 'ready_for_portal', 'filed'], "card": str, "kind": Literal['baggage_delay', 'baggage_loss', 'trip_delay', 'trip_cancellation', 'rental_damage', 'purchase_damage_theft'], "route": Dict[str, Any], "deadlines": List[Any], "reminders": List[Any], "clause": List[Any], "evidence": List[Any], "files": List[Any], "replies": List[Any], "incident": Dict[str, Any]}, total=False)

# cards.claim_file — input
CardsClaimFileIn = TypedDict('CardsClaimFileIn', {"end_user": str, "case_id": str}, total=False)

# cards.claim_file — output
CardsClaimFileOut = TypedDict('CardsClaimFileOut', {"act_id": Any, "evidence_id": Any, "outcome": Any, "card": Any, "case_id": Any, "clause": Any, "deadlines": Any, "evidence": Any, "files": Any, "incident": Any, "kind": Any, "reminders": Any, "replies": Any, "route": Any, "state": Any}, total=False)

# cards.claim_simulate_reply — input
CardsClaimSimulateReplyIn = TypedDict('CardsClaimSimulateReplyIn', {"end_user": str, "case_id": str, "text": str}, total=False)

# cards.claim_simulate_reply — output
CardsClaimSimulateReplyOut = TypedDict('CardsClaimSimulateReplyOut', {"act_id": Any, "evidence_id": Any, "outcome": Any, "card": Any, "case_id": Any, "clause": Any, "deadlines": Any, "evidence": Any, "files": Any, "incident": Any, "kind": Any, "reminders": Any, "replies": Any, "route": Any, "state": Any}, total=False)

# cards.claim_start — input
CardsClaimStartIn = TypedDict('CardsClaimStartIn', {"end_user": str, "card_item_id": str, "kind": Literal['baggage_delay', 'baggage_loss', 'trip_delay', 'trip_cancellation', 'rental_damage', 'purchase_damage_theft'], "incident_date": str, "amount_minor": int, "currency": str, "description": str}, total=False)

# cards.claim_start — output
CardsClaimStartOut = TypedDict('CardsClaimStartOut', {}, total=False)

# cards.claim_status — input
CardsClaimStatusIn = TypedDict('CardsClaimStatusIn', {"end_user": str, "case_id": str}, total=False)

# cards.claim_status — output
CardsClaimStatusOut = TypedDict('CardsClaimStatusOut', {"case_id": str, "state": Literal['preparing', 'ready_for_portal', 'filed'], "card": str, "kind": Literal['baggage_delay', 'baggage_loss', 'trip_delay', 'trip_cancellation', 'rental_damage', 'purchase_damage_theft'], "route": Dict[str, Any], "deadlines": List[Any], "reminders": List[Any], "clause": List[Any], "evidence": List[Any], "files": List[Any], "replies": List[Any], "incident": Dict[str, Any]}, total=False)

# cards.intake — input
CardsIntakeIn = TypedDict('CardsIntakeIn', {"end_user": str, "save": bool, "image": Dict[str, Any]}, total=False)

# cards.intake — output
CardsIntakeOut = TypedDict('CardsIntakeOut', {"card": Dict[str, Any], "saved": bool, "item_id": str, "masked": str, "terms": Dict[str, Any], "note": str}, total=False)

# cards.mine — input
CardsMineIn = TypedDict('CardsMineIn', {"end_user": str}, total=False)

# cards.mine — output
CardsMineOut = TypedDict('CardsMineOut', {"cards": List[Dict[str, Any]]}, total=False)

# cards.moment — input
CardsMomentIn = TypedDict('CardsMomentIn', {"end_user": str, "event": Dict[str, Any]}, total=False)

# cards.moment — output
CardsMomentOut = TypedDict('CardsMomentOut', {"speak": bool, "why_silent": str, "moment_id": str, "moment": Literal['rental_booked', 'pickup_tomorrow', 'which_card', 'rental_returned'], "line": str, "why": str, "card": Dict[str, Any]}, total=False)

# cards.moment_settings — input
CardsMomentSettingsIn = TypedDict('CardsMomentSettingsIn', {"end_user": str, "moment": Literal['rental_booked', 'pickup_tomorrow', 'which_card', 'rental_returned'], "on": bool}, total=False)

# cards.moment_settings — output
CardsMomentSettingsOut = TypedDict('CardsMomentSettingsOut', {"moments": List[Any]}, total=False)

# cards.products — input
CardsProductsIn = TypedDict('CardsProductsIn', {"query": str}, total=False)

# cards.products — output
CardsProductsOut = TypedDict('CardsProductsOut', {"products": List[Dict[str, Any]], "note": str}, total=False)

# cards.rental_cover — input
CardsRentalCoverIn = TypedDict('CardsRentalCoverIn', {"end_user": str, "country": str, "rental_company": str, "days": int, "vehicle": str, "card_item_id": str}, total=False)

# cards.rental_cover — output
CardsRentalCoverOut = TypedDict('CardsRentalCoverOut', {"framing": str, "country": str, "company": str, "card": Union[str, None], "cards": List[Any], "rental_note": str, "skipped": List[Any], "counter": Dict[str, Any], "conditions": List[Dict[str, Any]], "bring": List[Dict[str, Any]], "report": List[Dict[str, Any]]}, total=False)

# cards.rental_dispute — input
CardsRentalDisputeIn = TypedDict('CardsRentalDisputeIn', {"end_user": str, "moment_id": str}, total=False)

# cards.rental_dispute — output
CardsRentalDisputeOut = TypedDict('CardsRentalDisputeOut', {"state": Literal['sent', 'draft_only'], "draft": str, "why": str, "act_id": str, "outcome": Dict[str, Any], "evidence_id": str}, total=False)

# cards.terms — input
CardsTermsIn = TypedDict('CardsTermsIn', {"product_id": str, "benefit": Literal['travel_insurance', 'car_rental', 'purchase_protection', 'extended_warranty', 'lounges', 'fx_fee', 'points', 'claims']}, total=False)

# cards.terms — output
CardsTermsOut = TypedDict('CardsTermsOut', {"product": Dict[str, Any], "benefits": Dict[str, Any], "sources": List[Any], "unread": List[Any], "note": str}, total=False)

# cards.which — input
CardsWhichIn = TypedDict('CardsWhichIn', {"end_user": str, "purchase": Dict[str, Any]}, total=False)

# cards.which — output
CardsWhichOut = TypedDict('CardsWhichOut', {"framing": Literal["Information from your cards' own terms. You decide."], "ordered_by": str, "net_view": str, "text": str, "skipped": List[Any], "cards": List[Dict[str, Any]]}, total=False)

# dive.onboard — input
DiveOnboardIn = TypedDict('DiveOnboardIn', {"url": str, "replay": bool}, total=False)

# dive.onboard — output
DiveOnboardOut = TypedDict('DiveOnboardOut', {"url": str, "started_at": str, "seconds": float, "stages": List[Dict[str, Any]], "reached": List[Literal['read', 'understood', 'how_it_books', 'value']], "cant_read": Dict[str, Any], "name": Union[str, None], "kind": Union[str, None], "rung": Union[int, None], "channel": Union[str, None], "pacioli": Dict[str, Any], "copies": List[Any], "reader": Union[Dict[str, Any], None], "instruction_like": List[Any], "footer": str, "replay": Dict[str, Any], "plain_read": Any, "venue_id": Any}, total=False)

# entry.check — input
EntryCheckIn = TypedDict('EntryCheckIn', {"end_user": str, "passport_item_id": str, "passport_country": str, "destinations": List[Dict[str, Any]]}, total=False)

# entry.check — output
EntryCheckOut = TypedDict('EntryCheckOut', {"passport": Union[Dict[str, Any], None], "destinations": List[Any], "say": str}, total=False)

# entry.prepare — input
EntryPrepareIn = TypedDict('EntryPrepareIn', {"end_user": str, "country": str, "passport_item_id": str, "trip": Dict[str, Any]}, total=False)

# entry.prepare — output
EntryPrepareOut = TypedDict('EntryPrepareOut', {"country": str, "permission": str, "official_url": str, "fields": List[Any], "passport": Union[Dict[str, Any], None], "fee": Union[Dict[str, Any], None], "quotes": List[Any], "you_do": List[Any], "say": str}, total=False)

# evidence.get — input
EvidenceGetIn = TypedDict('EvidenceGetIn', {"evidence_id": str}, total=False)

# evidence.get — output
EvidenceGetOut = TypedDict('EvidenceGetOut', {"evidence_id": str, "basis": Literal['measured'], "states_no_conclusion": Literal[True], "operation": str, "act_id": str, "intent_id": str, "input_digest": str, "produced_at": str, "outcome": Dict[str, Any], "approval": Dict[str, Any], "sources": List[Dict[str, Any]], "body_sha256": str}, total=False)

# evidence.verify — input
EvidenceVerifyIn = TypedDict('EvidenceVerifyIn', {"evidence": Dict[str, Any]}, total=False)

# evidence.verify — output
EvidenceVerifyOut = TypedDict('EvidenceVerifyOut', {"valid": bool, "recomputed_body_sha256": str, "reason": str}, total=False)

# group.book — input
GroupBookIn = TypedDict('GroupBookIn', {"movement_id": str, "mandate_id": str, "end_user": str, "worker": Dict[str, Any], "items": List[Dict[str, Any]], "replaces": str}, total=False)

# group.book — output
GroupBookOut = TypedDict('GroupBookOut', {"booking_id": str, "worker": Dict[str, Any], "state": Literal['booked', 'swapped_out', 'cancelled', 'incomplete', 'unknown'], "parts": List[Any], "refund": Dict[str, Any], "difference": Dict[str, Any], "evidence_id": str, "test": bool, "replaces": str, "mandate_id": str, "replaced_by": str, "movement_id": str, "why": str, "replayed": Any}, total=False)

# group.bookings — input
GroupBookingsIn = TypedDict('GroupBookingsIn', {"end_user": str, "movement_id": str}, total=False)

# group.bookings — output
GroupBookingsOut = TypedDict('GroupBookingsOut', {"bookings": List[Dict[str, Any]]}, total=False)

# group.cancel — input
GroupCancelIn = TypedDict('GroupCancelIn', {"end_user": str, "booking_id": str}, total=False)

# group.cancel — output
GroupCancelOut = TypedDict('GroupCancelOut', {"booking_id": str, "worker": Dict[str, Any], "state": Literal['booked', 'swapped_out', 'cancelled', 'incomplete', 'unknown'], "parts": List[Any], "refund": Dict[str, Any], "difference": Dict[str, Any], "evidence_id": str, "test": bool, "replaces": str, "replaced_by": str, "movement_id": Any}, total=False)

# group.swap — input
GroupSwapIn = TypedDict('GroupSwapIn', {"end_user": str, "booking_id": str, "flights": List[Dict[str, Any]], "worker": Dict[str, Any]}, total=False)

# group.swap — output
GroupSwapOut = TypedDict('GroupSwapOut', {"booking_id": str, "worker": Dict[str, Any], "state": Literal['booked', 'swapped_out', 'cancelled', 'incomplete', 'unknown'], "parts": List[Any], "refund": Dict[str, Any], "difference": Dict[str, Any], "evidence_id": str, "test": bool, "replaces": str, "replaced_by": str, "movement_id": Any}, total=False)

# keep.activity — input
KeepActivityIn = TypedDict('KeepActivityIn', {"end_user": str, "since": str, "limit": int}, total=False)

# keep.activity — output
KeepActivityOut = TypedDict('KeepActivityOut', {"items": List[Dict[str, Any]]}, total=False)

# keep.delete — input
KeepDeleteIn = TypedDict('KeepDeleteIn', {"end_user": str, "item_id": str}, total=False)

# keep.delete — output
KeepDeleteOut = TypedDict('KeepDeleteOut', {"deleted": int, "key_destroyed": bool, "evidence_id": str}, total=False)

# keep.list — input
KeepListIn = TypedDict('KeepListIn', {"end_user": str}, total=False)

# keep.list — output
KeepListOut = TypedDict('KeepListOut', {"items": List[Dict[str, Any]], "values_shown": Literal[False]}, total=False)

# keep.put — input
KeepPutIn = TypedDict('KeepPutIn', {"end_user": str, "type": str, "value": Dict[str, Any]}, total=False)

# keep.put — output
KeepPutOut = TypedDict('KeepPutOut', {"item_id": str, "type": str, "tier": Literal['free', 'yes', 'read_back'], "masked": str, "created_at": str, "last_used_at": str, "created": bool, "evidence_id": str}, total=False)

# keep.use — input
KeepUseIn = TypedDict('KeepUseIn', {"end_user": str, "item_id": str, "purpose": str, "hold_id": str}, total=False)

# keep.use — output
KeepUseOut = TypedDict('KeepUseOut', {"state": Literal['ready', 'needs_yes', 'sent_to_phone'], "masked": str, "fill_token": str, "tier": Literal['free', 'yes', 'read_back'], "line": str, "read_back": Dict[str, Any], "channel": str, "expires_at": str}, total=False)

# magellan.read_site — input
MagellanReadSiteIn = TypedDict('MagellanReadSiteIn', {"url": str, "purpose": Literal['operator', 'venue', 'registry', 'card_terms']}, total=False)

# magellan.read_site — output
MagellanReadSiteOut = TypedDict('MagellanReadSiteOut', {"url": str, "purpose": Literal['operator', 'venue', 'registry', 'card_terms'], "operator": Dict[str, Any], "offers": List[Dict[str, Any]], "partners": List[Dict[str, Any]], "contacts": List[Dict[str, Any]], "booking_channels": List[Dict[str, Any]], "instruction_like": List[Dict[str, Any]], "coverage": Dict[str, Any], "reader": Dict[str, Any], "benefits": List[Dict[str, Any]], "sources": List[Dict[str, Any]], "unread": List[Dict[str, Any]]}, total=False)

# messages.ad_cases — input
MessagesAdCasesIn = TypedDict('MessagesAdCasesIn', {"from": str, "text": str}, total=False)

# messages.ad_cases — output
MessagesAdCasesOut = TypedDict('MessagesAdCasesOut', {"linked": bool, "why": Literal['closed', 'not_linked'], "named": List[str], "cases": List[Dict[str, Any]]}, total=False)

# messages.replies — input
MessagesRepliesIn = TypedDict('MessagesRepliesIn', {"end_user": str, "number": str}, total=False)

# messages.replies — output
MessagesRepliesOut = TypedDict('MessagesRepliesOut', {"replies": List[Dict[str, Any]]}, total=False)

# messages.send_email — input
MessagesSendEmailIn = TypedDict('MessagesSendEmailIn', {"end_user": str, "to": Dict[str, Any], "subject": str, "body": str}, total=False)

# messages.send_email — output
MessagesSendEmailOut = TypedDict('MessagesSendEmailOut', {"act_id": str, "intent_id": str, "outcome": Dict[str, Any], "evidence_id": str, "message": Dict[str, Any]}, total=False)

# messages.send_whatsapp — input
MessagesSendWhatsappIn = TypedDict('MessagesSendWhatsappIn', {"end_user": str, "to": Dict[str, Any], "text": str, "on_behalf_of": str}, total=False)

# messages.send_whatsapp — output
MessagesSendWhatsappOut = TypedDict('MessagesSendWhatsappOut', {"act_id": str, "intent_id": str, "outcome": Dict[str, Any], "evidence_id": str, "message": Dict[str, Any]}, total=False)

# messages.typing — input
MessagesTypingIn = TypedDict('MessagesTypingIn', {"message_id": str}, total=False)

# messages.typing — output
MessagesTypingOut = TypedDict('MessagesTypingOut', {"ok": bool, "status": Union[int, str, None], "error": str}, total=False)

# messages.whatsapp_inbound — input
MessagesWhatsappInboundIn = TypedDict('MessagesWhatsappInboundIn', {"from": str, "to": str, "text": str, "received_at": str, "message_id": str, "button": Dict[str, Any], "guest": bool, "account_email": str, "space": str, "media": List[Dict[str, Any]], "replied_to": str}, total=False)

# messages.whatsapp_inbound — output
MessagesWhatsappInboundOut = TypedDict('MessagesWhatsappInboundOut', {"conversation_role": Dict[str, Any], "matched": bool, "kept": bool, "why": str, "reply_id": str, "received_at": str, "opted_out": bool, "window_open_until": Union[str, None], "booking": Union[Dict[str, Any], None], "ad": str, "replied": bool, "declined": bool, "ignored": str, "asked": Any, "message_id": Any, "released": Any}, total=False)

# messages.whatsapp_switch — input
MessagesWhatsappSwitchIn = TypedDict('MessagesWhatsappSwitchIn', {"from": str, "product": str, "message_id": str}, total=False)

# messages.whatsapp_switch — output
MessagesWhatsappSwitchOut = TypedDict('MessagesWhatsappSwitchOut', {"product": str, "was": Union[str, None], "dropped": List[str], "since": str}, total=False)

# money.bag_check — input
MoneyBagCheckIn = TypedDict('MoneyBagCheckIn', {"end_user": str, "booking_reference": str, "passengers": List[str], "bag": Dict[str, Any]}, total=False)

# money.bag_check — output
MoneyBagCheckOut = TypedDict('MoneyBagCheckOut', {"case_id": str, "verdict": Literal['yes', 'no', 'late', 'unknown'], "deadlines": List[Any], "file_by": Union[str, None], "limit": List[Any], "note": str, "say": str}, total=False)

# money.bag_claim — input
MoneyBagClaimIn = TypedDict('MoneyBagClaimIn', {"end_user": str, "case_id": str, "booking_reference": str, "passengers": List[str], "pir_reference": str}, total=False)

# money.bag_claim — output
MoneyBagClaimOut = TypedDict('MoneyBagClaimOut', {"case_id": str, "state": Literal['draft_only', 'filed', 'form_prepared'], "draft": List[Any], "outcome": Dict[str, Any], "evidence_id": str, "to": str, "say": str, "form_url": str, "fields": List[str]}, total=False)

# money.claim_simulate_reply — input
MoneyClaimSimulateReplyIn = TypedDict('MoneyClaimSimulateReplyIn', {"end_user": str, "case_id": str, "text": str}, total=False)

# money.claim_simulate_reply — output
MoneyClaimSimulateReplyOut = TypedDict('MoneyClaimSimulateReplyOut', {"case_id": str, "kind": str, "state": str, "deadlines": List[Any], "reminders": List[Any], "next": Union[Dict[str, Any], None], "replies": List[Any], "reference": str, "to": str, "say": str}, total=False)

# money.claim_status — input
MoneyClaimStatusIn = TypedDict('MoneyClaimStatusIn', {"end_user": str, "case_id": str}, total=False)

# money.claim_status — output
MoneyClaimStatusOut = TypedDict('MoneyClaimStatusOut', {"case_id": str, "kind": str, "state": str, "deadlines": List[Any], "reminders": List[Any], "next": Union[Dict[str, Any], None], "replies": List[Any], "reference": str, "to": str, "say": str}, total=False)

# money.flight_check — input
MoneyFlightCheckIn = TypedDict('MoneyFlightCheckIn', {"end_user": str, "flight": Dict[str, Any], "booking_reference": str, "passengers": List[str]}, total=False)

# money.flight_check — output
MoneyFlightCheckOut = TypedDict('MoneyFlightCheckOut', {"case_id": str, "verdict": Literal['yes', 'no', 'depends', 'unknown', 'not_yet'], "amount": Union[Dict[str, Any], None], "distance_km": Union[int, None], "band": Union[str, None], "reduction_percent": int, "rules": List[Any], "why": List[Any], "read_at_source": bool, "note": str, "case_law": Union[str, None], "say": str}, total=False)

# money.flight_claim — input
MoneyFlightClaimIn = TypedDict('MoneyFlightClaimIn', {"end_user": str, "case_id": str, "booking_reference": str, "passengers": List[str]}, total=False)

# money.flight_claim — output
MoneyFlightClaimOut = TypedDict('MoneyFlightClaimOut', {"case_id": str, "state": Literal['draft_only', 'filed', 'form_prepared'], "draft": List[Any], "outcome": Dict[str, Any], "evidence_id": str, "to": str, "say": str, "form_url": str, "fields": List[str]}, total=False)

# outcomes.list — input
OutcomesListIn = TypedDict('OutcomesListIn', {"from": str, "to": str, "limit": int}, total=False)

# outcomes.list — output
OutcomesListOut = TypedDict('OutcomesListOut', {"outcomes": List[Dict[str, Any]]}, total=False)

# outcomes.mark_test — input
OutcomesMarkTestIn = TypedDict('OutcomesMarkTestIn', {"outcome_ids": List[str], "created_before": str, "test": bool, "refs": List[str]}, total=False)

# outcomes.mark_test — output
OutcomesMarkTestOut = TypedDict('OutcomesMarkTestOut', {"marked": int, "test": bool, "outcome_ids": List[str], "say": str}, total=False)

# outcomes.record — input
OutcomesRecordIn = TypedDict('OutcomesRecordIn', {"kind": Literal['booking', 'change', 'late', 'cancel'], "ref": str, "end_user": str, "venue": str, "sector": str, "city": str, "rung": Literal['api', 'zero_touch', 'human_tap', 'request_reply', 'phone', 'person'], "channel": Literal['api', 'web_form', 'page_handover', 'whatsapp', 'instagram', 'email', 'phone', 'sms', 'none'], "state": Literal['asked', 'sent', 'confirmed', 'declined', 'failed', 'handed_to_person'], "asked_at": str, "sent_at": str, "at": str, "confirmation_quote": str, "failure_reason": str, "test": bool}, total=False)

# outcomes.record — output
OutcomesRecordOut = TypedDict('OutcomesRecordOut', {"outcome_id": str, "ref": str, "venue": str, "sector": Union[str, None], "city": Union[str, None], "rung": str, "channel": str, "state": str, "asked_at": str, "sent_at": Union[str, None], "decided_at": Union[str, None], "confirmation_quote": str, "failure_reason": str, "time_to_confirm_s": int, "test": bool, "kind": Any, "time_to_outcome_s": Any}, total=False)

# outcomes.report — input
OutcomesReportIn = TypedDict('OutcomesReportIn', {"from": str, "to": str, "by": List[Literal['rung', 'sector', 'city', 'kind', 'channel']]}, total=False)

# outcomes.report — output
OutcomesReportOut = TypedDict('OutcomesReportOut', {"window": Dict[str, Any], "overall": Dict[str, Any], "by_rung": List[Dict[str, Any]], "by_sector": List[Dict[str, Any]], "by_city": List[Dict[str, Any]], "say": str, "note": str, "excluded_test": int, "billing": Dict[str, Any], "by_kind": List[Dict[str, Any]], "by_channel": List[Dict[str, Any]]}, total=False)

# outcomes.update — input
OutcomesUpdateIn = TypedDict('OutcomesUpdateIn', {"outcome_id": str, "ref": str, "state": Literal['sent', 'confirmed', 'declined', 'failed', 'handed_to_person'], "at": str, "confirmation_quote": str, "failure_reason": str}, total=False)

# outcomes.update — output
OutcomesUpdateOut = TypedDict('OutcomesUpdateOut', {"outcome_id": str, "ref": str, "venue": str, "sector": Union[str, None], "city": Union[str, None], "rung": str, "channel": str, "state": str, "asked_at": str, "sent_at": Union[str, None], "decided_at": Union[str, None], "confirmation_quote": str, "failure_reason": str, "time_to_confirm_s": int, "test": bool, "kind": Any, "time_to_outcome_s": Any}, total=False)

# registry.change_list — input
RegistryChangeListIn = TypedDict('RegistryChangeListIn', {"job_id": str}, total=False)

# registry.change_list — output
RegistryChangeListOut = TypedDict('RegistryChangeListOut', {"job_id": Union[str, None], "count": int, "lines": List[Dict[str, Any]], "csv": str, "note": str}, total=False)

# registry.countries — input
RegistryCountriesIn = TypedDict('RegistryCountriesIn', {"region": str, "has": List[Literal['company', 'ubo', 'insolvency', 'court', 'land', 'criminal', 'professional', 'vehicle', 'sanctions', 'other']], "min_confidence": Literal['frontier', 'desk', 'read_at_source', 'proven']}, total=False)

# registry.countries — output
RegistryCountriesOut = TypedDict('RegistryCountriesOut', {"note": str, "jurisdictions": List[Dict[str, Any]]}, total=False)

# registry.documents — input
RegistryDocumentsIn = TypedDict('RegistryDocumentsIn', {"jurisdiction": str, "kind": str, "subject": Literal['company', 'person', 'property']}, total=False)

# registry.documents — output
RegistryDocumentsOut = TypedDict('RegistryDocumentsOut', {"jurisdiction": str, "documents": List[Dict[str, Any]]}, total=False)

# registry.get — input
RegistryGetIn = TypedDict('RegistryGetIn', {"jurisdiction": str}, total=False)

# registry.get — output
RegistryGetOut = TypedDict('RegistryGetOut', {"jurisdiction": Dict[str, Any], "sources": Dict[str, Any], "registers": List[Dict[str, Any]]}, total=False)

# registry.obtain_plan — input
RegistryObtainPlanIn = TypedDict('RegistryObtainPlanIn', {"jurisdiction": str, "document_id": str, "need": Dict[str, Any], "identifier": str, "actor": Literal['agapi', 'person', 'subject']}, total=False)

# registry.obtain_plan — output
RegistryObtainPlanOut = TypedDict('RegistryObtainPlanOut', {"jurisdiction": str, "actor": str, "obtain": str, "obtainable_by_agapi": Literal['yes', 'with_human', 'no', 'unknown'], "excluded": List[Dict[str, Any]], "routes": List[Dict[str, Any]]}, total=False)

# registry.row_results — input
RegistryRowResultsIn = TypedDict('RegistryRowResultsIn', {"job_id": str, "jurisdiction": str, "verdict": Literal['verified', 'changed', 'gone', 'unreachable'], "limit": int}, total=False)

# registry.row_results — output
RegistryRowResultsOut = TypedDict('RegistryRowResultsOut', {"results": List[Dict[str, Any]], "count": int}, total=False)

# registry.verify — input
RegistryVerifyIn = TypedDict('RegistryVerifyIn', {"claim_id": str, "route_id": str}, total=False)

# registry.verify — output
RegistryVerifyOut = TypedDict('RegistryVerifyOut', {"state": Literal['fresh', 'drifted', 'broken'], "read_at": str, "quote_still_present": bool, "failure_layer": Literal['tls', 'http', 'robots', 'content', 'policy'], "checked": List[Any], "reverify_after": str}, total=False)

# registry.wave_resume — input
RegistryWaveResumeIn = TypedDict('RegistryWaveResumeIn', {"job_id": str}, total=False)

# registry.wave_resume — output
RegistryWaveResumeOut = TypedDict('RegistryWaveResumeOut', {"job_id": str, "state": str, "jurisdictions": List[str], "started_at": str, "finished_at": Union[str, None], "tasks": Dict[str, Any], "rows": Dict[str, Any], "pages": int, "failed": List[Dict[str, Any]], "max_parallel": int, "requeued": int}, total=False)

# registry.wave_run — input
RegistryWaveRunIn = TypedDict('RegistryWaveRunIn', {"jurisdictions": List[str], "note": str}, total=False)

# registry.wave_run — output
RegistryWaveRunOut = TypedDict('RegistryWaveRunOut', {"job_id": str, "state": str, "jurisdictions": List[str], "started_at": str, "finished_at": Union[str, None], "tasks": Dict[str, Any], "rows": Dict[str, Any], "pages": int, "failed": List[Dict[str, Any]], "max_parallel": int, "requeued": int}, total=False)

# registry.wave_status — input
RegistryWaveStatusIn = TypedDict('RegistryWaveStatusIn', {"job_id": str}, total=False)

# registry.wave_status — output
RegistryWaveStatusOut = TypedDict('RegistryWaveStatusOut', {"job_id": str, "state": str, "jurisdictions": List[str], "started_at": str, "finished_at": Union[str, None], "tasks": Dict[str, Any], "rows": Dict[str, Any], "pages": int, "failed": List[Dict[str, Any]], "max_parallel": int, "requeued": int}, total=False)

# sandbox.ad_case — input
SandboxAdCaseIn = TypedDict('SandboxAdCaseIn', {"case_id": str, "email": str, "door_down_seconds": int, "withdraw_interview": Dict[str, Any]}, total=False)

# sandbox.ad_case — output
SandboxAdCaseOut = TypedDict('SandboxAdCaseOut', {"door_down_until": int, "case_id": str, "company": Union[str, None], "timeline": List[Dict[str, Any]], "client_supplied_sources": List[Dict[str, Any]]}, total=False)

# sandbox.ad_open_case — input
SandboxAdOpenCaseIn = TypedDict('SandboxAdOpenCaseIn', {"email": str, "name": str, "interview": Dict[str, Any], "opened_at": str}, total=False)

# sandbox.ad_open_case — output
SandboxAdOpenCaseOut = TypedDict('SandboxAdOpenCaseOut', {"case_id": str, "name": str, "opened_at": str, "opened_on": Literal['desktop'], "interview": Any}, total=False)

# sandbox.link_proof — input
SandboxLinkProofIn = TypedDict('SandboxLinkProofIn', {"url": str, "expect": List[str], "inspect": bool}, total=False)

# sandbox.link_proof — output
SandboxLinkProofOut = TypedDict('SandboxLinkProofOut', {"url": str, "proven": bool, "matched": Dict[str, Any], "fields": List[Any], "forms": List[Any], "shot": Union[str, None]}, total=False)

# sandbox.messages — input
SandboxMessagesIn = TypedDict('SandboxMessagesIn', {"end_user_id": str, "since": str}, total=False)

# sandbox.messages — output
SandboxMessagesOut = TypedDict('SandboxMessagesOut', {"messages": List[Dict[str, Any]]}, total=False)

# sandbox.platform_prepare — input
SandboxPlatformPrepareIn = TypedDict('SandboxPlatformPrepareIn', {"end_user": str, "date": str, "time": str, "party": int, "person": Dict[str, Any], "variant": Literal['basic', 'lists', 'no_table'], "choices": Dict[str, Any]}, total=False)

# sandbox.platform_prepare — output
SandboxPlatformPrepareOut = TypedDict('SandboxPlatformPrepareOut', {"prepared_id": str, "page": str, "decision": str, "say": str}, total=False)

# sandbox.platform_walk — input
SandboxPlatformWalkIn = TypedDict('SandboxPlatformWalkIn', {"end_user": str, "url": str, "date": str, "time": str, "party": int, "first_name": str, "last_name": str, "phone": str, "email": str, "notes": str, "choices": Dict[str, Any], "press": bool, "venue": str, "city": str}, total=False)

# sandbox.platform_walk — output
SandboxPlatformWalkOut = TypedDict('SandboxPlatformWalkOut', {"decision": str, "say": str, "walked": bool, "dry_run": bool, "state": str, "why": Union[str, None], "pressed": bool, "confirmation": Union[Dict[str, Any], None], "steps": List[Any], "shot": Union[str, None], "final_button": Any, "hand_over": Any, "refused": Any, "stand_in": Any, "stopped_say": Any, "target": Any, "alternatives": List[Dict[str, Any]], "times": List[str]}, total=False)

# sandbox.simulate_approval — input
SandboxSimulateApprovalIn = TypedDict('SandboxSimulateApprovalIn', {"read_back_id": str, "said": str, "after_seconds": int}, total=False)

# sandbox.simulate_approval — output
SandboxSimulateApprovalOut = TypedDict('SandboxSimulateApprovalOut', {"approval_id": str, "state": Literal['valid', 'void', 'expired'], "decision": str}, total=False)

# sandbox.simulate_call — input
SandboxSimulateCallIn = TypedDict('SandboxSimulateCallIn', {"outbound": bool, "repeat_each": bool, "slow_model_ms": int, "number": str, "says": List[str]}, total=False)

# sandbox.simulate_call — output
SandboxSimulateCallOut = TypedDict('SandboxSimulateCallOut', {"call_sid": str, "said": List[Dict[str, Any]], "state": str, "ended": Union[str, None], "posted": bool, "case": Union[Dict[str, Any], None], "requests": int, "slowest_ms": int, "budget_ms": int, "repeats_differed": int}, total=False)

# sandbox.simulate_reply — input
SandboxSimulateReplyIn = TypedDict('SandboxSimulateReplyIn', {"number": str, "text": str}, total=False)

# sandbox.simulate_reply — output
SandboxSimulateReplyOut = TypedDict('SandboxSimulateReplyOut', {"reply_id": str, "received_at": str, "opted_out": bool, "window_open_until": Union[str, None]}, total=False)

# sandbox.wa_template — input
SandboxWaTemplateIn = TypedDict('SandboxWaTemplateIn', {"name": Literal['kanoe_venue_cancel_v2', 'kanoe_venue_change_v1', 'kanoe_venue_late_v1'], "lang": Literal['en', 'es'], "status": Literal['approved', 'pending', 'rejected']}, total=False)

# sandbox.wa_template — output
SandboxWaTemplateOut = TypedDict('SandboxWaTemplateOut', {"name": str, "lang": str, "status": str, "approved": bool}, total=False)

# sources.get — input
SourcesGetIn = TypedDict('SourcesGetIn', {"copy_id": str, "claim_id": str, "format": Literal['original', 'pdf']}, total=False)

# sources.get — output
SourcesGetOut = TypedDict('SourcesGetOut', {"copy_id": str, "url": str, "expires_at": str, "sha256": str, "format": Literal['pdf', 'html'], "read_at": str, "source_url": str, "reader_kind": str, "role": str, "size": int, "pdf_available": Any, "rendering": Any}, total=False)

# subscriptions.cancel — input
SubscriptionsCancelIn = TypedDict('SubscriptionsCancelIn', {"end_user": str, "subscription_id": str, "route": Literal['email', 'page'], "name": str, "account_email": str}, total=False)

# subscriptions.cancel — output
SubscriptionsCancelOut = TypedDict('SubscriptionsCancelOut', {"act_id": str, "intent_id": str, "outcome": Dict[str, Any], "evidence_id": str, "subscription": Dict[str, Any]}, total=False)

# subscriptions.cancel_plan — input
SubscriptionsCancelPlanIn = TypedDict('SubscriptionsCancelPlanIn', {"end_user": str, "subscription_id": str, "site_url": str}, total=False)

# subscriptions.cancel_plan — output
SubscriptionsCancelPlanOut = TypedDict('SubscriptionsCancelPlanOut', {"subscription_id": str, "merchant": str, "routes": List[Dict[str, Any]], "never": str}, total=False)

# subscriptions.find — input
SubscriptionsFindIn = TypedDict('SubscriptionsFindIn', {"end_user": str, "statement": Dict[str, Any], "emails": Dict[str, Any]}, total=False)

# subscriptions.find — output
SubscriptionsFindOut = TypedDict('SubscriptionsFindOut', {"subscriptions": List[Dict[str, Any]], "monthly_total": List[Dict[str, Any]], "likely_unused": int, "note": str, "statement": Dict[str, Any], "emails": Dict[str, Any]}, total=False)

# travel.find_flights — input
TravelFindFlightsIn = TypedDict('TravelFindFlightsIn', {"origin": Dict[str, Any], "destination": Dict[str, Any], "date": str, "passengers": int, "preferences": List[Literal['direct', 'morning', 'afternoon', 'evening']], "allow_substitution": bool}, total=False)

# travel.find_flights — output
TravelFindFlightsOut = TypedDict('TravelFindFlightsOut', {"offers": List[Dict[str, Any]], "coverage": Dict[str, Any], "substituted": List[Dict[str, Any]]}, total=False)

# travel.find_stays — input
TravelFindStaysIn = TypedDict('TravelFindStaysIn', {"city": Dict[str, Any], "check_in": str, "nights": int, "party": int, "preference": str}, total=False)

# travel.find_stays — output
TravelFindStaysOut = TypedDict('TravelFindStaysOut', {"stays": List[Dict[str, Any]], "coverage": Dict[str, Any], "substituted": List[Dict[str, Any]]}, total=False)

# trip.cancel — input
TripCancelIn = TypedDict('TripCancelIn', {"act_id": str, "reason": str}, total=False)

# trip.cancel — output
TripCancelOut = TypedDict('TripCancelOut', {"act_id": str, "outcome": Dict[str, Any], "refund": Dict[str, Any], "evidence_id": str}, total=False)

# trip.complete — input
TripCompleteIn = TypedDict('TripCompleteIn', {"hold_id": str, "payment": Dict[str, Any]}, total=False)

# trip.complete — output
TripCompleteOut = TypedDict('TripCompleteOut', {"act_id": str, "intent_id": str, "outcome": Dict[str, Any], "evidence_id": str}, total=False)

# trip.hold — input
TripHoldIn = TypedDict('TripHoldIn', {"end_user": str, "items": List[Dict[str, Any]], "travellers": List[Dict[str, Any]], "irreversible": bool}, total=False)

# trip.hold — output
TripHoldOut = TypedDict('TripHoldOut', {"hold_id": str, "intent_id": str, "read_back": Dict[str, Any], "items": List[Dict[str, Any]], "total": Dict[str, Any], "expires_at": str}, total=False)

# trip.plan — input
TripPlanIn = TypedDict('TripPlanIn', {"person": Dict[str, Any], "party": int, "rooms": int, "start": str, "arrive": Dict[str, Any], "depart": Dict[str, Any], "legs": List[Dict[str, Any]], "activity": Dict[str, Any], "stay": Dict[str, Any], "dining": Dict[str, Any], "transfer": Dict[str, Any], "ask": str}, total=False)

# trip.plan — output
TripPlanOut = TypedDict('TripPlanOut', {"trip_id": Union[str, None], "status": Literal['planning', 'ready', 'failed', 'interrupted', 'needs'], "days": List[Any], "pacioli": Dict[str, Any], "how_far": Dict[str, Any], "nothing_sent": bool, "say": str, "next": Dict[str, Any], "ask": str, "defaults_used": List[Any], "understood": Dict[str, Any], "bases": Any, "complete": Any, "limits": Any, "unavailable": Any, "version": Any}, total=False)

# trip.plan_get — input
TripPlanGetIn = TypedDict('TripPlanGetIn', {"trip_id": str}, total=False)

# trip.plan_get — output
TripPlanGetOut = TypedDict('TripPlanGetOut', {"trip_id": Union[str, None], "status": Literal['planning', 'ready', 'failed', 'interrupted', 'needs'], "days": List[Any], "pacioli": Dict[str, Any], "how_far": Dict[str, Any], "nothing_sent": bool, "say": str, "next": Dict[str, Any], "ask": str, "defaults_used": List[Any], "understood": Dict[str, Any], "bases": Any, "complete": Any, "limits": Any, "version": Any}, total=False)

# usage.get — input
UsageGetIn = TypedDict('UsageGetIn', {"from": str, "to": str}, total=False)

# usage.get — output
UsageGetOut = TypedDict('UsageGetOut', {"account": str, "from": str, "to": str, "by_operation": List[Dict[str, Any]], "total_cost_units": int, "budget_remaining": int}, total=False)

# users.confirm_whatsapp — input
UsersConfirmWhatsappIn = TypedDict('UsersConfirmWhatsappIn', {"t": int, "nonce": str, "wa_id": str, "message_id": str, "text": str, "signature": str}, total=False)

# users.confirm_whatsapp — output
UsersConfirmWhatsappOut = TypedDict('UsersConfirmWhatsappOut', {"end_user_id": str, "number": str, "state": Literal['verified'], "destinations": List[Any], "say": str, "account": Any, "created_at": Any, "external_ref": Any}, total=False)

# users.link_whatsapp — input
UsersLinkWhatsappIn = TypedDict('UsersLinkWhatsappIn', {"end_user": str, "number": str}, total=False)

# users.link_whatsapp — output
UsersLinkWhatsappOut = TypedDict('UsersLinkWhatsappOut', {"end_user": str, "number": str, "state": Literal['awaiting_message', 'verified'], "sent": bool, "code": str, "text": str, "expires_at": str, "say": str}, total=False)

# users.register — input
UsersRegisterIn = TypedDict('UsersRegisterIn', {"external_ref": str, "destinations": List[Dict[str, Any]]}, total=False)

# users.register — output
UsersRegisterOut = TypedDict('UsersRegisterOut', {"end_user_id": str, "account": str, "external_ref": str, "destinations": List[Dict[str, Any]], "sdk_devices": List[Dict[str, Any]], "created_at": str}, total=False)

# users.verify_destination — input
UsersVerifyDestinationIn = TypedDict('UsersVerifyDestinationIn', {"end_user_id": str, "channel": Literal['sms', 'whatsapp', 'email'], "value": str, "code": str}, total=False)

# users.verify_destination — output
UsersVerifyDestinationOut = TypedDict('UsersVerifyDestinationOut', {"end_user_id": str, "account": str, "external_ref": str, "destinations": List[Dict[str, Any]], "sdk_devices": List[Dict[str, Any]], "created_at": str}, total=False)

# venue.booking_status — input
VenueBookingStatusIn = TypedDict('VenueBookingStatusIn', {"act_id": str}, total=False)

# venue.booking_status — output
VenueBookingStatusOut = TypedDict('VenueBookingStatusOut', {"stay": Dict[str, Any], "change": Dict[str, Any], "at": str, "party": Union[int, str], "answers": Dict[str, Any], "act_id": str, "venue": str, "channel": str, "state": str, "outcome_id": Union[str, None], "venue_words": Dict[str, Any], "updated_at": str, "say": str, "next_call": Dict[str, Any], "no_answers": int, "ask": str, "choices": List[Any], "next_step": Dict[str, Any], "rules_version": str, "calls": Dict[str, Any], "booking": Dict[str, Any], "follow_up": Dict[str, Any], "watch": Dict[str, Any], "opted_out": bool, "opted_out_at": Union[str, None], "calendar": Any}, total=False)

# venue.bookings — input
VenueBookingsIn = TypedDict('VenueBookingsIn', {"end_user": str, "from": str, "include_cancelled": bool}, total=False)

# venue.bookings — output
VenueBookingsOut = TypedDict('VenueBookingsOut', {"bookings": List[Dict[str, Any]]}, total=False)

# venue.call_again — input
VenueCallAgainIn = TypedDict('VenueCallAgainIn', {"act_id": str, "reason": Literal['person_asked', 'R3', 'R5', 'R6'], "end_user": str}, total=False)

# venue.call_again — output
VenueCallAgainOut = TypedDict('VenueCallAgainOut', {"act_id": str, "status": Literal['calling', 'not_allowed'], "reason": str, "venue": str, "approval": Dict[str, Any], "call_plan": Dict[str, Any], "why": List[Any], "next_call": Dict[str, Any], "say": str, "takeover": Dict[str, Any]}, total=False)

# venue.call_attempt — input
VenueCallAttemptIn = TypedDict('VenueCallAttemptIn', {"act_id": str, "outcome": Literal['confirmed', 'proposed', 'declined', 'no_answer'], "venue_words": str, "answered_by": Literal['human', 'machine', 'none']}, total=False)

# venue.call_attempt — output
VenueCallAttemptOut = TypedDict('VenueCallAttemptOut', {"act_id": str, "status": Literal['recorded', 'refused'], "attempt": int, "outcome": str, "state": str, "rule": str, "reason": Union[str, None], "recorded": bool, "next_call": Dict[str, Any], "next_step": Dict[str, Any], "venue_words": Dict[str, Any], "say": str, "no_answers": int, "ask": str, "choices": List[Any], "rules_version": str, "approval_id": Union[str, None]}, total=False)

# venue.cancel_booking — input
VenueCancelBookingIn = TypedDict('VenueCancelBookingIn', {"end_user": str, "act_id": str, "reason": str}, total=False)

# venue.cancel_booking — output
VenueCancelBookingOut = TypedDict('VenueCancelBookingOut', {"act_id": str, "status": Literal['sent', 'not_allowed', 'already_cancelled', 'cancelled', 'person_sends', 'held'], "route": str, "manage_url": str, "link": str, "message": Dict[str, Any], "venue": str, "channel": Union[str, None], "cancel_act_id": str, "evidence_id": str, "why": List[Any], "takeover": Union[str, None], "say": str, "venue_words": Any}, total=False)

# venue.change_booking — input
VenueChangeBookingIn = TypedDict('VenueChangeBookingIn', {"check_in": str, "nights": int, "end_user": str, "act_id": str, "kind": Literal['change', 'late'], "at": str, "party": int, "arrive": str}, total=False)

# venue.change_booking — output
VenueChangeBookingOut = TypedDict('VenueChangeBookingOut', {"act_id": str, "status": Literal['sent', 'not_allowed', 'person_sends', 'held'], "venue": str, "channel": Union[str, None], "route": str, "change_act_id": str, "evidence_id": str, "why": List[Any], "takeover": Dict[str, Any], "manage_url": str, "link": str, "message": Dict[str, Any], "say": str}, total=False)

# venue.confirmation — input
VenueConfirmationIn = TypedDict('VenueConfirmationIn', {"act_id": str, "prepared_id": str, "end_user": str, "emails": List[Dict[str, Any]]}, total=False)

# venue.confirmation — output
VenueConfirmationOut = TypedDict('VenueConfirmationOut', {"kind": str, "trip": Dict[str, Any], "already": bool, "why": str, "matched": bool, "act_id": Union[str, None], "state": Union[str, None], "outcome": Literal['confirmed', 'declined', 'changed', 'proposed', None], "reference": Union[str, None], "booking": Dict[str, Any], "say_text": str, "relied_on": Dict[str, Any], "emails": List[Dict[str, Any]], "calendar": Union[Dict[str, Any], None], "version": str, "rules_version": str}, total=False)

# venue.discover — input
VenueDiscoverIn = TypedDict('VenueDiscoverIn', {"what": str, "where": Dict[str, Any], "open_at": str, "dates": Dict[str, Any], "when_words": str, "party": int, "near": str, "all": bool, "intent": Literal['book', 'takeaway', 'delivery', 'eat_now', 'browse']}, total=False)

# venue.discover — output
VenueDiscoverOut = TypedDict('VenueDiscoverOut', {"kind": Dict[str, Any], "handover": List[Dict[str, Any]], "trip": Dict[str, Any], "next": str, "unhandled": bool, "what": str, "where": str, "service": Union[Dict[str, Any], None], "options": List[Dict[str, Any]], "groups": List[Dict[str, Any]], "pick": Union[Dict[str, Any], None], "say": str, "say_text": str, "refused": bool, "category": Dict[str, Any], "checks": Dict[str, Any], "coverage": Dict[str, Any], "web_search": Dict[str, Any], "ranking_version": str, "policy_version": str, "sources_url": str, "intent": Dict[str, Any]}, total=False)

# venue.handed_over — input
VenueHandedOverIn = TypedDict('VenueHandedOverIn', {"end_user": str, "prepared_id": str, "how": Literal['platform', 'whatsapp_person', 'their_page'], "link": str, "external_ref": str}, total=False)

# venue.handed_over — output
VenueHandedOverOut = TypedDict('VenueHandedOverOut', {"act_id": str, "state": str, "again": bool}, total=False)

# venue.manage_options — input
VenueManageOptionsIn = TypedDict('VenueManageOptionsIn', {"end_user": str, "act_id": str}, total=False)

# venue.manage_options — output
VenueManageOptionsOut = TypedDict('VenueManageOptionsOut', {"act_id": str, "kind": str, "operator": str, "fare": Union[str, None], "departs_at": str, "known": bool, "options": List[Dict[str, Any]], "where": Dict[str, Any], "rules": Dict[str, Any], "say_text": str}, total=False)

# venue.person_report — input
VenuePersonReportIn = TypedDict('VenuePersonReportIn', {"report": Literal['sent', 'confirmed', 'declined', 'changed', 'check_in_asked'], "prepared_id": str, "act_id": str, "end_user": str, "words": str, "changed": Dict[str, Any]}, total=False)

# venue.person_report — output
VenuePersonReportOut = TypedDict('VenuePersonReportOut', {"act_id": str, "state": Literal['sent_by_person', 'confirmed', 'declined', 'changed', 'replied'], "say": str, "check_in": Union[Dict[str, Any], None], "calendar": Union[Dict[str, Any], None], "rules_version": str}, total=False)

# venue.prepare_booking — input
VenuePrepareBookingIn = TypedDict('VenuePrepareBookingIn', {"external_ref": str, "url": str, "place": Dict[str, Any], "person": Dict[str, Any], "date": str, "time": str, "party": int, "notes": str, "call": Dict[str, Any], "link": Dict[str, Any], "stay": Dict[str, Any], "answers": Dict[str, Any], "include_sensitive": bool, "clock": str, "end_user": str, "choices": Dict[str, Any], "open_slot": Literal['quote', 'whenever']}, total=False)

# venue.prepare_booking — output
VenuePrepareBookingOut = TypedDict('VenuePrepareBookingOut', {"venue_id": str, "venue": str, "status": str, "channel": Union[str, None], "rung": Union[int, None], "when": str, "party": int, "submitted": bool, "fills": List[Any], "missing": List[Any], "form": Union[Dict[str, Any], None], "human_step": str, "zero_touch_allowed": bool, "zero_touch_why": List[Any], "link": str, "expires_at": str, "say": str, "prepared_id": str, "routes": List[Literal['page', 'call']], "stay": Dict[str, Any], "decision": Dict[str, Any], "ask": Dict[str, Any], "hand_over": Dict[str, Any], "page_check": Dict[str, Any], "policy": Dict[str, Any], "checks": Dict[str, Any], "message": Dict[str, Any], "person_send": Dict[str, Any], "watch": Dict[str, Any], "open_slot": Any}, total=False)

# venue.profile — input
VenueProfileIn = TypedDict('VenueProfileIn', {"call": Dict[str, Any], "url": str, "place": Dict[str, Any], "refresh": bool, "link": Dict[str, Any], "clock": str}, total=False)

# venue.profile — output
VenueProfileOut = TypedDict('VenueProfileOut', {"venue_id": str, "site": str, "url": str, "read_at": Union[str, None], "facts": Dict[str, Any], "kind": Union[str, None], "photos": List[Any], "booking": Dict[str, Any], "confirm": Dict[str, Any], "form": Union[Dict[str, Any], None], "form_note": str, "withheld": List[Any], "cant_read": Dict[str, Any], "cached": bool, "age_days": int, "robots": Union[str, None], "channels": List[Dict[str, Any]], "listing": Dict[str, Any], "reservable": Dict[str, Any], "decision": Dict[str, Any], "web_site_unreadable": Dict[str, Any], "web_search": Dict[str, Any], "alternatives": Any, "hours_now": Any, "identity": Dict[str, Any], "own_name": Dict[str, Any], "listing_whatsapp": Any, "read_rules": Any, "refresh": Any, "site_unreadable": Any, "social_link": Any}, total=False)

# venue.recognition — input
VenueRecognitionIn = TypedDict('VenueRecognitionIn', {"place": Dict[str, Any], "location": Dict[str, Any], "search": bool}, total=False)

# venue.recognition — output
VenueRecognitionOut = TypedDict('VenueRecognitionOut', {"place": Dict[str, Any], "recognition": Union[Dict[str, Any], None], "say_text": Union[str, None], "searched": bool}, total=False)

# venue.submit_booking — input
VenueSubmitBookingIn = TypedDict('VenueSubmitBookingIn', {"end_user": str, "prepared_id": str, "choices": Dict[str, Any], "route": Literal['auto', 'call'], "mandate_id": str}, total=False)

# venue.submit_booking — output
VenueSubmitBookingOut = TypedDict('VenueSubmitBookingOut', {"prepared_id": str, "status": Literal['confirmed', 'sent', 'failed', 'not_allowed', 'calling'], "submitted": bool, "rung": str, "how": str, "venue": str, "act_id": str, "evidence_id": str, "outcome_id": Union[str, None], "reference": Union[str, None], "venue_words": Dict[str, Any], "why": List[Any], "say": str, "route": str, "call_plan": Dict[str, Any], "approval": Dict[str, Any], "takeover": Dict[str, Any], "hand_over": Dict[str, Any], "ask": Dict[str, Any], "instructed": Dict[str, Any], "alternatives": List[Dict[str, Any]]}, total=False)

# venue.unhandled — input
VenueUnhandledIn = TypedDict('VenueUnhandledIn', {"since": str, "limit": int}, total=False)

# venue.unhandled — output
VenueUnhandledOut = TypedDict('VenueUnhandledOut', {"count": int, "items": List[Dict[str, Any]], "table": List[Dict[str, Any]]}, total=False)

# venues.find_venues — input
VenuesFindVenuesIn = TypedDict('VenuesFindVenuesIn', {"what": str, "where": Dict[str, Any], "open_at": str, "party": int}, total=False)

# venues.find_venues — output
VenuesFindVenuesOut = TypedDict('VenuesFindVenuesOut', {"venues": List[Dict[str, Any]], "coverage": Dict[str, Any], "substituted": List[Dict[str, Any]]}, total=False)

# webhooks.register — input
WebhooksRegisterIn = TypedDict('WebhooksRegisterIn', {"url": str, "events": List[Literal['approval.presented', 'approval.given', 'approval.expired', 'approval.void', 'act.confirmed', 'act.awaiting_payment', 'act.refused', 'act.failed', 'act.unknown', 'act.cancelled', 'message.replied']]}, total=False)

# webhooks.register — output
WebhooksRegisterOut = TypedDict('WebhooksRegisterOut', {"endpoint_id": str, "url": str, "secret": str, "created_at": str, "events": List[str]}, total=False)

# webhooks.revoke — input
WebhooksRevokeIn = TypedDict('WebhooksRevokeIn', {"endpoint_id": str}, total=False)

# webhooks.revoke — output
WebhooksRevokeOut = TypedDict('WebhooksRevokeOut', {"endpoint_id": str, "revoked_at": str}, total=False)


REQUIRED: Dict[str, List[str]] = {
 "AccessGetIn": [
  "end_user"
 ],
 "AccessGetOut": [
  "mode",
  "source"
 ],
 "ActivitiesSuggestIn": [
  "city",
  "dates"
 ],
 "ActivitiesSuggestOut": [
  "candidates",
  "city",
  "say"
 ],
 "ActivitiesVerifyIn": [
  "date"
 ],
 "ActivitiesVerifyOut": [
  "confidence",
  "date",
  "say"
 ],
 "ActivityListIn": [
  "end_user"
 ],
 "ActivityListOut": [
  "coverage",
  "items"
 ],
 "ActsStatusIn": [],
 "ActsStatusOut": [
  "acts",
  "coverage"
 ],
 "ApprovalsInAppTapIn": [
  "session"
 ],
 "ApprovalsInAppTapOut": [
  "method",
  "say"
 ],
 "ApprovalsMandateIn": [
  "end_user",
  "proof",
  "scope",
  "words"
 ],
 "ApprovalsMandateOut": [
  "expires_at",
  "mandate_id"
 ],
 "ApprovalsRequestIn": [
  "channel",
  "read_back_id"
 ],
 "ApprovalsRequestOut": [
  "presentation",
  "read_back_id"
 ],
 "ApprovalsStatusIn": [
  "read_back_id"
 ],
 "ApprovalsStatusOut": [
  "approval",
  "presented_at",
  "read_back_id",
  "read_back_state"
 ],
 "CalendarAddEventIn": [
  "act_id"
 ],
 "CalendarAddEventOut": [
  "event",
  "event_sha256",
  "evidence_id",
  "ics",
  "links"
 ],
 "CardsAccidentNotifyIn": [
  "case_id",
  "end_user"
 ],
 "CardsAccidentNotifyOut": [
  "case_id",
  "step",
  "steps"
 ],
 "CardsAccidentPhotoIn": [
  "case_id",
  "content_base64",
  "end_user",
  "shot"
 ],
 "CardsAccidentPhotoOut": [
  "case_id",
  "step",
  "steps"
 ],
 "CardsAccidentStartIn": [
  "country",
  "end_user"
 ],
 "CardsAccidentStartOut": [
  "case_id",
  "step",
  "steps"
 ],
 "CardsAccidentStepIn": [
  "case_id",
  "end_user"
 ],
 "CardsAccidentStepOut": [
  "case_id",
  "step",
  "steps"
 ],
 "CardsAskIn": [
  "end_user",
  "question"
 ],
 "CardsAskOut": [
  "answer",
  "card",
  "framing",
  "quotes",
  "text"
 ],
 "CardsClaimAttachIn": [
  "case_id",
  "content_base64",
  "end_user",
  "kind",
  "media_type"
 ],
 "CardsClaimAttachOut": [
  "card",
  "case_id",
  "clause",
  "deadlines",
  "evidence",
  "kind",
  "route",
  "state"
 ],
 "CardsClaimFileIn": [
  "case_id",
  "end_user"
 ],
 "CardsClaimFileOut": [
  "card",
  "case_id",
  "clause",
  "deadlines",
  "evidence",
  "kind",
  "route",
  "state"
 ],
 "CardsClaimSimulateReplyIn": [
  "case_id",
  "end_user",
  "text"
 ],
 "CardsClaimSimulateReplyOut": [
  "card",
  "case_id",
  "clause",
  "deadlines",
  "evidence",
  "kind",
  "route",
  "state"
 ],
 "CardsClaimStartIn": [
  "card_item_id",
  "end_user",
  "incident_date",
  "kind"
 ],
 "CardsClaimStartOut": [],
 "CardsClaimStatusIn": [
  "case_id",
  "end_user"
 ],
 "CardsClaimStatusOut": [
  "card",
  "case_id",
  "clause",
  "deadlines",
  "evidence",
  "kind",
  "route",
  "state"
 ],
 "CardsIntakeIn": [
  "end_user",
  "image"
 ],
 "CardsIntakeOut": [
  "card",
  "note",
  "saved",
  "terms"
 ],
 "CardsMineIn": [
  "end_user"
 ],
 "CardsMineOut": [
  "cards"
 ],
 "CardsMomentIn": [
  "end_user",
  "event"
 ],
 "CardsMomentOut": [
  "speak"
 ],
 "CardsMomentSettingsIn": [
  "end_user"
 ],
 "CardsMomentSettingsOut": [
  "moments"
 ],
 "CardsProductsIn": [],
 "CardsProductsOut": [
  "note",
  "products"
 ],
 "CardsRentalCoverIn": [
  "country",
  "end_user",
  "rental_company"
 ],
 "CardsRentalCoverOut": [
  "bring",
  "card",
  "cards",
  "company",
  "conditions",
  "counter",
  "country",
  "framing",
  "report",
  "skipped"
 ],
 "CardsRentalDisputeIn": [
  "end_user",
  "moment_id"
 ],
 "CardsRentalDisputeOut": [
  "state"
 ],
 "CardsTermsIn": [
  "product_id"
 ],
 "CardsTermsOut": [
  "benefits",
  "product",
  "sources",
  "unread"
 ],
 "CardsWhichIn": [
  "end_user",
  "purchase"
 ],
 "CardsWhichOut": [
  "cards",
  "framing",
  "net_view",
  "skipped"
 ],
 "DiveOnboardIn": [
  "url"
 ],
 "DiveOnboardOut": [
  "cant_read",
  "reached",
  "stages",
  "url"
 ],
 "EntryCheckIn": [
  "destinations",
  "end_user"
 ],
 "EntryCheckOut": [
  "destinations",
  "say"
 ],
 "EntryPrepareIn": [
  "country",
  "end_user"
 ],
 "EntryPrepareOut": [
  "country",
  "fields",
  "official_url",
  "say"
 ],
 "EvidenceGetIn": [
  "evidence_id"
 ],
 "EvidenceGetOut": [
  "basis",
  "body_sha256",
  "evidence_id",
  "input_digest",
  "operation",
  "produced_at",
  "sources",
  "states_no_conclusion"
 ],
 "EvidenceVerifyIn": [
  "evidence"
 ],
 "EvidenceVerifyOut": [
  "recomputed_body_sha256",
  "valid"
 ],
 "GroupBookIn": [
  "end_user",
  "items",
  "movement_id",
  "worker"
 ],
 "GroupBookOut": [],
 "GroupBookingsIn": [
  "end_user"
 ],
 "GroupBookingsOut": [],
 "GroupCancelIn": [
  "booking_id",
  "end_user"
 ],
 "GroupCancelOut": [],
 "GroupSwapIn": [
  "booking_id",
  "end_user",
  "worker"
 ],
 "GroupSwapOut": [],
 "KeepActivityIn": [
  "end_user"
 ],
 "KeepActivityOut": [
  "items"
 ],
 "KeepDeleteIn": [
  "end_user"
 ],
 "KeepDeleteOut": [
  "deleted",
  "evidence_id",
  "key_destroyed"
 ],
 "KeepListIn": [
  "end_user"
 ],
 "KeepListOut": [
  "items",
  "values_shown"
 ],
 "KeepPutIn": [
  "end_user",
  "type",
  "value"
 ],
 "KeepPutOut": [
  "created",
  "created_at",
  "item_id",
  "masked",
  "tier",
  "type"
 ],
 "KeepUseIn": [
  "end_user",
  "item_id",
  "purpose"
 ],
 "KeepUseOut": [
  "masked",
  "state"
 ],
 "MagellanReadSiteIn": [
  "url"
 ],
 "MagellanReadSiteOut": [
  "booking_channels",
  "contacts",
  "coverage",
  "instruction_like",
  "offers",
  "operator",
  "partners",
  "purpose",
  "reader",
  "url"
 ],
 "MessagesAdCasesIn": [
  "from"
 ],
 "MessagesAdCasesOut": [
  "cases",
  "linked"
 ],
 "MessagesRepliesIn": [
  "end_user"
 ],
 "MessagesRepliesOut": [
  "replies"
 ],
 "MessagesSendEmailIn": [
  "body",
  "end_user",
  "subject",
  "to"
 ],
 "MessagesSendEmailOut": [
  "act_id",
  "evidence_id",
  "intent_id",
  "message",
  "outcome"
 ],
 "MessagesSendWhatsappIn": [
  "end_user",
  "to"
 ],
 "MessagesSendWhatsappOut": [
  "act_id",
  "evidence_id",
  "intent_id",
  "message",
  "outcome"
 ],
 "MessagesTypingIn": [
  "message_id"
 ],
 "MessagesTypingOut": [
  "ok",
  "status"
 ],
 "MessagesWhatsappInboundIn": [
  "from",
  "message_id",
  "text"
 ],
 "MessagesWhatsappInboundOut": [
  "matched"
 ],
 "MessagesWhatsappSwitchIn": [
  "from",
  "message_id",
  "product"
 ],
 "MessagesWhatsappSwitchOut": [
  "dropped",
  "product",
  "since"
 ],
 "MoneyBagCheckIn": [
  "bag",
  "end_user"
 ],
 "MoneyBagCheckOut": [
  "case_id",
  "deadlines",
  "say",
  "verdict"
 ],
 "MoneyBagClaimIn": [
  "case_id",
  "end_user"
 ],
 "MoneyBagClaimOut": [
  "case_id",
  "state"
 ],
 "MoneyClaimSimulateReplyIn": [
  "case_id",
  "end_user",
  "text"
 ],
 "MoneyClaimSimulateReplyOut": [
  "case_id",
  "deadlines",
  "replies",
  "say",
  "state"
 ],
 "MoneyClaimStatusIn": [
  "case_id",
  "end_user"
 ],
 "MoneyClaimStatusOut": [
  "case_id",
  "deadlines",
  "replies",
  "say",
  "state"
 ],
 "MoneyFlightCheckIn": [
  "end_user",
  "flight"
 ],
 "MoneyFlightCheckOut": [
  "case_id",
  "rules",
  "say",
  "verdict"
 ],
 "MoneyFlightClaimIn": [
  "case_id",
  "end_user"
 ],
 "MoneyFlightClaimOut": [
  "case_id",
  "state"
 ],
 "OutcomesListIn": [],
 "OutcomesListOut": [
  "outcomes"
 ],
 "OutcomesMarkTestIn": [],
 "OutcomesMarkTestOut": [
  "marked",
  "say",
  "test"
 ],
 "OutcomesRecordIn": [
  "channel",
  "rung",
  "venue"
 ],
 "OutcomesRecordOut": [
  "asked_at",
  "channel",
  "outcome_id",
  "rung",
  "state",
  "venue"
 ],
 "OutcomesReportIn": [],
 "OutcomesReportOut": [
  "overall",
  "say"
 ],
 "OutcomesUpdateIn": [
  "state"
 ],
 "OutcomesUpdateOut": [
  "asked_at",
  "channel",
  "outcome_id",
  "rung",
  "state",
  "venue"
 ],
 "RegistryChangeListIn": [],
 "RegistryChangeListOut": [],
 "RegistryCountriesIn": [],
 "RegistryCountriesOut": [
  "jurisdictions",
  "note"
 ],
 "RegistryDocumentsIn": [
  "jurisdiction"
 ],
 "RegistryDocumentsOut": [
  "documents",
  "jurisdiction"
 ],
 "RegistryGetIn": [
  "jurisdiction"
 ],
 "RegistryGetOut": [
  "jurisdiction",
  "registers",
  "sources"
 ],
 "RegistryObtainPlanIn": [
  "jurisdiction"
 ],
 "RegistryObtainPlanOut": [
  "actor",
  "excluded",
  "jurisdiction",
  "obtain",
  "obtainable_by_agapi",
  "routes"
 ],
 "RegistryRowResultsIn": [],
 "RegistryRowResultsOut": [],
 "RegistryVerifyIn": [],
 "RegistryVerifyOut": [
  "checked",
  "quote_still_present",
  "read_at",
  "state"
 ],
 "RegistryWaveResumeIn": [
  "job_id"
 ],
 "RegistryWaveResumeOut": [],
 "RegistryWaveRunIn": [
  "jurisdictions"
 ],
 "RegistryWaveRunOut": [],
 "RegistryWaveStatusIn": [
  "job_id"
 ],
 "RegistryWaveStatusOut": [],
 "SandboxAdCaseIn": [],
 "SandboxAdCaseOut": [
  "case_id",
  "client_supplied_sources",
  "timeline"
 ],
 "SandboxAdOpenCaseIn": [
  "email",
  "name"
 ],
 "SandboxAdOpenCaseOut": [
  "case_id",
  "name",
  "opened_at",
  "opened_on"
 ],
 "SandboxLinkProofIn": [
  "url"
 ],
 "SandboxLinkProofOut": [
  "proven",
  "url"
 ],
 "SandboxMessagesIn": [],
 "SandboxMessagesOut": [
  "messages"
 ],
 "SandboxPlatformPrepareIn": [
  "date",
  "end_user",
  "party",
  "time"
 ],
 "SandboxPlatformPrepareOut": [
  "prepared_id"
 ],
 "SandboxPlatformWalkIn": [
  "date",
  "end_user",
  "party",
  "time",
  "url"
 ],
 "SandboxPlatformWalkOut": [
  "decision",
  "say"
 ],
 "SandboxSimulateApprovalIn": [
  "read_back_id",
  "said"
 ],
 "SandboxSimulateApprovalOut": [
  "approval_id",
  "state"
 ],
 "SandboxSimulateCallIn": [
  "number",
  "says"
 ],
 "SandboxSimulateCallOut": [
  "call_sid",
  "posted",
  "said",
  "state"
 ],
 "SandboxSimulateReplyIn": [
  "number",
  "text"
 ],
 "SandboxSimulateReplyOut": [
  "opted_out",
  "received_at",
  "reply_id",
  "window_open_until"
 ],
 "SandboxWaTemplateIn": [
  "lang",
  "name",
  "status"
 ],
 "SandboxWaTemplateOut": [
  "approved",
  "lang",
  "name",
  "status"
 ],
 "SourcesGetIn": [],
 "SourcesGetOut": [
  "copy_id",
  "expires_at",
  "read_at",
  "reader_kind",
  "sha256",
  "source_url",
  "url"
 ],
 "SubscriptionsCancelIn": [
  "end_user",
  "route",
  "subscription_id"
 ],
 "SubscriptionsCancelOut": [
  "act_id",
  "evidence_id",
  "intent_id",
  "outcome",
  "subscription"
 ],
 "SubscriptionsCancelPlanIn": [
  "end_user",
  "subscription_id"
 ],
 "SubscriptionsCancelPlanOut": [
  "merchant",
  "never",
  "routes",
  "subscription_id"
 ],
 "SubscriptionsFindIn": [
  "end_user"
 ],
 "SubscriptionsFindOut": [
  "likely_unused",
  "monthly_total",
  "note",
  "subscriptions"
 ],
 "TravelFindFlightsIn": [
  "date",
  "destination",
  "origin",
  "passengers"
 ],
 "TravelFindFlightsOut": [
  "coverage",
  "offers"
 ],
 "TravelFindStaysIn": [
  "check_in",
  "city",
  "nights",
  "party"
 ],
 "TravelFindStaysOut": [
  "coverage",
  "stays"
 ],
 "TripCancelIn": [
  "act_id"
 ],
 "TripCancelOut": [
  "act_id",
  "evidence_id",
  "outcome"
 ],
 "TripCompleteIn": [
  "hold_id"
 ],
 "TripCompleteOut": [
  "act_id",
  "evidence_id",
  "intent_id",
  "outcome"
 ],
 "TripHoldIn": [
  "end_user",
  "items"
 ],
 "TripHoldOut": [
  "expires_at",
  "hold_id",
  "intent_id",
  "items",
  "read_back",
  "total"
 ],
 "TripPlanIn": [
  "person"
 ],
 "TripPlanOut": [
  "status",
  "trip_id"
 ],
 "TripPlanGetIn": [
  "trip_id"
 ],
 "TripPlanGetOut": [
  "status",
  "trip_id"
 ],
 "UsageGetIn": [
  "from",
  "to"
 ],
 "UsageGetOut": [
  "account",
  "budget_remaining",
  "by_operation",
  "from",
  "to",
  "total_cost_units"
 ],
 "UsersConfirmWhatsappIn": [
  "message_id",
  "nonce",
  "signature",
  "t",
  "text",
  "wa_id"
 ],
 "UsersConfirmWhatsappOut": [
  "say",
  "state"
 ],
 "UsersLinkWhatsappIn": [
  "end_user",
  "number"
 ],
 "UsersLinkWhatsappOut": [
  "number",
  "say",
  "state"
 ],
 "UsersRegisterIn": [
  "external_ref"
 ],
 "UsersRegisterOut": [
  "account",
  "created_at",
  "destinations",
  "end_user_id",
  "external_ref"
 ],
 "UsersVerifyDestinationIn": [
  "channel",
  "code",
  "end_user_id",
  "value"
 ],
 "UsersVerifyDestinationOut": [
  "account",
  "created_at",
  "destinations",
  "end_user_id",
  "external_ref"
 ],
 "VenueBookingStatusIn": [
  "act_id"
 ],
 "VenueBookingStatusOut": [
  "act_id",
  "say",
  "state"
 ],
 "VenueBookingsIn": [
  "end_user"
 ],
 "VenueBookingsOut": [
  "bookings"
 ],
 "VenueCallAgainIn": [
  "act_id",
  "reason"
 ],
 "VenueCallAgainOut": [
  "act_id",
  "say",
  "status"
 ],
 "VenueCallAttemptIn": [
  "act_id",
  "outcome"
 ],
 "VenueCallAttemptOut": [
  "act_id",
  "say",
  "status"
 ],
 "VenueCancelBookingIn": [
  "act_id",
  "end_user"
 ],
 "VenueCancelBookingOut": [
  "act_id",
  "say",
  "status"
 ],
 "VenueChangeBookingIn": [
  "act_id",
  "end_user",
  "kind"
 ],
 "VenueChangeBookingOut": [
  "act_id",
  "say",
  "status"
 ],
 "VenueConfirmationIn": [
  "emails",
  "end_user"
 ],
 "VenueConfirmationOut": [
  "emails",
  "matched",
  "say_text"
 ],
 "VenueDiscoverIn": [
  "what",
  "where"
 ],
 "VenueDiscoverOut": [
  "category",
  "coverage",
  "groups",
  "options",
  "pick",
  "policy_version",
  "ranking_version",
  "say_text",
  "what",
  "where"
 ],
 "VenueHandedOverIn": [
  "end_user",
  "how",
  "prepared_id"
 ],
 "VenueHandedOverOut": [
  "act_id",
  "state"
 ],
 "VenueManageOptionsIn": [
  "act_id",
  "end_user"
 ],
 "VenueManageOptionsOut": [
  "act_id",
  "known",
  "options",
  "say_text"
 ],
 "VenuePersonReportIn": [
  "report"
 ],
 "VenuePersonReportOut": [
  "act_id",
  "state"
 ],
 "VenuePrepareBookingIn": [
  "party",
  "person"
 ],
 "VenuePrepareBookingOut": [
  "submitted",
  "venue_id"
 ],
 "VenueProfileIn": [],
 "VenueProfileOut": [
  "site",
  "url",
  "venue_id"
 ],
 "VenueRecognitionIn": [
  "place"
 ],
 "VenueRecognitionOut": [
  "recognition"
 ],
 "VenueSubmitBookingIn": [
  "end_user",
  "prepared_id"
 ],
 "VenueSubmitBookingOut": [
  "prepared_id",
  "say",
  "status",
  "submitted"
 ],
 "VenueUnhandledIn": [],
 "VenueUnhandledOut": [
  "count",
  "items",
  "table"
 ],
 "VenuesFindVenuesIn": [
  "what",
  "where"
 ],
 "VenuesFindVenuesOut": [
  "coverage",
  "venues"
 ],
 "WebhooksRegisterIn": [
  "url"
 ],
 "WebhooksRegisterOut": [
  "created_at",
  "endpoint_id",
  "secret",
  "url"
 ],
 "WebhooksRevokeIn": [
  "endpoint_id"
 ],
 "WebhooksRevokeOut": [
  "endpoint_id",
  "revoked_at"
 ]
}

OPERATION_TYPES = {"access.get": (AccessGetIn, AccessGetOut), "activities.suggest": (ActivitiesSuggestIn, ActivitiesSuggestOut), "activities.verify": (ActivitiesVerifyIn, ActivitiesVerifyOut), "activity.list": (ActivityListIn, ActivityListOut), "acts.status": (ActsStatusIn, ActsStatusOut), "approvals.in_app_tap": (ApprovalsInAppTapIn, ApprovalsInAppTapOut), "approvals.mandate": (ApprovalsMandateIn, ApprovalsMandateOut), "approvals.request": (ApprovalsRequestIn, ApprovalsRequestOut), "approvals.status": (ApprovalsStatusIn, ApprovalsStatusOut), "calendar.add_event": (CalendarAddEventIn, CalendarAddEventOut), "cards.accident_notify": (CardsAccidentNotifyIn, CardsAccidentNotifyOut), "cards.accident_photo": (CardsAccidentPhotoIn, CardsAccidentPhotoOut), "cards.accident_start": (CardsAccidentStartIn, CardsAccidentStartOut), "cards.accident_step": (CardsAccidentStepIn, CardsAccidentStepOut), "cards.ask": (CardsAskIn, CardsAskOut), "cards.claim_attach": (CardsClaimAttachIn, CardsClaimAttachOut), "cards.claim_file": (CardsClaimFileIn, CardsClaimFileOut), "cards.claim_simulate_reply": (CardsClaimSimulateReplyIn, CardsClaimSimulateReplyOut), "cards.claim_start": (CardsClaimStartIn, CardsClaimStartOut), "cards.claim_status": (CardsClaimStatusIn, CardsClaimStatusOut), "cards.intake": (CardsIntakeIn, CardsIntakeOut), "cards.mine": (CardsMineIn, CardsMineOut), "cards.moment": (CardsMomentIn, CardsMomentOut), "cards.moment_settings": (CardsMomentSettingsIn, CardsMomentSettingsOut), "cards.products": (CardsProductsIn, CardsProductsOut), "cards.rental_cover": (CardsRentalCoverIn, CardsRentalCoverOut), "cards.rental_dispute": (CardsRentalDisputeIn, CardsRentalDisputeOut), "cards.terms": (CardsTermsIn, CardsTermsOut), "cards.which": (CardsWhichIn, CardsWhichOut), "dive.onboard": (DiveOnboardIn, DiveOnboardOut), "entry.check": (EntryCheckIn, EntryCheckOut), "entry.prepare": (EntryPrepareIn, EntryPrepareOut), "evidence.get": (EvidenceGetIn, EvidenceGetOut), "evidence.verify": (EvidenceVerifyIn, EvidenceVerifyOut), "group.book": (GroupBookIn, GroupBookOut), "group.bookings": (GroupBookingsIn, GroupBookingsOut), "group.cancel": (GroupCancelIn, GroupCancelOut), "group.swap": (GroupSwapIn, GroupSwapOut), "keep.activity": (KeepActivityIn, KeepActivityOut), "keep.delete": (KeepDeleteIn, KeepDeleteOut), "keep.list": (KeepListIn, KeepListOut), "keep.put": (KeepPutIn, KeepPutOut), "keep.use": (KeepUseIn, KeepUseOut), "magellan.read_site": (MagellanReadSiteIn, MagellanReadSiteOut), "messages.ad_cases": (MessagesAdCasesIn, MessagesAdCasesOut), "messages.replies": (MessagesRepliesIn, MessagesRepliesOut), "messages.send_email": (MessagesSendEmailIn, MessagesSendEmailOut), "messages.send_whatsapp": (MessagesSendWhatsappIn, MessagesSendWhatsappOut), "messages.typing": (MessagesTypingIn, MessagesTypingOut), "messages.whatsapp_inbound": (MessagesWhatsappInboundIn, MessagesWhatsappInboundOut), "messages.whatsapp_switch": (MessagesWhatsappSwitchIn, MessagesWhatsappSwitchOut), "money.bag_check": (MoneyBagCheckIn, MoneyBagCheckOut), "money.bag_claim": (MoneyBagClaimIn, MoneyBagClaimOut), "money.claim_simulate_reply": (MoneyClaimSimulateReplyIn, MoneyClaimSimulateReplyOut), "money.claim_status": (MoneyClaimStatusIn, MoneyClaimStatusOut), "money.flight_check": (MoneyFlightCheckIn, MoneyFlightCheckOut), "money.flight_claim": (MoneyFlightClaimIn, MoneyFlightClaimOut), "outcomes.list": (OutcomesListIn, OutcomesListOut), "outcomes.mark_test": (OutcomesMarkTestIn, OutcomesMarkTestOut), "outcomes.record": (OutcomesRecordIn, OutcomesRecordOut), "outcomes.report": (OutcomesReportIn, OutcomesReportOut), "outcomes.update": (OutcomesUpdateIn, OutcomesUpdateOut), "registry.change_list": (RegistryChangeListIn, RegistryChangeListOut), "registry.countries": (RegistryCountriesIn, RegistryCountriesOut), "registry.documents": (RegistryDocumentsIn, RegistryDocumentsOut), "registry.get": (RegistryGetIn, RegistryGetOut), "registry.obtain_plan": (RegistryObtainPlanIn, RegistryObtainPlanOut), "registry.row_results": (RegistryRowResultsIn, RegistryRowResultsOut), "registry.verify": (RegistryVerifyIn, RegistryVerifyOut), "registry.wave_resume": (RegistryWaveResumeIn, RegistryWaveResumeOut), "registry.wave_run": (RegistryWaveRunIn, RegistryWaveRunOut), "registry.wave_status": (RegistryWaveStatusIn, RegistryWaveStatusOut), "sandbox.ad_case": (SandboxAdCaseIn, SandboxAdCaseOut), "sandbox.ad_open_case": (SandboxAdOpenCaseIn, SandboxAdOpenCaseOut), "sandbox.link_proof": (SandboxLinkProofIn, SandboxLinkProofOut), "sandbox.messages": (SandboxMessagesIn, SandboxMessagesOut), "sandbox.platform_prepare": (SandboxPlatformPrepareIn, SandboxPlatformPrepareOut), "sandbox.platform_walk": (SandboxPlatformWalkIn, SandboxPlatformWalkOut), "sandbox.simulate_approval": (SandboxSimulateApprovalIn, SandboxSimulateApprovalOut), "sandbox.simulate_call": (SandboxSimulateCallIn, SandboxSimulateCallOut), "sandbox.simulate_reply": (SandboxSimulateReplyIn, SandboxSimulateReplyOut), "sandbox.wa_template": (SandboxWaTemplateIn, SandboxWaTemplateOut), "sources.get": (SourcesGetIn, SourcesGetOut), "subscriptions.cancel": (SubscriptionsCancelIn, SubscriptionsCancelOut), "subscriptions.cancel_plan": (SubscriptionsCancelPlanIn, SubscriptionsCancelPlanOut), "subscriptions.find": (SubscriptionsFindIn, SubscriptionsFindOut), "travel.find_flights": (TravelFindFlightsIn, TravelFindFlightsOut), "travel.find_stays": (TravelFindStaysIn, TravelFindStaysOut), "trip.cancel": (TripCancelIn, TripCancelOut), "trip.complete": (TripCompleteIn, TripCompleteOut), "trip.hold": (TripHoldIn, TripHoldOut), "trip.plan": (TripPlanIn, TripPlanOut), "trip.plan_get": (TripPlanGetIn, TripPlanGetOut), "usage.get": (UsageGetIn, UsageGetOut), "users.confirm_whatsapp": (UsersConfirmWhatsappIn, UsersConfirmWhatsappOut), "users.link_whatsapp": (UsersLinkWhatsappIn, UsersLinkWhatsappOut), "users.register": (UsersRegisterIn, UsersRegisterOut), "users.verify_destination": (UsersVerifyDestinationIn, UsersVerifyDestinationOut), "venue.booking_status": (VenueBookingStatusIn, VenueBookingStatusOut), "venue.bookings": (VenueBookingsIn, VenueBookingsOut), "venue.call_again": (VenueCallAgainIn, VenueCallAgainOut), "venue.call_attempt": (VenueCallAttemptIn, VenueCallAttemptOut), "venue.cancel_booking": (VenueCancelBookingIn, VenueCancelBookingOut), "venue.change_booking": (VenueChangeBookingIn, VenueChangeBookingOut), "venue.confirmation": (VenueConfirmationIn, VenueConfirmationOut), "venue.discover": (VenueDiscoverIn, VenueDiscoverOut), "venue.handed_over": (VenueHandedOverIn, VenueHandedOverOut), "venue.manage_options": (VenueManageOptionsIn, VenueManageOptionsOut), "venue.person_report": (VenuePersonReportIn, VenuePersonReportOut), "venue.prepare_booking": (VenuePrepareBookingIn, VenuePrepareBookingOut), "venue.profile": (VenueProfileIn, VenueProfileOut), "venue.recognition": (VenueRecognitionIn, VenueRecognitionOut), "venue.submit_booking": (VenueSubmitBookingIn, VenueSubmitBookingOut), "venue.unhandled": (VenueUnhandledIn, VenueUnhandledOut), "venues.find_venues": (VenuesFindVenuesIn, VenuesFindVenuesOut), "webhooks.register": (WebhooksRegisterIn, WebhooksRegisterOut), "webhooks.revoke": (WebhooksRevokeIn, WebhooksRevokeOut)}
