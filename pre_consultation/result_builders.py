"""Payload builders for pre-consultation result APIs keyed by user_id."""

from __future__ import annotations

from django.db.models import F, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce, Concat

from accounts.customers.models import CustomerProfile
from accounts.users.utils.helper import calculate_age
from core.utils.db.functions import ExtractPartText
from pre_consultation.models import PreConsultationSession
from pre_consultation.layers.patient_baseline import customer_profile_to_payload_v2
from pre_consultation.layers.patient_medical_history_context import (
    get_customer_profile_gender_and_age,
)
from pre_consultation.layers.patient_goals_priorities import (
    build_health_goals_response,
    get_session_stored_health_goals,
)
from pre_consultation.layers.patient_lifestyle_environment import (
    get_session_lifestyle_answers,
)
from pre_consultation.models import PreConsultationConcern
from pre_consultation.persistence import get_session_category_ids
from pre_consultation.result import build_overview_goals_payload
from pre_consultation.result_session import ResultSessionContext
from pre_consultation.utils.constants import (
    PreConsultationConcernSourceId,
    PreConsultationMedicationStatus,
)
from pre_consultation.utils.directive import (
    get_concern_category_id_map,
    get_concern_cluster_ids_map,
    get_directive_age_band_label_map,
    get_directive_category_label_map,
    get_directive_cluster_label_map,
    get_directive_cluster_metadata_map,
    get_directive_cluster_probes_for_cluster,
    get_directive_concern_label_map,
    get_directive_diagnosis_label_map,
    get_directive_reproductive_diagnoses_for_gender,
    get_directive_family_relation_label_map,
    get_directive_sexual_health_questions_for_gender,
    get_directive_health_goals,
    get_directive_impact_label_map,
    get_directive_lifestyle_fields,
    get_directive_lifestyle_signal_label_map,
    get_directive_symptom_label_map,
    get_directive_data,
)
from pre_consultation.utils.engine_directive import FamilyRelativeInput, FamilyRiskEngine


def _artifact_text(context: ResultSessionContext, field_name: str) -> str:
    artifacts = getattr(context.session, "artifacts", None)
    if artifacts is None:
        return ""
    return getattr(artifacts, field_name, "") or ""


def _concern_bucket_label(context: ResultSessionContext, confidence_score: int) -> str:
    _bucket_id, bucket_label = context.catalog.bucket_for_score(
        confidence_score,
        "concern_bucket",
    )
    return bucket_label


def _family_risk_bucket_label(context: ResultSessionContext, burden: float) -> str:
    risk_level_id = FamilyRiskEngine(context.catalog).risk_level_id(burden)
    for row in get_directive_data()["family_risk_contribution"]:
        if row["id"] == risk_level_id:
            return row["label"]
    return risk_level_id


def _session_concerns(context: ResultSessionContext) -> list[PreConsultationConcern]:
    return list(context.session.concerns.order_by("-confidence_score", "created_at"))


def _non_zero_cluster_scores(context: ResultSessionContext):
    return [
        cluster_score
        for cluster_score in context.session.cluster_scores.order_by(
            "-final_score",
            "cluster_id",
        )
        if cluster_score.final_score > 0
    ]


def _selected_diagnosis_ids(context: ResultSessionContext) -> set[str]:
    if context.medical_history is None:
        return set()
    return set(
        context.medical_history.diagnoses.filter(is_reproductive=False).values_list(
            "diagnosis_id",
            flat=True,
        )
    )


def _medication_entries(context: ResultSessionContext) -> list[dict[str, str]]:
    if context.medical_history is None:
        return []
    return [
        {
            "label": medication.name,
            "dosage": medication.dosage,
            "frequency": medication.frequency,
            "duration": medication.duration,
        }
        for medication in context.medical_history.medications.order_by("created_at")
    ]


def _concern_evidence_count(concern: PreConsultationConcern) -> int:
    symptom_count = concern.symptoms.count()
    source_count = concern.sources.count()
    family_count = concern.family_history.count()
    probe_positive_count = sum(
        probe_answer.value for probe_answer in concern.probe_answers.all()
    )
    impact_count = sum(
        1
        for impact_id in (
            concern.functional_impact_id,
            concern.duration_impact_id,
            concern.progression_impact_id,
        )
        if impact_id
    )
    return symptom_count + source_count + family_count + probe_positive_count + impact_count


def _concern_has_family_history(concern: PreConsultationConcern) -> bool:
    return concern.family_history.exists()


