from django.db.models import Case, F, Value, When

from leads.models import LeadSummary
from sequences.utils import get_next_sequence

LEAD_SUMMARY_KEY = "GLOBAL"


def generate_lead_unique_id() -> str:
    name = "LEADS"
    prefix = "L"
    sequence = get_next_sequence(name)
    return f"{prefix}-{sequence}"


def get_lead_summary() -> LeadSummary:
    lead_summary, _ = LeadSummary.objects.get_or_create(key=LEAD_SUMMARY_KEY)
    return lead_summary


def increment_leads_total() -> None:
    lead_summary = get_lead_summary()
    LeadSummary.objects.filter(pk=lead_summary.pk).update(
        leads_total=F("leads_total") + 1
    )


def decrement_leads_total() -> None:
    lead_summary = get_lead_summary()
    LeadSummary.objects.filter(pk=lead_summary.pk).update(
        leads_total=Case(
            When(leads_total__gt=0, then=F("leads_total") - 1),
            default=Value(0),
        )
    )


def increment_leads_converted() -> None:
    lead_summary = get_lead_summary()
    LeadSummary.objects.filter(pk=lead_summary.pk).update(
        leads_converted=F("leads_converted") + 1
    )


def decrement_leads_converted() -> None:
    lead_summary = get_lead_summary()
    LeadSummary.objects.filter(pk=lead_summary.pk).update(
        leads_converted=Case(
            When(leads_converted__gt=0, then=F("leads_converted") - 1),
            default=Value(0),
        )
    )


def increment_leads_assigned() -> None:
    lead_summary = get_lead_summary()
    LeadSummary.objects.filter(pk=lead_summary.pk).update(
        leads_assigned=F("leads_assigned") + 1
    )


def decrement_leads_assigned() -> None:
    lead_summary = get_lead_summary()
    LeadSummary.objects.filter(pk=lead_summary.pk).update(
        leads_assigned=Case(
            When(leads_assigned__gt=0, then=F("leads_assigned") - 1),
            default=Value(0),
        )
    )


def increment_leads_inactive() -> None:
    lead_summary = get_lead_summary()
    LeadSummary.objects.filter(pk=lead_summary.pk).update(
        leads_inactive=F("leads_inactive") + 1
    )


def decrement_leads_inactive() -> None:
    lead_summary = get_lead_summary()
    LeadSummary.objects.filter(pk=lead_summary.pk).update(
        leads_inactive=Case(
            When(leads_inactive__gt=0, then=F("leads_inactive") - 1),
            default=Value(0),
        )
    )


def share_onboarding_form() -> None:
    pass
