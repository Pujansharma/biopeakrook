"""Read-only accessors over pre_consultation_directive.json catalog data."""

import json
from pathlib import Path

DIRECTIVE_FILE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "pre_consultation_directive.json"
)


def get_directive_data() -> dict:
    with DIRECTIVE_FILE_PATH.open(encoding="utf-8") as directive_file:
        return json.load(directive_file)


def get_directive_schema_id() -> str:
    return get_directive_data()["schema_id"]


def get_directive_categories() -> list[dict]:
    directive_data = get_directive_data()
    return [
        {
            "id": category["id"],
            "label": category["label"],
            "hint": category["hint"],
            "icon": category["icon"],
            "icon-class": category["icon-class"],
        }
        for category in directive_data["category"]
    ]


def get_valid_category_ids() -> set[str]:
    return {category["id"] for category in get_directive_categories()}


def get_directive_concerns() -> list[dict]:
    directive_data = get_directive_data()
    return [
        {
            "id": concern["id"],
            "label": concern["label"],
            "category_id": concern["category_id"],
        }
        for concern in directive_data["concern"]
    ]


def get_valid_concern_ids() -> set[str]:
    return {concern["id"] for concern in get_directive_concerns()}


def get_concern_category_id_map() -> dict[str, str]:
    return {
        concern["id"]: concern["category_id"] for concern in get_directive_concerns()
    }


def get_directive_concerns_for_category(category_id: str) -> list[dict]:
    return [
        {"id": concern["id"], "label": concern["label"]}
        for concern in get_directive_concerns()
        if concern["category_id"] == category_id
    ]


def strip_directive_weight(directive_entry: dict) -> dict:
    return {
        field_name: field_value
        for field_name, field_value in directive_entry.items()
        if field_name != "weight"
    }


def get_directive_concern_sources() -> list[dict]:
    excluded_fields = {"weight", "effect"}
    return [
        {
            field_name: field_value
            for field_name, field_value in concern_source.items()
            if field_name not in excluded_fields
        }
        for concern_source in get_directive_data()["concern_source"]
    ]


def get_directive_age_bands() -> list[dict]:
    return [
        strip_directive_weight(age_band)
        for age_band in get_directive_data()["age_band"]
    ]


def get_directive_family_relations() -> list[dict]:
    return [
        strip_directive_weight(family_relation)
        for family_relation in get_directive_data()["family_relation"]
    ]


def get_valid_concern_source_ids() -> set[str]:
    return {concern_source["id"] for concern_source in get_directive_concern_sources()}


def get_valid_age_band_ids() -> set[str]:
    return {age_band["id"] for age_band in get_directive_age_bands()}


def get_valid_family_relation_ids() -> set[str]:
    return {
        family_relation["id"] for family_relation in get_directive_family_relations()
    }


def get_directive_symptoms() -> list[dict]:
    directive_data = get_directive_data()
    return [
        {
            "id": symptom["id"],
            "label": symptom["label"],
            "concern_id": symptom["concern_id"],
        }
        for symptom in directive_data["symptom"]
    ]


def get_directive_symptoms_for_concern(concern_id: str) -> list[dict]:
    return [
        {"id": symptom["id"], "label": symptom["label"]}
        for symptom in get_directive_symptoms()
        if symptom["concern_id"] == concern_id
    ]


def get_valid_symptom_ids_for_concern(concern_id: str) -> set[str]:
    return {symptom["id"] for symptom in get_directive_symptoms_for_concern(concern_id)}


def get_directive_concern_label_map() -> dict[str, str]:
    return {concern["id"]: concern["label"] for concern in get_directive_concerns()}


def get_directive_category_label_map() -> dict[str, str]:
    return {
        category["id"]: category["label"] for category in get_directive_categories()
    }


def get_directive_functional_impacts() -> list[dict]:
    return [
        strip_directive_weight(functional_impact)
        for functional_impact in get_directive_data()["functional_impact"]
    ]


def get_directive_duration_impacts() -> list[dict]:
    return [
        strip_directive_weight(duration_impact)
        for duration_impact in get_directive_data()["duration_impact"]
    ]


def get_directive_progression_impacts() -> list[dict]:
    return [
        strip_directive_weight(progression_impact)
        for progression_impact in get_directive_data()["progression_impact"]
    ]


def get_valid_functional_impact_ids() -> set[str]:
    return {
        functional_impact["id"]
        for functional_impact in get_directive_functional_impacts()
    }


