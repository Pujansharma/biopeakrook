"""Directive catalog and family risk scoring (shared by confidence engines)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DIRECTIVE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "pre_consultation_directive.json"
)


@dataclass(frozen=True)
class FamilyRelativeInput:
    relation_id: str
    age_band_id: str


class DirectiveCatalog:
    """Read-only view of pre_consultation_directive.json scoring tables."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self._weight_maps = {
            "concern_source": self._map_weights("concern_source"),
            "functional_impact": self._map_weights("functional_impact"),
            "duration_impact": self._map_weights("duration_impact"),
            "progression_impact": self._map_weights("progression_impact"),
        }
        self.concern_conf = data["concern_confidence"]
        self.cluster_conf = data["cluster_confidence"]
        self.family_relation_weight = {
            relation["id"]: relation["weight"] for relation in data["family_relation"]
        }
        self.age_band_weight = {
            age_band["id"]: age_band["weight"] for age_band in data["age_band"]
        }
        self.family_risk_levels = {
            row["id"]: row for row in data["family_risk_contribution"]
        }
        self.family_risk_level_score = {
            row["risk_level_id"]: row["score"]
            for row in data["cluster_confidence"]["family_risk_level_score"]
        }
        self.cluster_contribution_by_risk = {
            row["id"]: row["cluster_contribution_weight"]
            for row in data["family_risk_contribution"]
        }
        self.family_risk_cap = data["family_risk_contribution_cap"]
        self.lifestyle_contribution = data["lifestyle_contribution"]
        self.cluster_concern_map = {
            cluster["id"]: cluster["concern_id"] for cluster in data["cluster"]
        }
        self.concern_cluster_map = {
            concern["id"]: list(concern["cluster_id"]) for concern in data["concern"]
        }
        self.scoring_concern_source_ids = frozenset(self._weight_maps["concern_source"])

    def _map_weights(self, key: str) -> dict[str, int]:
        return {
            row["id"]: int(row["weight"]) for row in self.data[key] if "weight" in row
        }

    def weight(self, table: str, row_id: str | None) -> int:
        if not row_id:
            return 0
        return self._weight_maps[table].get(row_id, 0)

    def bucket_for_score(self, score: int, bucket_key: str) -> tuple[str, str]:
        for row in self.data[bucket_key]:
            if row["score_min"] <= score <= row["score_max"]:
                return row["id"], row["label"]
        last = self.data[bucket_key][-1]
        return last["id"], last["label"]

    def lifestyle_score(self, supporting_signal_count: int) -> int:
        best = 0
        for row in self.lifestyle_contribution:
            if "supporting_signal_count_min" in row:
                if supporting_signal_count >= row["supporting_signal_count_min"]:
                    best = max(best, int(row["score"]))
            elif row["supporting_signal_count"] == supporting_signal_count:
                best = max(best, int(row["score"]))
        return best


@lru_cache(maxsize=1)
def load_directive(path: Path = DIRECTIVE_PATH) -> DirectiveCatalog:
    return DirectiveCatalog(json.loads(path.read_text(encoding="utf-8")))


class FamilyRiskEngine:
    """Family burden -> risk level -> per-cluster contribution (cap from directive)."""

    def __init__(self, catalog: DirectiveCatalog | None = None) -> None:
        self.catalog = catalog or load_directive()

    def relative_contribution(self, relation_id: str, age_band_id: str) -> float:
        rel_w = self.catalog.family_relation_weight[relation_id]
        age_w = self.catalog.age_band_weight[age_band_id]
        return rel_w + age_w

    def concern_burden(self, relatives: list[FamilyRelativeInput]) -> float:
        return sum(
            self.relative_contribution(relative.relation_id, relative.age_band_id)
            for relative in relatives
        )

    def risk_level_id(self, burden: float) -> str:
        for level_id, row in self.catalog.family_risk_levels.items():
            if "burden_lt" in row and burden < row["burden_lt"]:
                return level_id
            if "burden_gte" in row and "burden_lte" in row:
                if row["burden_gte"] <= burden <= row["burden_lte"]:
                    return level_id
            if "burden_gt" in row and "burden_lte" in row:
                if row["burden_gt"] < burden <= row["burden_lte"]:
                    return level_id
            if "burden_gt" in row and "burden_lte" not in row:
                if burden > row["burden_gt"]:
                    return level_id
        return "very_high"

    def cluster_contribution_from_concern_burdens(
        self,
        concern_burdens: dict[str, float],
    ) -> dict[str, int]:
        """Sum cluster_contribution_weight per cluster (each concern's burden -> risk), capped."""
        totals: dict[str, int] = {}
        for concern_id, burden in concern_burdens.items():
            risk_id = self.risk_level_id(burden)
            weight = self.catalog.cluster_contribution_by_risk[risk_id]
            for cluster_id in self.catalog.concern_cluster_map.get(concern_id, []):
                totals[cluster_id] = totals.get(cluster_id, 0) + weight
        cap = self.catalog.family_risk_cap
        return {cluster_id: min(score, cap) for cluster_id, score in totals.items()}
