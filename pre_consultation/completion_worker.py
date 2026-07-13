"""Post-completion generation: summarization + medical report insight extraction.

When a pre-consultation session is completed, both generation steps run —
sequentially — on a single fire-and-forget daemon thread so the HTTP response is
not blocked on minutes of LLM work.

Each step is guarded independently: a failure in summarization never prevents
report extraction from running, and the daemon thread never dies with an
unlogged traceback. `connections.close_all()` runs at the end because the thread
lives outside Django's request-scoped connection lifecycle.
"""

import logging
import threading
from datetime import date

from django.db import connections
from django.utils import timezone

from accounts.users.utils.helper import calculate_age
from intelligence_engine.preconsultation import extract_insights_batch, summarize_patient
from pre_consultation.models import (
    PreConsultationMedicalReport,
    PreConsultationMedicalReportSummary,
    PreConsultationPreparationChecklistItem,
    PreConsultationSession,
    PreConsultationSessionArtifacts,
)
from pre_consultation.result_session import (
    ResultSessionContext,
    get_result_session_context,
)
from pre_consultation.utils.constants import PreConsultationArtifactGenerationStatus
from pre_consultation.utils.directive import (
    get_concern_cluster_ids_map,
    get_directive_age_band_label_map,
    get_directive_category_label_map,
    get_directive_cluster_probes_for_cluster,
    get_directive_concern_label_map,
    get_directive_concern_sources,
    get_directive_diagnosis_label_map,
    get_directive_family_relation_label_map,
    get_directive_health_goals,
    get_directive_impact_label_map,
    get_directive_lifestyle_fields,
    get_directive_lifestyle_signal_label_map,
    get_directive_sexual_health_questions_for_gender,
    get_directive_symptom_label_map,
)

logger = logging.getLogger(__name__)

def spawn_post_completion_generation(session_id: str, user_id: str) -> None:
    """Spawn a daemon thread that runs both post-completion generation steps."""
    logger.info(
        f"Spawning post-completion generation thread for session {session_id}",
        extra={"session_id": session_id},
    )
    threading.Thread(
        target=_run_post_completion_generation,
        args=(session_id, user_id),
        daemon=True,
    ).start()


def _run_post_completion_generation(session_id: str, user_id: str) -> None:
    logger.info(
        f"Post-completion generation thread started for session {session_id}",
        extra={"session_id": session_id},
    )
    try:
        try:
            run_summarization(session_id, user_id)
        except Exception:
            logger.exception(
                f"Summarization failed for session {session_id}",
                extra={"session_id": session_id},
            )

        try:
            run_report_insights_extraction(session_id, user_id)
        except Exception:
            logger.exception(
                f"Report insight extraction failed for session {session_id}",
                extra={"session_id": session_id},
            )

        logger.info(
            f"Post-completion generation thread finished for session {session_id}",
            extra={"session_id": session_id},
        )
    finally:
        connections.close_all()

def run_summarization(session_id: str, user_id: str) -> None:
    logger.info(
        f"Starting summarization for session {session_id}",
        extra={"session_id": session_id},
    )
    try:
        session = PreConsultationSession.objects.get(pk=session_id, user_id=user_id)

        artifacts, _ = PreConsultationSessionArtifacts.objects.get_or_create(
            session=session
        )
        artifacts.generation_status = (
            PreConsultationArtifactGenerationStatus.IN_PROGRESS
        )
        artifacts.generation_started_at = timezone.now()
        artifacts.save(
            update_fields=[
                "generation_status",
                "generation_started_at",
                "updated_at",
            ]
        )

        context = get_result_session_context(user_id)
        client_details = build_summarize_client_details(context)

        result = summarize_patient(client_details, trigger_webhook=True)

        _persist_summarization_result(session, artifacts, result)

        logger.info(
            f"Summarization completed for session {session_id}",
            extra={"session_id": session_id},
        )

    except Exception as e:
        logger.exception(
            f"Summarization failed for session {session_id}: {str(e)}",
            extra={"session_id": session_id},
        )
        try:
            session = PreConsultationSession.objects.get(pk=session_id)
            artifacts = PreConsultationSessionArtifacts.objects.get(session=session)
            artifacts.generation_status = (
                PreConsultationArtifactGenerationStatus.FAILED
            )
            artifacts.generation_completed_at = timezone.now()
            artifacts.save(
                update_fields=[
                    "generation_status",
                    "generation_completed_at",
                    "updated_at",
                ]
            )
        except Exception as persist_error:
            logger.exception(
                f"Failed to mark artifacts as FAILED: {str(persist_error)}"
            )