def _cluster_session_concern_labels(
    context: ResultSessionContext,
    cluster_id: str,
) -> list[str]:
    concern_label_map = get_directive_concern_label_map()
    cluster_metadata = get_directive_cluster_metadata_map().get(cluster_id, {})
    cluster_concern_ids = set(cluster_metadata.get("concern_id", []))
    session_concern_ids = {
        concern.concern_id for concern in _session_concerns(context)
    }
    return [
        concern_label_map[concern_id]
        for concern_id in sorted(cluster_concern_ids & session_concern_ids)
    ]


def serialize_checklist_item(checklist_item) -> dict:
    return {
        "id": str(checklist_item.pk),
        "done": checklist_item.marked,
        "identified_concern": checklist_item.identified_concern,
    }


def build_overview_payload(context: ResultSessionContext) -> dict:
    checklist = [
        serialize_checklist_item(checklist_item)
        for checklist_item in context.session.preparation_checklist_items.order_by(
            "created_at"
        )
    ]
    return {
        "summary": _artifact_text(context, "summary"),
        "checklist": checklist,
        "goals": build_overview_goals_payload(context.session),
    }


def build_context_payload(context: ResultSessionContext) -> dict:
    concern_label_map = get_directive_concern_label_map()
    top_concerns = []
    for concern in _session_concerns(context)[:5]:
        top_concerns.append(
            {
                "label": concern_label_map[concern.concern_id],
                "confidence_score": concern.confidence_score,
                "concern_bucket": _concern_bucket_label(
                    context,
                    concern.confidence_score,
                ),
            }
        )

    cluster_metadata_map = get_directive_cluster_metadata_map()
    top_clusters = []
    for cluster_score in _non_zero_cluster_scores(context)[:3]:
        cluster_concern_ids = set(
            cluster_metadata_map.get(cluster_score.cluster_id, {}).get(
                "concern_id",
                []
            )
        )
        session_concern_ids = {
            concern.concern_id for concern in _session_concerns(context)
        }
        concern_count = len(cluster_concern_ids & session_concern_ids)
        lifestyle_signal_count = cluster_score.lifestyle_signal_count
        top_clusters.append(
            {
                "label": cluster_score.cluster_label,
                "concern_count": concern_count + lifestyle_signal_count,
            }
        )

    medication_status = (
        context.medical_history.medication_status if context.medical_history else ""
    )
    current_medications: list[dict[str, str]] = []
    if medication_status in {
        PreConsultationMedicationStatus.MEDICATION,
        PreConsultationMedicationStatus.MEDICATION_SUPPLEMENT,
    }:
        current_medications = [
            {
                "label": entry["label"],
                "dosage": entry["dosage"],
                "frequency": entry["frequency"],
            }
            for entry in _medication_entries(context)
        ]

    progression_label_map = get_directive_impact_label_map("progression_impact")
    diagnosis_label_map = get_directive_diagnosis_label_map()
    know_diagnosis = []
    for diagnosis_id in sorted(_selected_diagnosis_ids(context)):
        if diagnosis_id == "none":
            continue
        progression_impact_label = ""
        diagnosis_row = next(
            (
                diagnosis
                for diagnosis in get_directive_data()["diagnosis"]
                if diagnosis["id"] == diagnosis_id
            ),
            None,
        )
        if diagnosis_row is not None:
            for concern_id in diagnosis_row.get("concern_id", []):
                concern = context.session.concerns.filter(
                    concern_id=concern_id,
                ).first()
                if concern is not None and concern.progression_impact_id:
                    progression_impact_label = progression_label_map.get(
                        concern.progression_impact_id,
                        "",
                    )
                    break
        know_diagnosis.append(
            {
                "label": diagnosis_label_map.get(diagnosis_id, diagnosis_id),
                "progression_impact": progression_impact_label,
            }
        )

    return {
        "quick_summary": _artifact_text(context, "quick_summary"),
        "top_5_concerns": top_concerns,
        "top_3_clusters": top_clusters,
        "current_medications": current_medications,
        "know_diagnosis": know_diagnosis,
    }


