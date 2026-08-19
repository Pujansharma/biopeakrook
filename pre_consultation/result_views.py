"""Staff-facing pre-consultation result endpoints keyed by customer user_id."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.pagination import BasePageNumberPagination
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
    build_medical_reports_payload,
    build_notes_payload,
    build_overview_payload,
    build_raw_data_payload,
    build_surgery_payload,
    get_session_list_queryset,
    serialize_checklist_item,
    serialize_session_list_item,
)
from pre_consultation.result_serializers import (
    PreConsultationChecklistItemPatchSerializer,
    PreConsultationSessionListItemSerializer,
    PreConsultationSessionNoteCreateSerializer,
)
from pre_consultation.result_session import get_result_session_context
from pre_consultation.utils.api import pre_consultation_paginated_response, pre_consultation_response
from pre_consultation.utils.schema import (
    PRE_CONSULTATION_RESULT_TAG,
    RESULT_LIST_CENTER_HEADER,
    RESULT_LIST_LIMIT_PARAM,
    RESULT_LIST_PAGE_PARAM,
    RESULT_LIST_SEARCH_PARAM,
)


class PreConsultationResultBaseView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]

    def load_context(self, user_id: str):
        return get_result_session_context(user_id)


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description=(
            "Paginated list of all pre-consultation sessions with customer profile "
            "fields for staff result workflows."
        ),
        parameters=[
            RESULT_LIST_CENTER_HEADER,
            RESULT_LIST_SEARCH_PARAM,
            RESULT_LIST_PAGE_PARAM,
            RESULT_LIST_LIMIT_PARAM,
        ],
        responses={200: PreConsultationSessionListItemSerializer(many=True)},
    ),
)
class PreConsultationSessionListView(PreConsultationResultBaseView, GetMethodMixin):
    pagination_class = BasePageNumberPagination

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        center_id = self.request.center_id
        return get_session_list_queryset(search, center_id=center_id)

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is None:
            results = [serialize_session_list_item(session) for session in queryset]
            return pre_consultation_paginated_response(
                success=True,
                status_code=status.HTTP_200_OK,
                count=len(results),
                next_link=None,
                previous_link=None,
                results=results,
            )

        results = [serialize_session_list_item(session) for session in page]
        return pre_consultation_paginated_response(
            success=True,
            status_code=status.HTTP_200_OK,
            count=self.paginator.page.paginator.count,
            next_link=self.paginator.get_next_link(),
            previous_link=self.paginator.get_previous_link(),
            results=results,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description="Overview summary, checklist, and ranked health goals for a user session.",
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
        description="Surgery history with name, performed_when, and reason.",
    ),
)
class PreConsultationResultSurgeryView(PreConsultationResultBaseView, GetMethodMixin):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_surgery_payload(context),
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_RESULT_TAG],
        description=(
            "Uploaded medical reports with download URL and generated summary metadata."
        ),
    ),
)
class PreConsultationResultMedicalReportsView(
    PreConsultationResultBaseView,
    GetMethodMixin,
):
    def get(self, request, user_id, *args, **kwargs):
        context = self.load_context(user_id)
        return pre_consultation_response(
            success=True,
            data=build_medical_reports_payload(context),
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