def _persist_summarization_result(
    session: PreConsultationSession,
    artifacts: PreConsultationSessionArtifacts,
    result: dict,
) -> None:
    summary = result.get("preconsultation_summary", "")
    family_risk_summary = result.get("family_risk_summary", "")
    checklist_items = result.get("preconsultation_checklist", [])

    artifacts.summary = summary
    artifacts.quick_summary = summary
    artifacts.family_risk_summary = family_risk_summary
    artifacts.generation_status = PreConsultationArtifactGenerationStatus.COMPLETED
    artifacts.generation_completed_at = timezone.now()
    artifacts.save(
        update_fields=[
            "summary",
            "quick_summary",
            "family_risk_summary",
            "generation_status",
            "generation_completed_at",
            "updated_at",
        ]
    )

    PreConsultationPreparationChecklistItem.objects.filter(session=session).delete()

    checklist_rows = [
        PreConsultationPreparationChecklistItem(
            session=session,
            identified_concern=item.get("probe", ""),
            marked=False,
        )
        for item in checklist_items
    ]

    PreConsultationPreparationChecklistItem.objects.bulk_create(checklist_rows)

    logger.info(
        f"Persisted summarization result for session {session.pk}: "
        f"summary={len(summary)} chars, checklist={len(checklist_rows)} item(s)",
        extra={"session_id": str(session.pk)},
    )

def build_summarize_client_details(context: ResultSessionContext) -> dict:
    """Transform ResultSessionContext into LLM-required client_details shape.

    All ID-to-label lookups use .get(id, id) fallback so missing directive entries
    never abort payload construction.
    """
    return {
        "patient_baseline": _patient_baseline_payload(context),
        "category_selections": _category_selections_payload(context),
        "concerns": _concerns_payload(context),
        "medical_history": _medical_history_payload(context),
        "cluster_scores": _cluster_scores_payload(context),
        "health_goals": _health_goals_payload(context),
        "lifestyle_answers": _lifestyle_answers_payload(context),
    }


def _patient_baseline_payload(context: ResultSessionContext) -> dict:
    if context.customer_profile is None:
        return {
            "id": str(context.session.pk),
            "first_name": "",
            "last_name": "",
            "contact_email": "",
            "date_of_birth": "",
            "gender": "",
        }

    profile = context.customer_profile
    dob_iso = profile.date_of_birth.isoformat() if profile.date_of_birth else ""
    contact_email = profile.customer.contact_email or ""

    return {
        "id": str(context.session.pk),
        "first_name": profile.first_name or "",
        "last_name": profile.last_name or "",
        "contact_email": contact_email,
        "date_of_birth": dob_iso,
        "gender": profile.gender or "",
    }


def _category_selections_payload(context: ResultSessionContext) -> list[dict]:
    category_label_map = get_directive_category_label_map()
    return [
        {
            "category_label": category_label_map.get(
                cat_sel.category_id,
                cat_sel.category_id,
            )
        }
        for cat_sel in context.session.category_selections.all()
    ]