def build_family_risk_payload(context: ResultSessionContext) -> dict:
    concern_label_map = get_directive_concern_label_map()
    relation_label_map = get_directive_family_relation_label_map()
    age_band_label_map = get_directive_age_band_label_map()
    family_risk_engine = FamilyRiskEngine(context.catalog)

    patient_name = ""
    patient_age = None
    if context.customer_profile is not None:
        first_name = context.customer_profile.first_name or ""
        last_name = context.customer_profile.last_name or ""
        patient_name = f"{first_name} {last_name}".strip()
        patient_age = calculate_age(context.customer_profile.date_of_birth)

    family_relations = []
    seen_relation_keys: set[tuple[str, str, str]] = set()
    family_concern_count: dict[str, int] = {}
    cluster_contribution_rows = []

    for concern in _session_concerns(context):
        if not concern.sources.filter(source_id=PreConsultationConcernSourceId.FAMILY).exists():
            continue
        concern_label = concern_label_map[concern.concern_id]
        family_member_count = concern.family_history.count()
        if family_member_count:
            family_concern_count[concern_label] = family_member_count

        relatives = [
            FamilyRelativeInput(
                relation_id=family_history.relation_id,
                age_band_id=family_history.age_band_id,
            )
            for family_history in concern.family_history.all()
        ]
        burden = family_risk_engine.concern_burden(relatives) if relatives else 0.0
        contribution_bucket = _family_risk_bucket_label(context, burden)
        for cluster_id in get_concern_cluster_ids_map().get(concern.concern_id, []):
            cluster_contribution_rows.append(
                {
                    "cluster": get_directive_cluster_label_map().get(
                        cluster_id,
                        cluster_id,
                    ),
                    "concern": concern_label,
                    "contribution_bucket": contribution_bucket,
                }
            )

        for family_history in concern.family_history.all():
            relation_key = (
                family_history.relation_id,
                family_history.age_band_id,
                concern.concern_id,
            )
            if relation_key in seen_relation_keys:
                continue
            seen_relation_keys.add(relation_key)
            family_relations.append(
                {
                    "label": relation_label_map.get(
                        family_history.relation_id,
                        family_history.relation_id,
                    ),
                    "age_band": age_band_label_map.get(
                        family_history.age_band_id,
                        family_history.age_band_id,
                    ),
                    "flagged_concern": concern_label,
                }
            )

    return {
        "patient": {
            "name": patient_name,
            "age": patient_age,
        },
        "family_relations": family_relations,
        "family_concern_count": family_concern_count,
        "family_risk_summary": _artifact_text(context, "family_risk_summary"),
        "family_history_cluster_contribution": cluster_contribution_rows,
    }


def build_health_map_payload(context: ResultSessionContext) -> dict:
    concern_label_map = get_directive_concern_label_map()
    functional_label_map = get_directive_impact_label_map("functional_impact")
    duration_label_map = get_directive_impact_label_map("duration_impact")
    progression_label_map = get_directive_impact_label_map("progression_impact")
    non_zero_cluster_ids = {
        cluster_score.cluster_id for cluster_score in _non_zero_cluster_scores(context)
    }

    concerns_payload = []
    for concern in _session_concerns(context):
        mapped_cluster_ids = get_concern_cluster_ids_map().get(concern.concern_id, [])
        map_cluster_count = len(
            [cluster_id for cluster_id in mapped_cluster_ids if cluster_id in non_zero_cluster_ids]
        )
        concerns_payload.append(
            {
                "label": concern_label_map[concern.concern_id],
                "duration_impact": duration_label_map.get(
                    concern.duration_impact_id,
                    "",
                ),
                "functional_impact": functional_label_map.get(
                    concern.functional_impact_id,
                    "",
                ),
                "concern_bucket": _concern_bucket_label(
                    context,
                    concern.confidence_score,
                ),
                "progression_impact": progression_label_map.get(
                    concern.progression_impact_id,
                    "",
                ),
                "evidence_count": _concern_evidence_count(concern),
                "has_family_history": _concern_has_family_history(concern),
                "map_cluster_count": map_cluster_count,
            }
        )
    return {"concerns": concerns_payload}


def _cluster_supporting_diagnosis_labels(
    context: ResultSessionContext,
    cluster_id: str,
) -> list[str]:
    diagnosis_label_map = get_directive_diagnosis_label_map()
    selected_diagnosis_ids = _selected_diagnosis_ids(context)
    cluster_metadata = get_directive_cluster_metadata_map().get(cluster_id, {})
    cluster_concern_ids = set(cluster_metadata.get("concern_id", []))
    supporting_diagnosis_labels: list[str] = []
    for diagnosis in get_directive_data()["diagnosis"]:
        if diagnosis["id"] not in selected_diagnosis_ids:
            continue
        mapped_concern_ids = set(diagnosis.get("concern_id", []))
        if mapped_concern_ids & cluster_concern_ids:
            supporting_diagnosis_labels.append(
                diagnosis_label_map.get(diagnosis["id"], diagnosis["id"])
            )
    return supporting_diagnosis_labels


