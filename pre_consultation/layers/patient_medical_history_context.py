"""Layer 7 — diagnoses, allergies, medications, sexual health, and report uploads."""

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from pre_consultation.customer_profile import resolve_customer_profile_for_request
from pre_consultation.gender_mapping import (
    baseline_gender_supports_sex_gated_content,
    profile_gender_to_baseline_gender,
)
from pre_consultation.models import (
    PreConsultationAllergy,
    PreConsultationDiagnosis,
    PreConsultationMedicalHistory,
    PreConsultationMedicalReport,
    PreConsultationMedication,
    PreConsultationSession,
    PreConsultationSexualHealthAnswer,
    PreConsultationSurgery,
)
from pre_consultation.persistence import get_or_create_medical_history
from pre_consultation.layers.patient_concern_probe import (
    update_concern_probe_scores_for_session,
)
from pre_consultation.utils.constants import (
    PreConsultationLayerProgression,
    PreConsultationMedicationStatus,
)
from pre_consultation.utils.medical_report import (
    MEDICAL_REPORT_MAX_COUNT,
    sanitize_medical_report_filename,
    validate_medical_report_upload,
)
from pre_consultation.utils.directive import (
    get_directive_diagnoses,
    get_directive_reproductive_diagnoses_for_gender,
    get_directive_sexual_health_questions_for_gender,
    get_valid_diagnosis_ids,
    get_valid_reproductive_diagnosis_ids_for_gender,
    get_valid_sexual_health_option_ids_for_gender,
)

EMPTY_PATIENT_MEDICAL_HISTORY_CONTEXT_PAYLOAD = {
    "diagnosis": [],
    "reproductive_diagnosis": [],
    "allergies": [],
    "surgeries": [],
    "medication_status": "",
    "medication": [],
    "sexual_health_question": [],
    "medical_reports": [],
}


class PatientMedicalHistoryContextMedicationRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    dosage = serializers.CharField(max_length=100)
    frequency = serializers.CharField(max_length=100)
    duration = serializers.CharField(max_length=100)


class PatientMedicalHistoryContextSurgeryRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    performed_when = serializers.CharField(max_length=100)
    reason = serializers.CharField(max_length=255)


class PatientMedicalHistoryContextSexualHealthAnswerRequestSerializer(
    serializers.Serializer
):
    id = serializers.CharField()
    option_id = serializers.CharField()


class PatientMedicalHistoryContextMedicalReportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, uploaded_file):
        try:
            validate_medical_report_upload(
                uploaded_file.name,
                uploaded_file.content_type or "",
                uploaded_file.size,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return uploaded_file


class PatientMedicalHistoryContextRequestSerializer(serializers.Serializer):
    selected_diagnosis_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )
    reproductive_diagnosis_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )
    allergies = serializers.ListField(
        child=serializers.CharField(max_length=255),
        allow_empty=True,
    )
    medication_status = serializers.ChoiceField(
        choices=PreConsultationMedicationStatus.choices,
        allow_blank=True,
    )

    def validate_medication_status(self, value: str) -> str:
        return normalize_medication_status(value)

    medications = PatientMedicalHistoryContextMedicationRequestSerializer(
        many=True,
        required=False,
        default=list,
    )
    surgeries = PatientMedicalHistoryContextSurgeryRequestSerializer(
        many=True,
        allow_empty=True,
    )
    sexual_health_question = (
        PatientMedicalHistoryContextSexualHealthAnswerRequestSerializer(
            many=True,
            allow_empty=True,
        )
    )
    medical_report_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        allow_empty=True,
    )

    def validate_medical_report_ids(self, value: list) -> list:
        report_ids = [str(report_id) for report_id in value]
        if len(report_ids) != len(set(report_ids)):
            raise serializers.ValidationError(
                "Duplicate medical report ids are not allowed."
            )
        if len(report_ids) > MEDICAL_REPORT_MAX_COUNT:
            raise serializers.ValidationError(
                f"A maximum of {MEDICAL_REPORT_MAX_COUNT} medical reports is allowed."
            )

        session = self.context["session"]
        medical_history = PreConsultationMedicalHistory.objects.filter(
            session=session,
        ).first()
        if not report_ids:
            return report_ids
        if medical_history is None:
            raise serializers.ValidationError("Invalid medical report ids.")

        existing_report_ids = {
            str(report_id)
            for report_id in medical_history.medical_reports.values_list(
                "pk",
                flat=True,
            )
        }
        invalid_report_ids = set(report_ids) - existing_report_ids
        if invalid_report_ids:
            invalid_list = ", ".join(sorted(invalid_report_ids))
            raise serializers.ValidationError(
                f"Invalid medical report ids: {invalid_list}"
            )
        return report_ids

    def validate_selected_diagnosis_ids(self, value: list[str]) -> list[str]:
        return validate_unique_ids(value, get_valid_diagnosis_ids(), "diagnosis")

    def validate_reproductive_diagnosis_ids(self, value: list[str]) -> list[str]:
        gender = self.context["gender"]
        if not baseline_gender_supports_sex_gated_content(gender):
            if value:
                raise serializers.ValidationError(
                    "Reproductive diagnoses are not applicable for this gender."
                )
            return value
        return validate_unique_ids(
            value,
            get_valid_reproductive_diagnosis_ids_for_gender(gender),
            "reproductive diagnosis",
        )

    def validate(self, attrs: dict) -> dict:
        selected_diagnosis_ids = attrs["selected_diagnosis_ids"]
        if "none" in selected_diagnosis_ids and len(selected_diagnosis_ids) > 1:
            raise serializers.ValidationError(
                {
                    "selected_diagnosis_ids": (
                        "'none' cannot be combined with other diagnoses."
                    )
                }
            )

        medication_status = attrs["medication_status"]
        medications = attrs.get("medications", [])
        if medication_status == PreConsultationMedicationStatus.NO and medications:
            raise serializers.ValidationError(
                {
                    "medications": (
                        "Medications must be empty when medication_status is 'no'."
                    )
                }
            )
        if medication_status != PreConsultationMedicationStatus.NO and not medications:
            raise serializers.ValidationError(
                {"medications": "At least one medication entry is required."}
            )

        gender = self.context["gender"]
        age_years = self.context.get("age_years")
        sexual_health_question = attrs.get("sexual_health_question", [])
        if not baseline_gender_supports_sex_gated_content(gender):
            if sexual_health_question:
                raise serializers.ValidationError(
                    {
                        "sexual_health_question": (
                            "Sexual health questions are not applicable for this gender."
                        )
                    }
                )
        else:
            validate_sexual_health_answers(
                sexual_health_question,
                gender,
                age_years,
            )

        return attrs


class PatientMedicalHistoryContextMedicationResponseSerializer(serializers.Serializer):
    name = serializers.CharField()
    dosage = serializers.CharField()
    frequency = serializers.CharField()
    duration = serializers.CharField()


class PatientMedicalHistoryContextSurgeryResponseSerializer(serializers.Serializer):
    name = serializers.CharField()
    performed_when = serializers.CharField()
    reason = serializers.CharField()


class PatientMedicalHistoryContextDiagnosisResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    selected = serializers.BooleanField()


class PatientMedicalHistoryContextSexualHealthOptionResponseSerializer(
    serializers.Serializer
):
    id = serializers.CharField()
    label = serializers.CharField()
    selected = serializers.BooleanField()


class PatientMedicalHistoryContextSexualHealthQuestionResponseSerializer(
    serializers.Serializer
):
    id = serializers.CharField()
    label = serializers.CharField()
    options = PatientMedicalHistoryContextSexualHealthOptionResponseSerializer(
        many=True
    )


class PatientMedicalHistoryContextMedicalReportResponseSerializer(
    serializers.Serializer
):
    id = serializers.UUIDField()
    filename = serializers.CharField()
    content_type = serializers.CharField()
    size_bytes = serializers.IntegerField()
    url = serializers.CharField()
    uploaded_at = serializers.DateTimeField()