def _concerns_payload(context: ResultSessionContext) -> list[dict]:
    concern_label_map = get_directive_concern_label_map()
    functional_impact_map = get_directive_impact_label_map("functional_impact")
    duration_impact_map = get_directive_impact_label_map("duration_impact")
    progression_impact_map = get_directive_impact_label_map("progression_impact")
    symptom_label_map = get_directive_symptom_label_map()
    concern_source_label_map = _build_concern_source_label_map()
    family_relation_label_map = get_directive_family_relation_label_map()
    age_band_label_map = get_directive_age_band_label_map()

    concern_cluster_ids_map = get_concern_cluster_ids_map()
    probe_label_map_by_cluster = {}
    for cluster_id in set(
        cid for cids in concern_cluster_ids_map.values() for cid in cids
    ):
        probe_label_map_by_cluster[cluster_id] = {
            probe["id"]: probe["label"]
            for probe in get_directive_cluster_probes_for_cluster(cluster_id)
        }

    concerns = []
    for concern in context.session.concerns.all():
        symptoms = [
            {"symptom_label": symptom_label_map.get(s.symptom_id, s.symptom_id)}
            for s in concern.symptoms.all()
        ]

        sources = [
            {
                "source_label": concern_source_label_map.get(
                    s.source_id,
                    s.source_id,
                )
            }
            for s in concern.sources.all()
        ]

        family_history = [
            {
                "relation_label": family_relation_label_map.get(
                    fh.relation_id,
                    fh.relation_id,
                ),
                "age_band_label": age_band_label_map.get(
                    fh.age_band_id,
                    fh.age_band_id,
                ),
            }
            for fh in concern.family_history.all()
        ]

        cluster_probe_answers = []
        for cluster_id in concern_cluster_ids_map.get(concern.concern_id, []):
            probe_map = probe_label_map_by_cluster.get(cluster_id, {})
            for probe_answer in concern.probe_answers.all():
                probe_label = probe_map.get(
                    probe_answer.probe_id, probe_answer.probe_id
                )
                cluster_probe_answers.append(
                    {
                        "probe_label": probe_label,
                        "value": "yes" if probe_answer.value == 1 else "no",
                    }
                )

        concerns.append(
            {
                "concern_label": concern_label_map.get(
                    concern.concern_id,
                    concern.concern_id,
                ),
                "functional_impact_id": concern.functional_impact_id,
                "functional_impact_label": functional_impact_map.get(
                    concern.functional_impact_id,
                    concern.functional_impact_id,
                ),
                "duration_impact_label": duration_impact_map.get(
                    concern.duration_impact_id,
                    concern.duration_impact_id,
                ),
                "progression_impact_id": concern.progression_impact_id,
                "progression_impact_label": progression_impact_map.get(
                    concern.progression_impact_id,
                    concern.progression_impact_id,
                ),
                "confidence_score": concern.confidence_score,
                "probe_flagged": concern.probe_flagged,
                "probe_question_count": concern.probe_question_count,
                "symptoms": symptoms,
                "concern_sources": sources,
                "family_history": family_history,
                "cluster_probe_answers": cluster_probe_answers,
            }
        )

    return concerns


def _medical_history_payload(context: ResultSessionContext) -> dict:
    if context.medical_history is None:
        return {}

    diagnosis_label_map = get_directive_diagnosis_label_map()

    diagnoses = [
        {
            "diagnosis_label": diagnosis_label_map.get(
                diag.diagnosis_id,
                diag.diagnosis_id,
            )
        }
        for diag in context.medical_history.diagnoses.all()
    ]

    medications = [
        {
            "name": med.name,
            "dosage": med.dosage,
            "frequency": med.frequency,
            "duration": med.duration,
        }
        for med in context.medical_history.medications.all()
    ]

    allergies = [
        {"name": allergy.name} for allergy in context.medical_history.allergies.all()
    ]

    surgeries = [
        {
            "name": surgery.name,
            "performed_when": surgery.performed_when,
            "reason": surgery.reason,
        }
        for surgery in context.medical_history.surgeries.all()
    ]

    sexual_health_answers = _sexual_health_answers_payload(context)

    result = {
        "diagnoses": diagnoses,
        "medications": medications,
        "allergies": allergies,
        "surgeries": surgeries,
    }

    if sexual_health_answers:
        result["sexual_health_answers"] = sexual_health_answers

    return result


