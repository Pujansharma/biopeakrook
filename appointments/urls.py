from django.urls import path

from appointments import views

urlpatterns = [
    path("", views.CenterAvailabilityCalendarView.as_view()),
    path(
        "associates/<uuid:associate_id>/roster/",
        views.AssociateRosterBulkUpsertView.as_view(),
    ),
    path(
        "associates/<uuid:associate_id>/google-calendar/",
        views.AssociateGoogleCalendarStatusView.as_view(),
    ),
    path(
        "associates/<uuid:associate_id>/google-calendar/sync/",
        views.AssociateGoogleCalendarSyncView.as_view(),
    ),
    path(
        "associates/<uuid:associate_id>/blocks/",
        views.AssociateAvailabilityBlockListCreateView.as_view(),
    ),
    path(
        "associates/<uuid:associate_id>/blocks/<uuid:pk>/",
        views.AssociateAvailabilityBlockDetailView.as_view(),
    ),
    path(
        "associates/<uuid:associate_id>/leaves/",
        views.AssociateLeaveListCreateView.as_view(),
    ),
    path(
        "associates/<uuid:associate_id>/leaves/<uuid:pk>/",
        views.AssociateLeaveDetailView.as_view(),
    ),
    path(
        "associates/<uuid:associate_id>/",
        views.AssociateCenterAvailabilityCalendarView.as_view(),
    ),
    path(
        "care-teams/<uuid:care_team_id>/blocks/",
        views.CareTeamAvailabilityBlockListCreateView.as_view(),
    ),
    path(
        "care-teams/<uuid:care_team_id>/blocks/<uuid:pk>/",
        views.CareTeamAvailabilityBlockDetailView.as_view(),
    ),
    path(
        "care-teams/<uuid:care_team_id>/",
        views.CareTeamAvailabilityCalendarView.as_view(),
    ),
    path(
        "rooms/<uuid:room_id>/",
        views.RoomAvailabilityCalendarView.as_view(),
    ),
    path(
        "equipment/<uuid:equipment_id>/",
        views.EquipmentAvailabilityCalendarView.as_view(),
    ),
    path("operating-hours/", views.CenterAvailabilityOperatingHoursView.as_view()),
    path("closures/", views.CenterClosureListCreateView.as_view()),
    path("closures/<uuid:pk>/", views.CenterClosureDetailView.as_view()),
    path("associate-roster/", views.AssociateRosterEntryListView.as_view()),
    path(
        "room-blocks/<uuid:room_id>/",
        views.RoomAvailabilityBlockListCreateView.as_view(),
    ),
    path(
        "room-blocks/<uuid:room_id>/<uuid:pk>/",
        views.RoomAvailabilityBlockDetailView.as_view(),
    ),
    path(
        "room-downtimes/<uuid:room_id>/",
        views.RoomDowntimeListCreateView.as_view(),
    ),
    path(
        "room-downtimes/<uuid:room_id>/<uuid:pk>/",
        views.RoomDowntimeDetailView.as_view(),
    ),
    path(
        "equipment-blocks/<uuid:equipment_id>/",
        views.EquipmentAvailabilityBlockListCreateView.as_view(),
    ),
    path(
        "equipment-blocks/<uuid:equipment_id>/<uuid:pk>/",
        views.EquipmentAvailabilityBlockDetailView.as_view(),
    ),
    path(
        "equipment-downtimes/<uuid:equipment_id>/",
        views.EquipmentDowntimeListCreateView.as_view(),
    ),
    path(
        "equipment-downtimes/<uuid:equipment_id>/<uuid:pk>/",
        views.EquipmentDowntimeDetailView.as_view(),
    ),
]