def _cluster_family_history_labels(
    context: ResultSessionContext,
    cluster_id: str,
) -> list[str]:
    concern_label_map = get_directive_concern_label_map()
    cluster_concern_ids = set(
        get_directive_cluster_metadata_map().get(cluster_id, {}).get("concern_id", [])
    )
    labels = []
    for concern in _session_concerns(context):
        if concern.concern_id not in cluster_concern_ids:
            continue
        if not _concern_has_family_history(concern):
            continue
        labels.append(concern_label_map[concern.concern_id])
    return labels


def _cluster_positive_probe_labels(
    context: ResultSessionContext,
    cluster_id: str,
) -> list[str]:
    cluster_probe_ids = {
        cluster_probe["id"]
        for cluster_probe in get_directive_cluster_probes_for_cluster(cluster_id)
    }
    probe_label_by_id = {
        cluster_probe["id"]: cluster_probe["label"]
        for cluster_probe in get_directive_cluster_probes_for_cluster(cluster_id)
    }
    positive_probe_labels: list[str] = []
    for concern in _session_concerns(context):
        for probe_answer in concern.probe_answers.all():
            if probe_answer.probe_id not in cluster_probe_ids:
                continue
            if probe_answer.value != 1:
                continue
            positive_probe_labels.append(
                probe_label_by_id.get(probe_answer.probe_id, probe_answer.probe_id)
            )
    return positive_probe_labels


def build_clusters_payload(context: ResultSessionContext) -> dict:
    lifestyle_signal_label_map = get_directive_lifestyle_signal_label_map()
    clusters_payload = []
    for cluster_score in _non_zero_cluster_scores(context):
        evidence_points = (
            cluster_score.base_concern_contribution
            + cluster_score.family_risk_contribution
            + cluster_score.lifestyle_contribution
            + cluster_score.validation_contribution
        )
        lifestyle_factors = [
            lifestyle_signal_label_map.get(signal_id, signal_id)
            for signal_id in cluster_score.lifestyle_signals_triggered
        ]
        clusters_payload.append(
            {
                "label": cluster_score.cluster_label,
                "cluster_bucket": cluster_score.bucket_label,
                "evidence_points": evidence_points,
                "concerns": _cluster_session_concern_labels(
                    context,
                    cluster_score.cluster_id,
                ),
                "supporting_diagnosis": _cluster_supporting_diagnosis_labels(
                    context,
                    cluster_score.cluster_id,
                ),
                "family_history": _cluster_family_history_labels(
                    context,
                    cluster_score.cluster_id,
                ),
                "lifestyle_factors": lifestyle_factors,
                "probe": _cluster_positive_probe_labels(
                    context,
                    cluster_score.cluster_id,
                ),
            }
        )
    return {"clusters": clusters_payload}


def _lifestyle_option_label_map() -> dict[str, dict[str, str]]:
    option_label_by_field_id: dict[str, dict[str, str]] = {}
    for lifestyle_field in get_directive_lifestyle_fields():
        option_label_by_field_id[lifestyle_field["id"]] = {
            option["value"]: option["label"] for option in lifestyle_field["options"]
        }
    return option_label_by_field_id


def _mapped_concerns_for_lifestyle_field(
    context: ResultSessionContext,
    field_id: str,
    option_value: str,
) -> list[str]:
    triggered_signals = []
    for lifestyle_signal in get_directive_data()["lifestyle_signal"]:
        if lifestyle_signal["field_id"] != field_id:
            continue
        if option_value not in lifestyle_signal["trigger_values"]:
            continue
        triggered_signals.append(lifestyle_signal["id"])

    if not triggered_signals:
        return []

    cluster_ids: set[str] = set()
    for lifestyle_cluster_map in get_directive_data()["lifestyle_cluster_map"]:
        eligible_signal_ids = set(lifestyle_cluster_map["eligible_signal_id"])
        if eligible_signal_ids & set(triggered_signals):
            cluster_ids.add(lifestyle_cluster_map["cluster_id"])

    concern_label_map = get_directive_concern_label_map()
    session_concern_ids = {concern.concern_id for concern in _session_concerns(context)}
    mapped_concern_labels: list[str] = []
    for cluster_id in sorted(cluster_ids):
        cluster_concern_ids = set(
            get_directive_cluster_metadata_map().get(cluster_id, {}).get(
                "concern_id",
                []
            )
        )
        for concern_id in sorted(cluster_concern_ids & session_concern_ids):
            mapped_concern_labels.append(concern_label_map[concern_id])
    return mapped_concern_labels


