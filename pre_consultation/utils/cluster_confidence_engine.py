"""Cluster Confidence Engine — evidence for an underlying physiological pattern."""

from __future__ import annotations

from dataclasses import dataclass

from pre_consultation.utils.engine_directive import DirectiveCatalog, load_directive


@dataclass
class ClusterConfidenceInput:
    cluster_id: str
    participating_concern_final_scores: list[int]
    family_risk_contribution: int = 0
    lifestyle_signal_count: int = 0
    validation_probed: bool = False
    validation_positive_answers: int = 0
    validation_questions_asked: int = 0
    validation_skip_reason: str | None = None


@dataclass
class ClusterConfidenceResult:
    cluster_id: str
    base_concern_contribution: int
    family_risk_contribution: int
    lifestyle_contribution: int
    provisional_score: int
    validation_probed: bool
    validation_contribution: int
    validation_skip_reason: str | None
    final_score: int
    bucket_id: str
    bucket_label: str

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "base_concern_contribution": self.base_concern_contribution,
            "family_risk_contribution": self.family_risk_contribution,
            "lifestyle_contribution": self.lifestyle_contribution,
            "provisional_score": self.provisional_score,
            "validation_probed": self.validation_probed,
            "validation_contribution": self.validation_contribution,
            "validation_skip_reason": self.validation_skip_reason,
            "final_score": self.final_score,
            "bucket_id": self.bucket_id,
            "bucket_label": self.bucket_label,
        }


class ClusterConfidenceEngine:
    """How much evidence exists that an underlying physiological pattern is present?"""

    def __init__(self, catalog: DirectiveCatalog | None = None) -> None:
        self.catalog = catalog or load_directive()

    def base_concern_contribution(self, final_scores: list[int]) -> int:
        if not final_scores:
            return 0
        config = self.catalog.cluster_conf["base_concern"]
        peak_weight = config["highest_concern_weight"]
        average_weight = config["average_concern_weight"]
        scale = config["scale"]
        highest = max(final_scores)
        average = sum(final_scores) / len(final_scores)
        weighted = (peak_weight * highest) + (average_weight * average)
        return round(weighted * scale)

    def validation_contribution(
        self,
        probed: bool,
        positive_answers: int,
        questions_asked: int,
    ) -> int:
        if not probed or questions_asked <= 0:
            return 0
        max_value = self.catalog.cluster_conf["validation"]["max"]
        return min(
            round((positive_answers / questions_asked) * max_value),
            max_value,
        )

    def compute(
        self, confidence_input: ClusterConfidenceInput
    ) -> ClusterConfidenceResult:
        base = self.base_concern_contribution(
            confidence_input.participating_concern_final_scores
        )
        family = min(
            confidence_input.family_risk_contribution,
            self.catalog.cluster_conf["component_max"]["family_risk"],
        )
        lifestyle = min(
            self.catalog.lifestyle_score(confidence_input.lifestyle_signal_count),
            self.catalog.cluster_conf["component_max"]["lifestyle"],
        )
        provisional = min(
            base + family + lifestyle,
            self.catalog.cluster_conf["component_max"]["provisional"],
        )
        validation = self.validation_contribution(
            confidence_input.validation_probed,
            confidence_input.validation_positive_answers,
            confidence_input.validation_questions_asked,
        )
        final = min(
            provisional + validation,
            self.catalog.cluster_conf["component_max"]["final"],
        )
        bucket_id, bucket_label = self.catalog.bucket_for_score(final, "cluster_bucket")
        return ClusterConfidenceResult(
            cluster_id=confidence_input.cluster_id,
            base_concern_contribution=base,
            family_risk_contribution=family,
            lifestyle_contribution=lifestyle,
            provisional_score=provisional,
            validation_probed=confidence_input.validation_probed,
            validation_contribution=validation,
            validation_skip_reason=confidence_input.validation_skip_reason,
            final_score=final,
            bucket_id=bucket_id,
            bucket_label=bucket_label,
        )

    def probe_action(self, provisional_score: int) -> str:
        for gate in self.catalog.data["cluster_probe_config"]["eligibility"]:
            if (
                "provisional_score_gte" in gate
                and provisional_score >= gate["provisional_score_gte"]
            ):
                return gate["action"]
            if (
                "provisional_score_min" in gate
                and "provisional_score_max" in gate
                and gate["provisional_score_min"]
                <= provisional_score
                <= gate["provisional_score_max"]
            ):
                return gate["action"]
            if (
                "provisional_score_lt" in gate
                and provisional_score < gate["provisional_score_lt"]
            ):
                return gate["action"]
        return "skip"

    def select_clusters_for_probe(
        self,
        provisional_scores: dict[str, int],
    ) -> list[str]:
        max_clusters = self.catalog.data["cluster_probe_config"]["max_clusters"]
        ranked = sorted(
            provisional_scores.items(), key=lambda item: item[1], reverse=True
        )
        selected: list[str] = []
        for cluster_id, score in ranked:
            if len(selected) >= max_clusters:
                break
            if self.probe_action(score) == "probe":
                selected.append(cluster_id)
        return selected