def _sexual_health_answers_payload(context: ResultSessionContext) -> list[dict]:
    if context.medical_history is None or context.customer_profile is None:
        return []

    profile = context.customer_profile
    gender = profile.gender
    if not gender:
        return []

    age_years = None
    if profile.date_of_birth:
        age_years = calculate_age(profile.date_of_birth)

    try:
        questions = get_directive_sexual_health_questions_for_gender(
            gender, age_years
        )
    except Exception:
        return []

    question_label_map = {q["id"]: q["label"] for q in questions}
    option_label_map = {}
    for q in questions:
        option_label_map[q["id"]] = {
            opt["id"]: opt["label"] for opt in q.get("options", [])
        }

    answers = []
    for sha in context.medical_history.sexual_health_answers.all():
        question_label = question_label_map.get(sha.question_id, sha.question_id)
        option_labels = option_label_map.get(sha.question_id, {})
        option_label = option_labels.get(sha.option_id, sha.option_id)

        answers.append(
            {
                "question_label": question_label,
                "option_id": sha.option_id,
                "option_label": option_label,
            }
        )

    return answers


def _cluster_scores_payload(context: ResultSessionContext) -> list[dict]:
    lifestyle_signal_label_map = get_directive_lifestyle_signal_label_map()

    return [
        {
            "cluster_label": score.cluster_label,
            "final_score": score.final_score,
            "bucket_id": score.bucket_id,
            "bucket_label": score.bucket_label,
            "lifestyle_signals_triggered": [
                {
                    "signal_label": lifestyle_signal_label_map.get(
                        signal_id,
                        signal_id,
                    )
                }
                for signal_id in score.lifestyle_signals_triggered
            ],
            "family_risk_contribution": score.family_risk_contribution,
            "validation_skip_reason": score.validation_skip_reason,
        }
        for score in context.session.cluster_scores.all()
    ]


def _health_goals_payload(context: ResultSessionContext) -> list[dict]:
    health_goal_label_map = _build_health_goal_label_map()

    return [
        {
            "goal_label": health_goal_label_map.get(goal.goal_id, goal.goal_id),
            "priority": goal.priority,
        }
        for goal in context.session.health_goals.order_by("priority")
    ]


def _lifestyle_answers_payload(context: ResultSessionContext) -> list[dict]:
    lifestyle_fields = get_directive_lifestyle_fields()

    field_label_map = {lf["id"]: lf["label"] for lf in lifestyle_fields}
    option_label_map = {}
    for lf in lifestyle_fields:
        option_label_map[lf["id"]] = {
            opt["value"]: opt["label"] for opt in lf["options"]
        }

    return [
        {
            "field_label": field_label_map.get(answer.field_id, answer.field_id),
            "option_value": answer.option_value,
            "option_label": option_label_map.get(answer.field_id, {}).get(
                answer.option_value,
                answer.option_value,
            ),
        }
        for answer in context.session.lifestyle_answers.all()
    ]


def _build_concern_source_label_map() -> dict[str, str]:
    return {cs["id"]: cs["label"] for cs in get_directive_concern_sources()}


def _build_health_goal_label_map() -> dict[str, str]:
    return {hg["id"]: hg["label"] for hg in get_directive_health_goals()}

def run_report_insights_extraction(session_id: str, user_id: str) -> None:
    """Fetch uploaded reports, call extraction LLM, persist results."""
    logger.info(
        f"Starting report insight extraction for session {session_id}",
        extra={"session_id": session_id},
    )
    reports: list[dict] = []
    try:
        context = get_result_session_context(user_id)
        reports = build_extract_insights_reports(context)

        if not reports:
            logger.info(
                f"No medical reports to extract for session {session_id}",
                extra={"session_id": session_id},
            )
            return

        logger.info(
            f"Fetched {len(reports)} report(s) for session {session_id}, "
            "calling extraction LLM",
            extra={"session_id": session_id, "report_count": len(reports)},
        )
        result = extract_insights_batch(reports)

        _persist_extraction_results(result)

        logger.info(
            f"Report insight extraction completed for session {session_id}: "
            f"{len(result.get('results', []))} processed, "
            f"{len(result.get('skipped', []))} skipped",
            extra={"session_id": session_id, "result": result},
        )

    except Exception as e:
        logger.exception(
            f"Report insight extraction failed for session {session_id}: {str(e)}",
            extra={"session_id": session_id},
        )
        doc_ids = [report["metadata"]["doc_id"] for report in reports]
        if doc_ids:
            _mark_reports_failed(doc_ids)