def _mapped_cluster_labels_for_lifestyle_field(
    context: ResultSessionContext,
    field_id: str,
    option_value: str,
) -> list[str]:
    triggered_signals = []
    for lifestyle_signal in get_directive_data()["lifestyle_signal"]:
        if lifestyle_signal["field_id"] != field_id:
            continue
        if option_value not in lifestyle_signal["trigger_values"]:
            continue
        triggered_signals.append(lifestyle_signal["id"])

    cluster_label_map = get_directive_cluster_label_map()
    cluster_labels: list[str] = []
    for lifestyle_cluster_map in get_directive_data()["lifestyle_cluster_map"]:
        eligible_signal_ids = set(lifestyle_cluster_map["eligible_signal_id"])
        if not (eligible_signal_ids & set(triggered_signals)):
            continue
        cluster_id = lifestyle_cluster_map["cluster_id"]
        cluster_labels.append(cluster_label_map.get(cluster_id, cluster_id))
    return cluster_labels


def build_lifestyle_payload(context: ResultSessionContext) -> dict:
    selected_lifestyle_answers = get_session_lifestyle_answers(context.session)
    option_label_by_field_id = _lifestyle_option_label_map()
    lifestyle_rows = []
    for lifestyle_field in get_directive_lifestyle_fields():
        field_id = lifestyle_field["id"]
        selected_option_value = selected_lifestyle_answers.get(field_id)
        if selected_option_value is None:
            continue
        answer_label = option_label_by_field_id[field_id].get(
            selected_option_value,
            selected_option_value,
        )
        lifestyle_rows.append(
            {
                "label": lifestyle_field["label"],
                "answer": answer_label,
                "mapped_concerns": _mapped_concerns_for_lifestyle_field(
                    context,
                    field_id,
                    selected_option_value,
                ),
                "mapped_clusters": _mapped_cluster_labels_for_lifestyle_field(
                    context,
                    field_id,
                    selected_option_value,
                ),
            }
        )
    return {"life_style": lifestyle_rows}


def build_medical_context_payload(context: ResultSessionContext) -> dict:
    diagnosis_label_map = get_directive_diagnosis_label_map()
    cluster_label_map = get_directive_cluster_label_map()
    medication_entries = _medication_entries(context)
    medication_status = (
        context.medical_history.medication_status if context.medical_history else ""
    )

    diagnosis_rows = []
    for diagnosis_id in sorted(_selected_diagnosis_ids(context)):
        if diagnosis_id == "none":
            continue
        diagnosis_row = next(
            (
                diagnosis
                for diagnosis in get_directive_data()["diagnosis"]
                if diagnosis["id"] == diagnosis_id
            ),
            None,
        )
        mapped_cluster_labels = []
        if diagnosis_row is not None:
            cluster_ids: set[str] = set()
            for concern_id in diagnosis_row.get("concern_id", []):
                cluster_ids.update(get_concern_cluster_ids_map().get(concern_id, []))
            mapped_cluster_labels = [
                cluster_label_map.get(cluster_id, cluster_id)
                for cluster_id in sorted(cluster_ids)
            ]
        diagnosis_rows.append(
            {
                "label": diagnosis_label_map.get(diagnosis_id, diagnosis_id),
                "mapped_cluster": mapped_cluster_labels,
            }
        )

    medications: list[dict[str, str]] = []
    supplements: list[dict[str, str]] = []
    if medication_status in {
        PreConsultationMedicationStatus.MEDICATION,
        PreConsultationMedicationStatus.MEDICATION_SUPPLEMENT,
    }:
        medications = medication_entries
    if medication_status in {
        PreConsultationMedicationStatus.SUPPLEMENTS,
        PreConsultationMedicationStatus.MEDICATION_SUPPLEMENT,
    }:
        supplements = medication_entries

    surgeries = []
    if context.medical_history is not None:
        surgeries = [
            surgery.name
            for surgery in context.medical_history.surgeries.order_by("created_at")
        ]

    return {
        "diagnosis": diagnosis_rows,
        "medications": medications,
        "suppliments": supplements,
        "surgeries": surgeries,
    }