def get_valid_duration_impact_ids() -> set[str]:
    return {
        duration_impact["id"] for duration_impact in get_directive_duration_impacts()
    }


def get_valid_progression_impact_ids() -> set[str]:
    return {
        progression_impact["id"]
        for progression_impact in get_directive_progression_impacts()
    }


def get_directive_clusters() -> list[dict]:
    directive_data = get_directive_data()
    return [
        {
            "id": cluster["id"],
            "label": cluster["label"],
            "icon": cluster["icon"],
            "icon-class": cluster["icon-class"],
        }
        for cluster in directive_data["cluster"]
    ]


def get_directive_cluster_label_map() -> dict[str, str]:
    return {cluster["id"]: cluster["label"] for cluster in get_directive_clusters()}


def get_directive_impact_label_map(impact_key: str) -> dict[str, str]:
    accessor_by_key = {
        "functional_impact": get_directive_functional_impacts,
        "duration_impact": get_directive_duration_impacts,
        "progression_impact": get_directive_progression_impacts,
    }
    return {
        impact_row["id"]: impact_row["label"]
        for impact_row in accessor_by_key[impact_key]()
    }


def get_directive_age_band_label_map() -> dict[str, str]:
    return {age_band["id"]: age_band["label"] for age_band in get_directive_age_bands()}


def get_directive_family_relation_label_map() -> dict[str, str]:
    return {
        family_relation["id"]: family_relation["label"]
        for family_relation in get_directive_family_relations()
    }


def get_directive_symptom_label_map() -> dict[str, str]:
    return {symptom["id"]: symptom["label"] for symptom in get_directive_symptoms()}


def get_directive_diagnosis_label_map() -> dict[str, str]:
    return {diagnosis["id"]: diagnosis["label"] for diagnosis in get_directive_diagnoses()}


def get_directive_concern_metadata_map() -> dict[str, dict]:
    return {
        concern["id"]: concern for concern in get_directive_data()["concern"]
    }


def get_directive_cluster_metadata_map() -> dict[str, dict]:
    return {cluster["id"]: cluster for cluster in get_directive_data()["cluster"]}


def get_directive_lifestyle_signal_label_map() -> dict[str, str]:
    lifestyle_field_label_by_id = {
        lifestyle_field["id"]: lifestyle_field["label"]
        for lifestyle_field in get_directive_lifestyle_fields()
    }
    signal_labels: dict[str, str] = {}
    for lifestyle_signal in get_directive_data()["lifestyle_signal"]:
        field_label = lifestyle_field_label_by_id.get(
            lifestyle_signal["field_id"],
            lifestyle_signal["field_id"],
        )
        signal_labels[lifestyle_signal["id"]] = field_label
    return signal_labels


def get_directive_cluster_display_map() -> dict[str, dict[str, str]]:
    return {
        cluster["id"]: {
            "label": cluster["label"],
            "icon": cluster["icon"],
            "icon-class": cluster["icon-class"],
        }
        for cluster in get_directive_clusters()
    }


def get_concern_cluster_ids_map() -> dict[str, list[str]]:
    directive_data = get_directive_data()
    return {
        concern["id"]: list(concern["cluster_id"])
        for concern in directive_data["concern"]
    }


def get_directive_cluster_probes_for_cluster(cluster_id: str) -> list[dict]:
    directive_data = get_directive_data()
    return [
        {"id": cluster_probe["id"], "label": cluster_probe["label"]}
        for cluster_probe in directive_data["cluster_probe"]
        if cluster_probe["cluster_id"] == cluster_id
    ]


def get_cluster_probe_ids_for_concern(concern_id: str) -> list[str]:
    cluster_probe_ids = []
    concern_cluster_ids_map = get_concern_cluster_ids_map()
    for cluster_id in concern_cluster_ids_map.get(concern_id, []):
        for cluster_probe in get_directive_cluster_probes_for_cluster(cluster_id):
            cluster_probe_ids.append(cluster_probe["id"])
    return cluster_probe_ids


def get_valid_cluster_probe_ids_for_concern(concern_id: str) -> set[str]:
    return set(get_cluster_probe_ids_for_concern(concern_id))


def get_directive_diagnoses() -> list[dict]:
    return [
        {"id": diagnosis["id"], "label": diagnosis["label"]}
        for diagnosis in get_directive_data()["diagnosis"]
    ]


def get_valid_diagnosis_ids() -> set[str]:
    return {diagnosis["id"] for diagnosis in get_directive_diagnoses()}


