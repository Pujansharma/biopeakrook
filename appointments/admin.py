from django.contrib import admin

from appointments.models import (
    AssociateAvailabilityBlock,
    AssociateLeave,
    AssociateRosterEntry,
    EquipmentAvailabilityBlock,
    EquipmentDowntime,
    RoomAvailabilityBlock,
    RoomDowntime,
)

admin.site.register(AssociateRosterEntry)
admin.site.register(AssociateAvailabilityBlock)
admin.site.register(AssociateLeave)
admin.site.register(RoomAvailabilityBlock)
admin.site.register(RoomDowntime)
admin.site.register(EquipmentAvailabilityBlock)
admin.site.register(EquipmentDowntime)