def _raw_data_diagnosis_labels(context: ResultSessionContext) -> list[str]:
    if context.medical_history is None:
        return []

    diagnosis_label_map = get_directive_diagnosis_label_map()
    gender, _age_years = get_customer_profile_gender_and_age(context.customer_profile)
    reproductive_label_map: dict[str, str] = {}
    if gender is not None:
        reproductive_label_map = {
            reproductive_diagnosis["id"]: reproductive_diagnosis["label"]
            for reproductive_diagnosis in get_directive_reproductive_diagnoses_for_gender(
                gender
            )
        }

    diagnosis_labels: list[str] = []
    for diagnosis in context.medical_history.diagnoses.order_by("created_at"):
        if diagnosis.is_reproductive:
            label = reproductive_label_map.get(
                diagnosis.diagnosis_id,
                diagnosis.diagnosis_id,
            )
        else:
            label = diagnosis_label_map.get(
                diagnosis.diagnosis_id,
                diagnosis.diagnosis_id,
            )
        diagnosis_labels.append(label)
    return diagnosis_labels


def _raw_data_medication_supplement_labels(context: ResultSessionContext) -> list[str]:
    if context.medical_history is None:
        return []

    medication_status = context.medical_history.medication_status
    if medication_status in {
        PreConsultationMedicationStatus.NO,
        "",
    }:
        return []

    return [
        medication_entry["label"]
        for medication_entry in _medication_entries(context)
    ]


def _raw_data_allergy_labels(context: ResultSessionContext) -> list[str]:
    if context.medical_history is None:
        return []

    return [
        allergy.name
        for allergy in context.medical_history.allergies.order_by("created_at")
    ]


def _raw_data_sexual_health_rows(context: ResultSessionContext) -> list[dict[str, str]]:
    if context.medical_history is None:
        return []

    gender, age_years = get_customer_profile_gender_and_age(context.customer_profile)

    question_label_by_id: dict[str, str] = {}
    option_label_by_id: dict[str, str] = {}
    if gender is not None:
        for question in get_directive_sexual_health_questions_for_gender(
            gender,
            age_years,
        ):
            question_label_by_id[question["id"]] = question["label"]
            for option in question["options"]:
                option_label_by_id[option["id"]] = option["label"]

    sexual_health_rows: list[dict[str, str]] = []
    for answer in context.medical_history.sexual_health_answers.order_by("created_at"):
        sexual_health_rows.append(
            {
                "question": question_label_by_id.get(
                    answer.question_id,
                    answer.question_id,
                ),
                "answer": option_label_by_id.get(
                    answer.option_id,
                    answer.option_id,
                ),
            }
        )
    return sexual_health_rows


def _raw_data_family_medical_history_rows(
    context: ResultSessionContext,
) -> list[dict[str, str]]:
    relation_label_map = get_directive_family_relation_label_map()
    age_band_label_map = get_directive_age_band_label_map()
    concern_label_map = get_directive_concern_label_map()

    family_history_rows: list[dict[str, str]] = []
    seen_relation_keys: set[tuple[str, str, str]] = set()
    for concern in _session_concerns(context):
        concern_label = concern_label_map[concern.concern_id]
        for family_history in concern.family_history.all():
            relation_key = (
                family_history.relation_id,
                family_history.age_band_id,
                concern.concern_id,
            )
            if relation_key in seen_relation_keys:
                continue
            seen_relation_keys.add(relation_key)
            family_history_rows.append(
                {
                    "relation": relation_label_map.get(
                        family_history.relation_id,
                        family_history.relation_id,
                    ),
                    "age_band": age_band_label_map.get(
                        family_history.age_band_id,
                        family_history.age_band_id,
                    ),
                    "concern": concern_label,
                }
            )
    return family_history_rows


def _raw_data_surgery_rows(context: ResultSessionContext) -> list[dict[str, str]]:
    if context.medical_history is None:
        return []

    return [
        {
            "name": surgery.name,
            "performed_when": surgery.performed_when,
            "reason": surgery.reason,
        }
        for surgery in context.medical_history.surgeries.order_by("created_at")
    ]