class PatientMedicalHistoryContextResponseSerializer(serializers.Serializer):
    diagnosis = PatientMedicalHistoryContextDiagnosisResponseSerializer(many=True)
    reproductive_diagnosis = PatientMedicalHistoryContextDiagnosisResponseSerializer(
        many=True
    )
    allergies = serializers.ListField(child=serializers.CharField())
    surgeries = PatientMedicalHistoryContextSurgeryResponseSerializer(many=True)
    medication_status = serializers.ChoiceField(
        choices=PreConsultationMedicationStatus.choices,
        allow_blank=True,
        allow_null=True,
        required=False,
    )
    medication = PatientMedicalHistoryContextMedicationResponseSerializer(many=True)
    sexual_health_question = (
        PatientMedicalHistoryContextSexualHealthQuestionResponseSerializer(many=True)
    )
    medical_reports = PatientMedicalHistoryContextMedicalReportResponseSerializer(
        many=True
    )


def normalize_medication_status(medication_status: str) -> str:
    if not medication_status or medication_status == PreConsultationMedicationStatus.NO:
        return PreConsultationMedicationStatus.NO
    return medication_status


def validate_unique_ids(
    submitted_ids: list[str],
    valid_ids: set[str],
    field_label: str,
) -> list[str]:
    submitted_id_set = set(submitted_ids)
    if len(submitted_ids) != len(submitted_id_set):
        raise serializers.ValidationError(
            f"Duplicate {field_label} ids are not allowed."
        )

    invalid_ids = submitted_id_set - valid_ids
    if invalid_ids:
        invalid_list = ", ".join(sorted(invalid_ids))
        raise serializers.ValidationError(f"Invalid ids: {invalid_list}")

    return submitted_ids


def validate_sexual_health_answers(
    sexual_health_answers: list[dict],
    gender: str,
    age_years: int | None = None,
) -> None:
    valid_option_ids_by_question_id = get_valid_sexual_health_option_ids_for_gender(
        gender,
        age_years,
    )
    submitted_question_ids = [
        sexual_health_answer["id"] for sexual_health_answer in sexual_health_answers
    ]
    submitted_question_id_set = set(submitted_question_ids)
    if len(submitted_question_ids) != len(submitted_question_id_set):
        raise serializers.ValidationError(
            {
                "sexual_health_question": (
                    "Duplicate sexual health question ids are not allowed."
                )
            }
        )

    invalid_question_ids = submitted_question_id_set - set(
        valid_option_ids_by_question_id
    )
    if invalid_question_ids:
        invalid_list = ", ".join(sorted(invalid_question_ids))
        raise serializers.ValidationError(
            {"sexual_health_question": f"Invalid question ids: {invalid_list}"}
        )

    for sexual_health_answer in sexual_health_answers:
        question_id = sexual_health_answer["id"]
        option_id = sexual_health_answer["option_id"]
        valid_option_ids = valid_option_ids_by_question_id[question_id]
        if option_id not in valid_option_ids:
            raise serializers.ValidationError(
                {
                    "sexual_health_question": (
                        f"Invalid option id '{option_id}' for question '{question_id}'."
                    )
                }
            )


