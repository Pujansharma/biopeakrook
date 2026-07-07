"""Compute and persist lifestyle + cluster confidence scores for a session."""

from __future__ import annotations

from pre_consultation.models import (
    PreConsultationSession,
    PreConsultationSessionClusterScore,
)
from pre_consultation.utils.cluster_confidence_engine import (
    ClusterConfidenceEngine,
    ClusterConfidenceInput,
)
from pre_consultation.utils.directive import get_directive_cluster_probes_for_cluster
from pre_consultation.utils.engine_directive import (
    FamilyRelativeInput,
    FamilyRiskEngine,
    load_directive,
)
from pre_consultation.utils.lifestyle_contribution_engine import (
    LifestyleContributionEngine,
)


def build_family_risk_by_cluster(session: PreConsultationSession) -> dict[str, int]:
    """Aggregate family-history burden per cluster from concerns sourced as family."""
    family_risk_engine = FamilyRiskEngine()
    concern_burdens: dict[str, float] = {}
    for concern in session.concerns.prefetch_related("family_history", "sources"):
        if not concern.sources.filter(source_id="family").exists():
            continue
        relatives = [
            FamilyRelativeInput(
                relation_id=family_history.relation_id,
                age_band_id=family_history.age_band_id,
            )
            for family_history in concern.family_history.all()
        ]
        if relatives:
            concern_burdens[concern.concern_id] = family_risk_engine.concern_burden(
                relatives
            )
    return family_risk_engine.cluster_contribution_from_concern_burdens(concern_burdens)


def build_concern_scores_for_cluster(
    session: PreConsultationSession,
    cluster_id: str,
    cluster_concern_map: dict[str, list[str]],
) -> list[int]:
    concern_ids = set(cluster_concern_map.get(cluster_id, []))
    return [
        concern.confidence_score
        for concern in session.concerns.all()
        if concern.concern_id in concern_ids
    ]


def build_cluster_probe_ids(cluster_id: str) -> set[str]:
    return {
        cluster_probe["id"]
        for cluster_probe in get_directive_cluster_probes_for_cluster(cluster_id)
    }


def build_cluster_validation_stats(
    session: PreConsultationSession,
    cluster_id: str,
    provisional_score: int,
    cluster_confidence_engine: ClusterConfidenceEngine,
) -> tuple[bool, int, int, str | None]:
    cluster_probe_ids = build_cluster_probe_ids(cluster_id)
    questions_asked = 0
    positive_answers = 0
    for concern in session.concerns.prefetch_related("probe_answers"):
        for probe_answer in concern.probe_answers.all():
            if probe_answer.probe_id not in cluster_probe_ids:
                continue
            questions_asked += 1
            positive_answers += probe_answer.value

    probed = questions_asked > 0
    skip_reason = None
    if not probed:
        # Derive why cluster_probe layer was skipped (settled, weak signal, etc.).
        probe_action = cluster_confidence_engine.probe_action(provisional_score)
        if probe_action == "skip":
            if provisional_score >= 80:
                skip_reason = "settled"
            else:
                skip_reason = "weak_signal"
        else:
            skip_reason = "not_probed"
    return probed, positive_answers, questions_asked, skip_reason