def build_raw_data_payload(context: ResultSessionContext) -> dict:
    category_label_map = get_directive_category_label_map()
    concern_label_map = get_directive_concern_label_map()
    concern_category_id_map = get_concern_category_id_map()
    symptom_label_map = get_directive_symptom_label_map()
    functional_label_map = get_directive_impact_label_map("functional_impact")
    duration_label_map = get_directive_impact_label_map("duration_impact")
    progression_label_map = get_directive_impact_label_map("progression_impact")
    health_goal_label_map = {
        health_goal["id"]: health_goal["label"]
        for health_goal in get_directive_health_goals()
    }

    baseline_payload = {
        "name": "",
        "sex": None,
        "age": None,
        "city": "",
        "height": None,
        "weight": None,
    }
    if context.customer_profile is not None:
        profile_payload = customer_profile_to_payload_v2(context.customer_profile)
        address = profile_payload["address"]
        baseline_payload = {
            "name": f"{profile_payload['first_name']} {profile_payload['last_name']}".strip(),
            "sex": profile_payload["gender"],
            "age": calculate_age(context.customer_profile.date_of_birth),
            "city": address.get("city", ""),
            "height": profile_payload["height"],
            "weight": profile_payload["weight"],
        }

    patient_category = [
        category_label_map.get(category_id, category_id)
        for category_id in sorted(get_session_category_ids(context.session))
    ]

    patient_concern = []
    for concern in context.session.concerns.order_by("created_at"):
        category_id = concern_category_id_map.get(concern.concern_id, "")
        patient_concern.append(
            {
                "concern": {
                    "label": concern_label_map[concern.concern_id],
                    "health_system": category_label_map.get(category_id, category_id),
                }
            }
        )

    patient_symptom = []
    for concern in context.session.concerns.prefetch_related("symptoms").order_by(
        "created_at"
    ):
        for symptom in concern.symptoms.all():
            patient_symptom.append(
                symptom_label_map.get(symptom.symptom_id, symptom.symptom_id)
            )

    patient_concern_probe = []
    for concern in context.session.concerns.order_by("created_at"):
        concern_label = concern_label_map[concern.concern_id]
        for impact_id, impact_label in (
            (concern.functional_impact_id, functional_label_map),
            (concern.duration_impact_id, duration_label_map),
            (concern.progression_impact_id, progression_label_map),
        ):
            if not impact_id:
                continue
            patient_concern_probe.append(
                {
                    "concern": concern_label,
                    "label": impact_label.get(impact_id, impact_id),
                }
            )

    patient_cluster_probe = []
    for concern in context.session.concerns.prefetch_related("probe_answers").order_by(
        "created_at"
    ):
        probe_label_by_id = {}
        for cluster_id in get_concern_cluster_ids_map().get(concern.concern_id, []):
            for cluster_probe in get_directive_cluster_probes_for_cluster(cluster_id):
                probe_label_by_id[cluster_probe["id"]] = cluster_probe["label"]
        for probe_answer in concern.probe_answers.all():
            question_label = probe_label_by_id.get(
                probe_answer.probe_id,
                probe_answer.probe_id,
            )
            answer_label = "Yes" if probe_answer.value == 1 else "No"
            patient_cluster_probe.append(
                {
                    "question": question_label,
                    "answer": answer_label,
                }
            )

    patient_lifestyle_environment = []
    lifestyle_payload = build_lifestyle_payload(context)
    for lifestyle_row in lifestyle_payload["life_style"]:
        patient_lifestyle_environment.append(
            f"{lifestyle_row['label']}: {lifestyle_row['answer']}"
        )

    stored_health_goals = get_session_stored_health_goals(context.session)
    ranked_health_goals = build_health_goals_response(stored_health_goals)
    patient_goals_priorities = [
        health_goal_label_map.get(health_goal["id"], health_goal["id"])
        for health_goal in ranked_health_goals
        if health_goal["priority"] is not None
    ]

    return {
        "patient_baseline": baseline_payload,
        "patient_category": patient_category,
        "patient_concern": patient_concern,
        "patient_symptom": patient_symptom,
        "patient_concern_probe": patient_concern_probe,
        "patient_cluster_probe": patient_cluster_probe,
        "patient_medical_diagnosis": _raw_data_diagnosis_labels(context),
        "patient_medications_suppliments": _raw_data_medication_supplement_labels(
            context
        ),
        "patient_allergies": _raw_data_allergy_labels(context),
        "patient_sexual_health": _raw_data_sexual_health_rows(context),
        "patient_family_medical_history": _raw_data_family_medical_history_rows(
            context
        ),
        "patient_surgeries": _raw_data_surgery_rows(context),
        "patient_lifestyle_environment": patient_lifestyle_environment,
        "patient_goals_priorities": patient_goals_priorities,
    }