def calculate_age_years(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def get_customer_profile_gender_and_age(
    customer_profile,
) -> tuple[str | None, int | None]:
    if customer_profile is None:
        return None, None
    if customer_profile.date_of_birth is None:
        return profile_gender_to_baseline_gender(customer_profile.gender), None
    age_years = calculate_age_years(customer_profile.date_of_birth)
    return profile_gender_to_baseline_gender(customer_profile.gender), age_years


def build_selected_option_map(
    sexual_health_answers: list[dict],
    gender: str | None,
) -> dict[str, str]:
    return {
        sexual_health_answer["id"]: sexual_health_answer["option_id"]
        for sexual_health_answer in sexual_health_answers
    }


def build_diagnosis_response(
    diagnosis_catalog: list[dict],
    selected_diagnosis_ids: set[str],
) -> list[dict]:
    return [
        {
            "id": diagnosis["id"],
            "label": diagnosis["label"],
            "selected": diagnosis["id"] in selected_diagnosis_ids,
        }
        for diagnosis in diagnosis_catalog
    ]


def build_sexual_health_question_response(
    gender: str,
    age_years: int | None,
    selected_option_map: dict[str, str],
) -> list[dict]:
    sexual_health_questions = []
    for question in get_directive_sexual_health_questions_for_gender(gender, age_years):
        selected_option_id = selected_option_map.get(question["id"])
        sexual_health_questions.append(
            {
                "id": question["id"],
                "label": question["label"],
                "options": [
                    {
                        "id": option["id"],
                        "label": option["label"],
                        "selected": option["id"] == selected_option_id,
                    }
                    for option in question["options"]
                ],
            }
        )
    return sexual_health_questions


def build_medical_report_response(
    medical_report: PreConsultationMedicalReport,
) -> dict:
    return {
        "id": medical_report.pk,
        "filename": medical_report.original_filename,
        "content_type": medical_report.content_type,
        "size_bytes": medical_report.file_size,
        "url": medical_report.file.url,
        "uploaded_at": medical_report.created_at,
    }


def build_medical_reports_response(
    medical_history: PreConsultationMedicalHistory | None,
) -> list[dict]:
    if medical_history is None:
        return []
    return [
        build_medical_report_response(medical_report)
        for medical_report in medical_history.medical_reports.order_by("created_at")
    ]


def load_medical_history_from_db(session: PreConsultationSession) -> dict:
    medical_history = PreConsultationMedicalHistory.objects.filter(
        session=session,
    ).first()
    if medical_history is None:
        return {
            "selected_diagnosis_ids": set(),
            "selected_reproductive_diagnosis_ids": set(),
            "allergies": [],
            "surgeries": [],
            "medication": [],
            "sexual_health_answers": [],
            "medication_status": "",
            "medical_report_ids": [],
            "medical_reports": [],
        }

    medical_reports = build_medical_reports_response(medical_history)
    return {
        "selected_diagnosis_ids": set(
            medical_history.diagnoses.filter(is_reproductive=False).values_list(
                "diagnosis_id",
                flat=True,
            )
        ),
        "selected_reproductive_diagnosis_ids": set(
            medical_history.diagnoses.filter(is_reproductive=True).values_list(
                "diagnosis_id",
                flat=True,
            )
        ),
        "allergies": list(medical_history.allergies.values_list("name", flat=True)),
        "surgeries": [
            {
                "name": surgery.name,
                "performed_when": surgery.performed_when,
                "reason": surgery.reason,
            }
            for surgery in medical_history.surgeries.order_by("created_at")
        ],
        "medication": [
            {
                "name": medication.name,
                "dosage": medication.dosage,
                "frequency": medication.frequency,
                "duration": medication.duration,
            }
            for medication in medical_history.medications.order_by("created_at")
        ],
        "sexual_health_answers": [
            {
                "id": answer.question_id,
                "option_id": answer.option_id,
            }
            for answer in medical_history.sexual_health_answers.order_by("created_at")
        ],
        "medication_status": medical_history.medication_status,
        "medical_report_ids": [str(report["id"]) for report in medical_reports],
        "medical_reports": medical_reports,
    }


def load_patient_medical_history_context_payload(
    user,
    session: PreConsultationSession,
    customer_profile=None,
) -> dict:
    gender, age_years = get_customer_profile_gender_and_age(customer_profile)
    if gender is None:
        return EMPTY_PATIENT_MEDICAL_HISTORY_CONTEXT_PAYLOAD

    stored = load_medical_history_from_db(session)
    if not baseline_gender_supports_sex_gated_content(gender):
        reproductive_diagnosis: list[dict] = []
        sexual_health_question: list[dict] = []
    else:
        selected_option_map = build_selected_option_map(
            stored["sexual_health_answers"],
            gender,
        )
        reproductive_diagnosis = build_diagnosis_response(
            get_directive_reproductive_diagnoses_for_gender(gender),
            stored["selected_reproductive_diagnosis_ids"],
        )
        sexual_health_question = build_sexual_health_question_response(
            gender,
            age_years,
            selected_option_map,
        )

    return {
        "diagnosis": build_diagnosis_response(
            get_directive_diagnoses(),
            stored["selected_diagnosis_ids"],
        ),
        "reproductive_diagnosis": reproductive_diagnosis,
        "allergies": stored["allergies"],
        "surgeries": stored["surgeries"],
        "medication_status": stored["medication_status"],
        "medication": stored["medication"],
        "sexual_health_question": sexual_health_question,
        "medical_reports": stored["medical_reports"],
    }


def build_patient_medical_history_put_context(session, request) -> dict:
    customer_profile = resolve_customer_profile_for_request(
        request.user,
        getattr(request, "customer_profile_id", None),
    )
    gender, age_years = get_customer_profile_gender_and_age(customer_profile)
    return {"gender": gender, "age_years": age_years, "session": session}


def sync_medical_reports(
    medical_history: PreConsultationMedicalHistory,
    medical_report_ids: list[str],
) -> None:
    reports_to_delete = medical_history.medical_reports.exclude(
        pk__in=medical_report_ids,
    )
    for medical_report in reports_to_delete:
        medical_report.delete()


def persist_medical_history_medical_report_upload(
    session: PreConsultationSession,
    uploaded_file,
) -> dict:
    medical_history = get_or_create_medical_history(session)
    if medical_history.medical_reports.count() >= MEDICAL_REPORT_MAX_COUNT:
        raise serializers.ValidationError(
            {
                "file": (
                    f"A maximum of {MEDICAL_REPORT_MAX_COUNT} medical reports is allowed."
                )
            }
        )

    original_filename = sanitize_medical_report_filename(uploaded_file.name)
    try:
        content_type = validate_medical_report_upload(
            uploaded_file.name,
            uploaded_file.content_type or "",
            uploaded_file.size,
        )
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"file": str(exc)}) from exc
    medical_report = PreConsultationMedicalReport(
        medical_history=medical_history,
        original_filename=original_filename,
        content_type=content_type,
        file_size=uploaded_file.size,
    )
    medical_report.file = uploaded_file
    medical_report.save()
    return build_medical_report_response(medical_report)


