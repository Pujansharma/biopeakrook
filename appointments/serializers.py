from appointments.models import Schedule
from core.utils.serializers import BaseModelSerializer


class ScheduleSerializer(BaseModelSerializer):
    class Meta:
        model = Schedule
        fields = [
            "id",
            "day_of_week",
            "start_time",
            "end_time",
            "duration",
            "mode",
            "buffer_time",
            "valid_from",
            "valid_until",
            "created_at",
            "updated_at",
        ]