def build_notes_payload(context: ResultSessionContext) -> dict:
    return {
        "notes": [
            {
                "note": note.note,
                "category": note.category,
                "created_at": note.created_at,
            }
            for note in context.session.notes.order_by("-created_at")
        ]
    }


def build_surgery_payload(context: ResultSessionContext) -> dict:
    surgeries: list[dict[str, str]] = []
    if context.medical_history is not None:
        surgeries = [
            {
                "name": surgery.name,
                "performed_when": surgery.performed_when,
                "reason": surgery.reason,
            }
            for surgery in context.medical_history.surgeries.order_by("created_at")
        ]
    return {"surgeries": surgeries}


def _medical_report_download_url(medical_report) -> str:
    if not medical_report.file:
        return ""
    return medical_report.file.url


def build_medical_reports_payload(context: ResultSessionContext) -> dict:
    medical_reports: list[dict] = []
    if context.medical_history is not None:
        for medical_report in context.medical_history.medical_reports.order_by(
            "created_at"
        ):
            report_summary = getattr(medical_report, "summary", None)
            medical_reports.append(
                {
                    "name": medical_report.original_filename,
                    "download_url": _medical_report_download_url(medical_report),
                    "report_summary": report_summary.summary if report_summary else "",
                    "testing_location": (
                        report_summary.testing_location if report_summary else ""
                    ),
                    "testing_date": (
                        report_summary.testing_date if report_summary else None
                    ),
                    "is_flagged": (
                        report_summary.is_flagged if report_summary else False
                    ),
                }
            )
    return {"medical_reports": medical_reports}


def _session_list_profile_fields(
    session: PreConsultationSession,
    profile: CustomerProfile | None,
) -> dict:
    if profile is not None:
        return {
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "gender": profile.get_gender_display() if profile.gender else None,
            "date_of_birth": profile.date_of_birth,
            "height": profile.height_cm,
            "weight": profile.weight_kg,
        }

    user = session.user
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "gender": user.get_gender_display() if user.gender else None,
        "date_of_birth": user.date_of_birth,
        "height": None,
        "weight": None,
    }


def serialize_session_list_item(session: PreConsultationSession) -> dict:
    customer = getattr(session.user, "customer", None)
    main_profiles = getattr(customer, "main_profiles", None) if customer else None
    profile = main_profiles[0] if main_profiles else None
    phone = session.user.phone
    return {
        "user_id": str(session.user_id),
        "id": str(session.pk),
        "contact_email": customer.contact_email if customer else None,
        "phone": str(phone) if phone else None,
        "status": session.get_status_display(),
        **_session_list_profile_fields(session, profile),
    }


def get_session_list_queryset(search: str = "", center_id: str | None = None):
    main_profile_first_name = CustomerProfile.objects.filter(
        customer_id=OuterRef("user_id"),
        is_main=True,
    ).values("first_name")[:1]
    main_profile_last_name = CustomerProfile.objects.filter(
        customer_id=OuterRef("user_id"),
        is_main=True,
    ).values("last_name")[:1]
    main_profiles = CustomerProfile.objects.filter(is_main=True)
    queryset = (
        PreConsultationSession.objects.select_related(
            "user__customer",
        )
        .annotate(
            profile_first_name=Subquery(main_profile_first_name),
            profile_last_name=Subquery(main_profile_last_name),
            full_name=Concat(
                Coalesce(F("profile_first_name"), F("user__first_name"), Value("")),
                Value(" "),
                Coalesce(F("profile_last_name"), F("user__last_name"), Value("")),
            ),
            national_phone=ExtractPartText(
                F("user__phone"),
                Value("-"),
                Value("-1"),
            ),
        )
        .prefetch_related(
            Prefetch(
                "user__customer__profiles",
                queryset=main_profiles,
                to_attr="main_profiles",
            ),
        )
        .order_by("-created_at")
    )

    if center_id:
        queryset = queryset.filter(
            user__customer__profiles__center_assignments__center_id=center_id,
            user__customer__profiles__is_converted=True,
            user__customer__profiles__is_main=True,
        )

    if not search:
        return queryset

    search_query = Q()
    search_query |= Q(full_name__istartswith=search)
    search_query |= Q(national_phone__istartswith=search)
    search_query |= Q(user__customer__contact_email__istartswith=search)
    search_query |= Q(user__customer__contact_email__icontains=search)
    return queryset.filter(search_query)