def build_extract_insights_reports(context: ResultSessionContext) -> list[dict]:
    if context.medical_history is None:
        return []

    client_id = str(context.session.pk)
    name, age, gender = _extraction_client_identity(context)

    return [
        {
            "filebytestream": report.file.read(),
            "filename": report.original_filename,
            "metadata": {
                "doc_id": str(report.pk),
                "upload_date": report.created_at.strftime("%Y-%m-%d"),
            },
            "client_details": {
                "client_id": client_id,
                "name": name,
                "age": age,
                "gender": gender,
            },
        }
        for report in context.medical_history.medical_reports.all()
    ]

def _extraction_client_identity(
    context: ResultSessionContext,
) -> tuple[str, int | None, str]:
    if context.customer_profile is None:
        return "", None, ""

    profile = context.customer_profile
    name = f"{profile.first_name or ''} {profile.last_name or ''}".strip()
    age = calculate_age(profile.date_of_birth) if profile.date_of_birth else None
    return name, age, profile.gender or ""

def _parse_testing_date(report_date: str | None) -> date | None:
    if not report_date:
        return None
    try:
        return date.fromisoformat(report_date)
    except ValueError:
        logger.warning(f"Could not parse report_date {report_date!r} as ISO date")
        return None


def _persist_extraction_results(result: dict) -> None:
    processed = result.get("results", [])
    skipped = result.get("skipped", [])

    doc_ids = {doc["doc_id"] for doc in processed} | {
        item["doc_id"] for item in skipped if item.get("doc_id")
    }
    if not doc_ids:
        logger.info("No doc_ids in extraction result — nothing to persist")
        return

    reports_by_id = {
        str(report.pk): report
        for report in PreConsultationMedicalReport.objects.filter(pk__in=doc_ids)
    }

    for doc in processed:
        report = reports_by_id.get(doc["doc_id"])
        if report is None:
            logger.warning(
                f"Medical report {doc['doc_id']} not found for extraction result"
            )
            continue
        PreConsultationMedicalReportSummary.objects.update_or_create(
            medical_report=report,
            defaults={
                "summary": doc.get("summary", ""),
                "testing_location": doc.get("report_location") or "",
                "testing_date": _parse_testing_date(doc.get("report_date")),
                "is_flagged": doc.get("is_flagged", False),
                "generation_status": PreConsultationArtifactGenerationStatus.COMPLETED,
            },
        )

    for item in skipped:
        doc_id = item.get("doc_id")
        if not doc_id:
            continue
        report = reports_by_id.get(doc_id)
        if report is None:
            logger.warning(f"Medical report {doc_id} not found for skipped extraction")
            continue
        PreConsultationMedicalReportSummary.objects.update_or_create(
            medical_report=report,
            defaults={"generation_status": PreConsultationArtifactGenerationStatus.FAILED},
        )

    logger.info(
        f"Persisted extraction results: {len(processed)} completed, "
        f"{len(skipped)} skipped/failed"
    )

def _mark_reports_failed(doc_ids: list[str]) -> None:
    reports = PreConsultationMedicalReport.objects.filter(pk__in=doc_ids)
    for report in reports:
        PreConsultationMedicalReportSummary.objects.update_or_create(
            medical_report=report,
            defaults={"generation_status": PreConsultationArtifactGenerationStatus.FAILED},
        )
    logger.info(f"Marked {len(reports)} report(s) as FAILED after extraction call error")