def compute_session_cluster_scores(
    session: PreConsultationSession,
    lifestyle_answers: dict[str, str],
) -> tuple[dict, dict]:
    catalog = load_directive()
    lifestyle_engine = LifestyleContributionEngine.from_catalog(catalog)
    cluster_confidence_engine = ClusterConfidenceEngine(catalog)
    lifestyle_results = lifestyle_engine.evaluate(lifestyle_answers)
    family_risk_by_cluster = build_family_risk_by_cluster(session)
    cluster_concern_map = catalog.cluster_concern_map

    lifestyle_payload: dict[str, dict] = {}
    confidence_payload: dict[str, dict] = {}

    for cluster_id, lifestyle_result in lifestyle_results.items():
        lifestyle_payload[cluster_id] = lifestyle_result.to_dict()

        provisional_input = ClusterConfidenceInput(
            cluster_id=cluster_id,
            participating_concern_final_scores=build_concern_scores_for_cluster(
                session,
                cluster_id,
                cluster_concern_map,
            ),
            family_risk_contribution=family_risk_by_cluster.get(cluster_id, 0),
            lifestyle_signal_count=lifestyle_result.lifestyle_signal_count,
        )
        provisional_score = min(
            cluster_confidence_engine.base_concern_contribution(
                provisional_input.participating_concern_final_scores
            )
            + min(
                provisional_input.family_risk_contribution,
                catalog.cluster_conf["component_max"]["family_risk"],
            )
            + min(
                catalog.lifestyle_score(provisional_input.lifestyle_signal_count),
                catalog.cluster_conf["component_max"]["lifestyle"],
            ),
            catalog.cluster_conf["component_max"]["provisional"],
        )
        validation_probed, validation_positive, validation_questions, skip_reason = (
            build_cluster_validation_stats(
                session,
                cluster_id,
                provisional_score,
                cluster_confidence_engine,
            )
        )
        confidence_result = cluster_confidence_engine.compute(
            ClusterConfidenceInput(
                cluster_id=cluster_id,
                participating_concern_final_scores=provisional_input.participating_concern_final_scores,
                family_risk_contribution=provisional_input.family_risk_contribution,
                lifestyle_signal_count=provisional_input.lifestyle_signal_count,
                validation_probed=validation_probed,
                validation_positive_answers=validation_positive,
                validation_questions_asked=validation_questions,
                validation_skip_reason=skip_reason,
            )
        )
        confidence_payload[cluster_id] = confidence_result.to_dict()

    return lifestyle_payload, confidence_payload


def persist_session_cluster_scores(
    session: PreConsultationSession,
    lifestyle_answers: dict[str, str],
) -> None:
    lifestyle_payload, confidence_payload = compute_session_cluster_scores(
        session,
        lifestyle_answers,
    )
    session.cluster_scores.all().delete()
    rows = []
    for cluster_id, lifestyle_row in lifestyle_payload.items():
        confidence_row = confidence_payload[cluster_id]
        rows.append(
            PreConsultationSessionClusterScore(
                session=session,
                cluster_id=cluster_id,
                cluster_label=lifestyle_row["cluster_label"],
                lifestyle_signal_count=lifestyle_row["lifestyle_signal_count"],
                lifestyle_signals_triggered=lifestyle_row[
                    "lifestyle_signals_triggered"
                ],
                lifestyle_contribution=lifestyle_row["lifestyle_contribution"],
                base_concern_contribution=confidence_row["base_concern_contribution"],
                family_risk_contribution=confidence_row["family_risk_contribution"],
                provisional_score=confidence_row["provisional_score"],
                validation_probed=confidence_row["validation_probed"],
                validation_contribution=confidence_row["validation_contribution"],
                validation_skip_reason=confidence_row["validation_skip_reason"] or "",
                final_score=confidence_row["final_score"],
                bucket_id=confidence_row["bucket_id"],
                bucket_label=confidence_row["bucket_label"],
            )
        )
    PreConsultationSessionClusterScore.objects.bulk_create(rows)


def build_cluster_score_response(session: PreConsultationSession) -> dict:
    lifestyle_rows = []
    confidence_rows = []
    for cluster_score in session.cluster_scores.order_by("cluster_id"):
        lifestyle_rows.append(
            {
                "cluster_id": cluster_score.cluster_id,
                "cluster_label": cluster_score.cluster_label,
                "lifestyle_signal_count": cluster_score.lifestyle_signal_count,
                "lifestyle_signals_triggered": list(
                    cluster_score.lifestyle_signals_triggered
                ),
                "lifestyle_contribution": cluster_score.lifestyle_contribution,
            }
        )
        confidence_rows.append(
            {
                "cluster_id": cluster_score.cluster_id,
                "cluster_label": cluster_score.cluster_label,
                "base_concern_contribution": cluster_score.base_concern_contribution,
                "family_risk_contribution": cluster_score.family_risk_contribution,
                "lifestyle_contribution": cluster_score.lifestyle_contribution,
                "provisional_score": cluster_score.provisional_score,
                "validation_probed": cluster_score.validation_probed,
                "validation_contribution": cluster_score.validation_contribution,
                "validation_skip_reason": cluster_score.validation_skip_reason or None,
                "final_score": cluster_score.final_score,
                "bucket_id": cluster_score.bucket_id,
                "bucket_label": cluster_score.bucket_label,
            }
        )
    return {
        "cluster_lifestyle": lifestyle_rows,
        "cluster_confidence": confidence_rows,
    }


def delete_session_cluster_scores(session: PreConsultationSession) -> None:
    session.cluster_scores.all().delete()