def get_diagnosis_override_concern_ids_by_diagnosis_id() -> dict[str, list[str]]:
    override_concern_ids_by_diagnosis_id: dict[str, list[str]] = {}
    for diagnosis in get_directive_data()["diagnosis"]:
        concern_ids = diagnosis.get("concern_id")
        if concern_ids:
            override_concern_ids_by_diagnosis_id[diagnosis["id"]] = list(concern_ids)
    return override_concern_ids_by_diagnosis_id


def get_directive_reproductive_diagnoses_for_gender(gender: str) -> list[dict]:
    return [
        {"id": reproductive_diagnosis["id"], "label": reproductive_diagnosis["label"]}
        for reproductive_diagnosis in get_directive_data()["reproductive_diagnosis"]
        if reproductive_diagnosis.get("sex_gate") == gender
    ]


def get_valid_reproductive_diagnosis_ids_for_gender(gender: str) -> set[str]:
    return {
        reproductive_diagnosis["id"]
        for reproductive_diagnosis in get_directive_reproductive_diagnoses_for_gender(
            gender
        )
    }


def get_sexual_health_group_for_gender(gender: str) -> dict | None:
    for sexual_health_group in get_directive_data()["sexual_health"]:
        if sexual_health_group.get("sex_gate") == gender:
            return sexual_health_group
    return None


def get_directive_sexual_health_questions_for_gender(
    gender: str,
    age_years: int | None = None,
) -> list[dict]:
    sexual_health_group = get_sexual_health_group_for_gender(gender)
    if sexual_health_group is None:
        return []

    sexual_health_questions = []
    for question in sexual_health_group["question"]:
        question_age_min = question.get("age_min")
        if question_age_min is not None and age_years is not None:
            if age_years < question_age_min:
                continue

        if "option" not in question:
            continue

        question_payload = {
            "id": question["id"],
            "label": question["label"],
            "options": [
                {"id": option["id"], "label": option["label"]}
                for option in question["option"]
            ],
        }
        if question.get("type") == "number":
            question_payload["type"] = "number"
        sexual_health_questions.append(question_payload)

    return sexual_health_questions


def get_pregnancy_question_id_for_gender(gender: str) -> str | None:
    for question in get_directive_sexual_health_questions_for_gender(gender):
        if question.get("type") == "number":
            return question["id"]
    return None


def is_number_type_sexual_health_question_id(
    gender: str,
    question_id: str,
    age_years: int | None = None,
) -> bool:
    for question in get_directive_sexual_health_questions_for_gender(gender, age_years):
        if question["id"] == question_id:
            return question.get("type") == "number"
    return False


def get_valid_sexual_health_option_ids_for_gender(
    gender: str,
    age_years: int | None = None,
) -> dict[str, set[str]]:
    option_ids_by_question_id = {}
    for question in get_directive_sexual_health_questions_for_gender(gender, age_years):
        option_ids_by_question_id[question["id"]] = {
            option["id"] for option in question["options"]
        }
    return option_ids_by_question_id


def get_valid_pregnancy_option_ids(gender: str) -> set[str]:
    pregnancy_question_id = get_pregnancy_question_id_for_gender(gender)
    if pregnancy_question_id is None:
        return set()
    option_ids_by_question_id = get_valid_sexual_health_option_ids_for_gender(gender)
    return option_ids_by_question_id.get(pregnancy_question_id, set())


def get_directive_lifestyle_fields() -> list[dict]:
    return [
        {
            "id": lifestyle_field["id"],
            "label": lifestyle_field["label"],
            "options": [
                {"value": option["value"], "label": option["label"]}
                for option in lifestyle_field["option"]
            ],
        }
        for lifestyle_field in get_directive_data()["lifestyle_field"]
    ]


def get_valid_lifestyle_field_ids() -> set[str]:
    return {
        lifestyle_field["id"] for lifestyle_field in get_directive_lifestyle_fields()
    }


def get_valid_lifestyle_option_values_by_field_id() -> dict[str, set[str]]:
    return {
        lifestyle_field["id"]: {
            option["value"] for option in lifestyle_field["options"]
        }
        for lifestyle_field in get_directive_lifestyle_fields()
    }


def get_directive_health_goals() -> list[dict]:
    return [
        {"id": health_goal["id"], "label": health_goal["label"]}
        for health_goal in get_directive_data()["health_goals"]
    ]


def get_health_goal_count() -> int:
    return int(get_directive_data()["max_health_goals"])


def get_valid_health_goal_ids() -> set[str]:
    return {health_goal["id"] for health_goal in get_directive_health_goals()}
