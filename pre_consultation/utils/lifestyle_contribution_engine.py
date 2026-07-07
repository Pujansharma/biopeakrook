"""Lifestyle Contribution Engine — Layer 6 lifestyle answers -> per-cluster contribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pre_consultation.utils.engine_directive import DirectiveCatalog, load_directive


@dataclass
class ClusterLifestyleResult:
    cluster_id: str
    cluster_label: str
    lifestyle_signal_count: int
    lifestyle_signals_triggered: list[str]
    lifestyle_contribution: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "cluster_label": self.cluster_label,
            "lifestyle_signal_count": self.lifestyle_signal_count,
            "lifestyle_signals_triggered": self.lifestyle_signals_triggered,
            "lifestyle_contribution": self.lifestyle_contribution,
        }


@dataclass
class LifestyleContributionEngine:
    catalog: DirectiveCatalog

    _signals: list[dict[str, Any]] = field(default_factory=list, init=False)
    _signal_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _dedup_rules: list[dict[str, Any]] = field(default_factory=list, init=False)
    _cluster_map: dict[str, list[str]] = field(default_factory=dict, init=False)
    _cluster_label: dict[str, str] = field(default_factory=dict, init=False)
    _contribution_lookup: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        data = self.catalog.data
        self._signals = data["lifestyle_signal"]
        self._signal_by_id = {signal["id"]: signal for signal in self._signals}
        self._dedup_rules = data["lifestyle_dedup_rule"]
        self._cluster_map = {
            cluster_row["cluster_id"]: list(cluster_row["eligible_signal_id"])
            for cluster_row in data["lifestyle_cluster_map"]
        }
        self._cluster_label = {
            cluster_row["id"]: cluster_row["label"] for cluster_row in data["cluster"]
        }
        self._contribution_lookup = data["lifestyle_contribution"]

    @classmethod
    def from_catalog(
        cls,
        catalog: DirectiveCatalog | None = None,
    ) -> LifestyleContributionEngine:
        return cls(catalog=catalog or load_directive())

    def triggered_signals(self, answers: dict[str, str]) -> list[str]:
        triggered: list[str] = []
        for signal in self._signals:
            value = answers.get(signal["field_id"])
            if value is None:
                continue
            if value in signal["trigger_values"]:
                triggered.append(signal["id"])
        return triggered

    def _dedup(self, signal_ids: list[str]) -> list[str]:
        kept = list(signal_ids)

        for rule in self._dedup_rules:
            groups = set(rule["groups"])
            in_scope = [
                signal_id
                for signal_id in kept
                if self._signal_by_id[signal_id]["group"] in groups
            ]
            if not in_scope:
                continue

            winners: set[str] = set()
            if "max_per_group" in rule:
                cap = rule["max_per_group"]
                for group_id in rule["groups"]:
                    group_signals = [
                        signal_id
                        for signal_id in in_scope
                        if self._signal_by_id[signal_id]["group"] == group_id
                    ]
                    winners.update(self._apply_preference(group_signals, rule)[:cap])
            else:
                cap = rule.get("max", 1)
                winners.update(self._apply_preference(in_scope, rule)[:cap])

            scope_set = set(in_scope)
            kept = [
                signal_id
                for signal_id in kept
                if signal_id not in scope_set or signal_id in winners
            ]

        return kept

    def _apply_preference(
        self,
        signal_ids: list[str],
        rule: dict[str, Any],
    ) -> list[str]:
        prefer = rule.get("prefer", [])
        order = {signal_id: index for index, signal_id in enumerate(prefer)}
        return sorted(
            signal_ids, key=lambda signal_id: order.get(signal_id, len(prefer))
        )

    def _count_to_contribution(self, count: int) -> int:
        best = 0
        for row in self._contribution_lookup:
            if "supporting_signal_count_min" in row:
                if count >= row["supporting_signal_count_min"]:
                    best = max(best, int(row["score"]))
            elif row["supporting_signal_count"] == count:
                best = max(best, int(row["score"]))
        return best

    def evaluate_cluster(
        self,
        cluster_id: str,
        triggered: list[str],
    ) -> ClusterLifestyleResult:
        eligible = self._cluster_map.get(cluster_id, [])
        in_cluster = [signal_id for signal_id in triggered if signal_id in eligible]
        deduped = self._dedup(in_cluster)
        count = len(deduped)
        contribution = self._count_to_contribution(count)
        return ClusterLifestyleResult(
            cluster_id=cluster_id,
            cluster_label=self._cluster_label.get(cluster_id, cluster_id),
            lifestyle_signal_count=count,
            lifestyle_signals_triggered=deduped,
            lifestyle_contribution=contribution,
        )

    def evaluate(self, answers: dict[str, str]) -> dict[str, ClusterLifestyleResult]:
        triggered = self.triggered_signals(answers)
        return {
            cluster_id: self.evaluate_cluster(cluster_id, triggered)
            for cluster_id in self._cluster_map
        }
