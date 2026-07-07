"""Concern Confidence Engine — per-concern attention score from sources and probes."""

from __future__ import annotations

from dataclasses import dataclass

from pre_consultation.utils.engine_directive import DirectiveCatalog, load_directive


@dataclass
class ConcernConfidenceInput:
    """Inputs for a single concern deep-dive score."""

    concern_id: str
    concern_source_ids: list[str]
    functional_impact_id: str | None = None
    duration_impact_id: str | None = None
    progression_impact_id: str | None = None
    medical_override: bool = False


@dataclass
class ConcernConfidenceResult:
    """Concern confidence engine output."""

    concern_id: str
    signal_score: int
    impact_score: int
    duration_score: int
    progression_score: int
    raw_score: int
    medical_override: bool
    final_score: int
    bucket_id: str
    bucket_label: str


class ConcernConfidenceEngine:
    """How strongly should the doctor pay attention to this concern?"""

    def __init__(self, catalog: DirectiveCatalog | None = None) -> None:
        self.catalog = catalog or load_directive()

    def signal_score(self, concern_source_ids: list[str]) -> int:
        scoring_ids = [
            source_id
            for source_id in concern_source_ids
            if source_id in self.catalog.scoring_concern_source_ids
        ]
        if not scoring_ids:
            return 0
        bases = sorted(
            (
                self.catalog.weight("concern_source", source_id)
                for source_id in scoring_ids
            ),
            reverse=True,
        )
        bonus = self.catalog.concern_conf["concern_source_multi_select"][
            "additional_source_bonus"
        ]
        cap = self.catalog.concern_conf["concern_source_multi_select"]["cap"]
        extra = max(0, len(bases) - 1) * bonus
        return min(bases[0] + extra, cap)

    def compute(
        self, confidence_input: ConcernConfidenceInput
    ) -> ConcernConfidenceResult:
        signal = self.signal_score(confidence_input.concern_source_ids)
        impact = self.catalog.weight(
            "functional_impact", confidence_input.functional_impact_id
        )
        duration = self.catalog.weight(
            "duration_impact", confidence_input.duration_impact_id
        )
        progression = self.catalog.weight(
            "progression_impact",
            confidence_input.progression_impact_id,
        )
        raw = signal + impact + duration + progression
        floor = self.catalog.concern_conf["medical_override_floor"]
        overridden = bool(confidence_input.medical_override)
        final = max(raw, floor) if overridden else raw
        bucket_id, bucket_label = self.catalog.bucket_for_score(final, "concern_bucket")
        return ConcernConfidenceResult(
            concern_id=confidence_input.concern_id,
            signal_score=signal,
            impact_score=impact,
            duration_score=duration,
            progression_score=progression,
            raw_score=raw,
            medical_override=overridden,
            final_score=final,
            bucket_id=bucket_id,
            bucket_label=bucket_label,
        )
