"""Transform pre-consultation session context into LLM-ready client_details dict."""

from accounts.users.utils.helper import calculate_age
from pre_consultation.result_session import ResultSessionContext
from pre_consultation.utils.directive import (
    get_directive_category_label_map,
    get_directive_concern_label_map,
    get_directive_concern_sources,
    get_directive_diagnosis_label_map,
    get_directive_impact_label_map,
    get_directive_age_band_label_map,
    get_directive_family_relation_label_map,
    get_directive_symptom_label_map,
    get_directive_health_goals,
    get_directive_lifestyle_fields,
    get_directive_lifestyle_signal_label_map,
    get_directive_cluster_probes_for_cluster,
    get_concern_cluster_ids_map,
    get_directive_sexual_health_questions_for_gender,
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
    """Build patient_baseline dict from customer_profile."""
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
    """Build category_selections list with resolved labels."""
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
    """Build concerns list with nested symptoms, sources, family_history, probe_answers."""
    concern_label_map = get_directive_concern_label_map()
    functional_impact_map = get_directive_impact_label_map("functional_impact")
    duration_impact_map = get_directive_impact_label_map("duration_impact")
    progression_impact_map = get_directive_impact_label_map(
        "progression_impact"
    )
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
    """Build medical_history dict with diagnoses, medications, allergies, surgeries, sexual_health_answers."""
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
        {"name": allergy.name}
        for allergy in context.medical_history.allergies.all()
    ]

    surgeries = [
        {
            "name": surgery.name,
            "area": surgery.area,
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
    """Build sexual_health_answers list (best-effort, handles missing gender/questions gracefully)."""
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
        question_label = question_label_map.get(
            sha.question_id, sha.question_id
        )
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
    """Build cluster_scores list with resolved lifestyle signal labels."""
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
    """Build health_goals list with resolved labels, ordered by priority."""
    health_goal_label_map = _build_health_goal_label_map()

    return [
        {
            "goal_label": health_goal_label_map.get(goal.goal_id, goal.goal_id),
            "priority": goal.priority,
        }
        for goal in context.session.health_goals.order_by("priority")
    ]


def _lifestyle_answers_payload(context: ResultSessionContext) -> list[dict]:
    """Build lifestyle_answers list with resolved field and option labels."""
    lifestyle_fields = get_directive_lifestyle_fields()

    field_label_map = {lf["id"]: lf["label"] for lf in lifestyle_fields}
    option_label_map = {}
    for lf in lifestyle_fields:
        option_label_map[lf["id"]] = {
            opt["value"]: opt["label"] for opt in lf["options"]
        }

    return [
        {
            "field_label": field_label_map.get(
                answer.field_id, answer.field_id
            ),
            "option_value": answer.option_value,
            "option_label": option_label_map.get(answer.field_id, {}).get(
                answer.option_value,
                answer.option_value,
            ),
        }
        for answer in context.session.lifestyle_answers.all()
    ]


def build_extract_insights_reports(context: ResultSessionContext) -> list[dict]:
    """Build the `reports` list for extract_insights_batch from a session's uploaded medical reports."""
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
    """Resolve (name, age, gender) for extraction client_details from customer_profile."""
    if context.customer_profile is None:
        return "", None, ""

    profile = context.customer_profile
    name = f"{profile.first_name or ''} {profile.last_name or ''}".strip()
    age = (
        calculate_age(profile.date_of_birth) if profile.date_of_birth else None
    )
    return name, age, profile.gender or ""


def _build_concern_source_label_map() -> dict[str, str]:
    """Build concern_source id→label map from directive data."""
    return {cs["id"]: cs["label"] for cs in get_directive_concern_sources()}


def _build_health_goal_label_map() -> dict[str, str]:
    """Build health_goal id→label map from directive data."""
    return {hg["id"]: hg["label"] for hg in get_directive_health_goals()}