def persist_patient_medical_history_context_payload(
    user,
    session: PreConsultationSession,
    validated_data: dict,
    customer_profile=None,
) -> None:
    medical_history = get_or_create_medical_history(session)
    medication_status = normalize_medication_status(validated_data["medication_status"])
    medical_history.medication_status = medication_status
    medical_history.save(update_fields=["medication_status", "updated_at"])

    medical_history.diagnoses.all().delete()
    diagnosis_rows = [
        PreConsultationDiagnosis(
            medical_history=medical_history,
            diagnosis_id=diagnosis_id,
            is_reproductive=False,
        )
        for diagnosis_id in validated_data["selected_diagnosis_ids"]
    ]
    diagnosis_rows.extend(
        PreConsultationDiagnosis(
            medical_history=medical_history,
            diagnosis_id=diagnosis_id,
            is_reproductive=True,
        )
        for diagnosis_id in validated_data["reproductive_diagnosis_ids"]
    )
    PreConsultationDiagnosis.objects.bulk_create(diagnosis_rows)

    medical_history.allergies.all().delete()
    PreConsultationAllergy.objects.bulk_create(
        [
            PreConsultationAllergy(medical_history=medical_history, name=allergy)
            for allergy in validated_data["allergies"]
        ]
    )

    medical_history.surgeries.all().delete()
    PreConsultationSurgery.objects.bulk_create(
        [
            PreConsultationSurgery(
                medical_history=medical_history,
                name=surgery["name"],
                performed_when=surgery["performed_when"],
                reason=surgery["reason"],
            )
            for surgery in validated_data["surgeries"]
        ]
    )

    medication_entries = validated_data.get("medications", [])
    if medication_status == PreConsultationMedicationStatus.NO:
        medication_entries = []
    medical_history.medications.all().delete()
    PreConsultationMedication.objects.bulk_create(
        [
            PreConsultationMedication(
                medical_history=medical_history,
                name=medication["name"],
                dosage=medication["dosage"],
                frequency=medication["frequency"],
                duration=medication["duration"],
            )
            for medication in medication_entries
        ]
    )

    medical_history.sexual_health_answers.all().delete()
    PreConsultationSexualHealthAnswer.objects.bulk_create(
        [
            PreConsultationSexualHealthAnswer(
                medical_history=medical_history,
                question_id=answer["id"],
                option_id=answer["option_id"],
            )
            for answer in validated_data.get("sexual_health_question", [])
        ]
    )

    sync_medical_reports(
        medical_history,
        validated_data.get("medical_report_ids", []),
    )

    update_concern_probe_scores_for_session(session)

    session.current_layer = PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT
    session.updated_at = timezone.now()
    session.save(update_fields=["current_layer", "updated_at"])
