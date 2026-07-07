"""Staff-facing pre-consultation result endpoints keyed by customer user_id."""

from drf_spectacular.utils import extend_schema, extend_schema_view
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.utils.view_types import GetMethodMixin, PatchMethodMixin, PostMethodMixin
from core.utils.views import BaseGenericAPIView
from pre_consultation.models import (
    PreConsultationPreparationChecklistItem,
    PreConsultationSessionNote,
)
from pre_consultation.result_builders import (
    build_clusters_payload,
    build_context_payload,
    build_family_risk_payload,
    build_health_map_payload,
    build_lifestyle_payload,
    build_medical_context_payload,
    build_notes_payload,
    build_overview_payload,
    build_raw_data_payload,
    serialize_checklist_item,
)
from pre_consultation.result_serializers import (
    PreConsultationChecklistItemPatchSerializer,
    PreConsultationSessionNoteCreateSerializer,
)
from pre_consultation.result_session import get_result_session_context
from pre_consultation.utils.api import pre_consultation_response
from pre_consultation.utils.schema import PRE_CONSULTATION_RESULT_TAG


class PreConsultationResultBaseView(BaseGenericAPIView):
    permission_classes = [IsAuthenticated]

    def load_context(self, user_id: str):
        return get_result_session_context(user_id)


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Overview summary, checklist, and patient goals for a user session.",
    ),
)
class PreConsultationResultOverviewView(PreConsultationResultBaseView, GetMethodMixin):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_overview_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Clinical context: quick summary, top concerns/clusters, medications, diagnoses.",
    ),
)
class PreConsultationResultContextView(PreConsultationResultBaseView, GetMethodMixin):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_context_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Family risk relations, counts, summary, and cluster contributions.",
    ),
)
class PreConsultationResultFamilyRiskView(PreConsultationResultBaseView, GetMethodMixin):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_family_risk_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Health map concerns sorted by confidence score.",
    ),
)
class PreConsultationResultHealthMapView(PreConsultationResultBaseView, GetMethodMixin):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_health_map_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Non-zero health clusters with evidence, diagnoses, and probes.",
    ),
)
class PreConsultationResultClustersView(PreConsultationResultBaseView, GetMethodMixin):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_clusters_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Lifestyle answers with mapped concerns and clusters.",
    ),
)
class PreConsultationResultLifestyleView(PreConsultationResultBaseView, GetMethodMixin):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_lifestyle_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Medical context: diagnoses, medications, supplements, surgeries.",
    ),
)
class PreConsultationResultMedicalContextView(
    PreConsultationResultBaseView,
    GetMethodMixin,
):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_medical_context_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Raw layer answers for audit and downstream tooling.",
    ),
)
class PreConsultationResultRawDataView(PreConsultationResultBaseView, GetMethodMixin):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_raw_data_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="List associate notes for the user's pre-consultation session.",
    ),
    post=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Create an associate note on the user's pre-consultation session.",
        request=PreConsultationSessionNoteCreateSerializer,
    ),
)
class PreConsultationResultNotesView(
    PreConsultationResultBaseView,
    GetMethodMixin,
    PostMethodMixin,
):
    serializer_class = PreConsultationSessionNoteCreateSerializer

    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_notes_payload(context),
            status_code=status.HTTP_200_OK,
        )

    def post(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = PreConsultationSessionNote.objects.create(
            session=context.session,
            note=serializer.validated_data["note"],
            category=serializer.validated_data["category"],
        )
        return pre_consultation_response(
            success=True,
            data={
                "note": note.note,
                "category": note.category,
                "created_at": note.created_at,
            },
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    patch=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Toggle a preparation checklist item done state.",
        request=PreConsultationChecklistItemPatchSerializer,
    ),
)
class PreConsultationResultChecklistItemView(
    PreConsultationResultBaseView,
    PatchMethodMixin,
):
    serializer_class = PreConsultationChecklistItemPatchSerializer

    def patch(self, request, user_id, item_id, *args, **kwargs):
        context = self.load_context(user_id)
        checklist_item = get_object_or_404(
            PreConsultationPreparationChecklistItem,
            pk=item_id,
            session=context.session,
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        checklist_item.marked = serializer.validated_data["done"]
        checklist_item.save(update_fields=["marked", "updated_at"])
        return pre_consultation_response(
            success=True,
            data=serialize_checklist_item(checklist_item),
            status_code=status.HTTP_200_OK,
        )
