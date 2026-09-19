from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.centers.models import Center
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType
from appointments.models import AssociateAvailabilityBlock, AssociateLeave
from appointments.utils.constants import LeaveScope
from integrations.google_calendar import availability_sync as sync

MODULE = "integrations.google_calendar.availability_sync"
START_DAY = timezone.localdate() + timedelta(days=3)


def timed_event(event_id="Test event", start="13:30:00", end="14:30:00", day=START_DAY, **extra):
    event = {
        "id": event_id,
        "summary": event_id,
        "start": {"dateTime": f"{day.isoformat()}T{start}+05:30"},
        "end": {"dateTime": f"{day.isoformat()}T{end}+05:30"},
    }
    event.update(extra)
    return event


def all_day_event(event_id, first_day, last_day, **extra):
    event = {
        "id": event_id,
        "summary": event_id,
        "start": {"date": first_day.isoformat()},
        "end": {"date": (last_day + timedelta(days=1)).isoformat()},
    }
    event.update(extra)
    return event


def rrule(rule):
    return [f"RRULE:{rule}"]


class RruleConversionTests(SimpleTestCase):
    def convert(self, rule, day=START_DAY):
        return sync.build_spec_from_event(timed_event(day=day, recurrence=rrule(rule)))

    def test_every_weekday_letter_maps_to_its_own_code(self):
        expected = {"MO": "0", "TU": "1", "WE": "2", "TH": "3", "FR": "4", "SA": "5", "SU": "6"}
        for token, code in expected.items():
            with self.subTest(token=token):
                self.assertEqual(self.convert(f"FREQ=WEEKLY;BYDAY={token}")["days_of_week"], [code])

    def test_weekly_without_byday_uses_start_date_weekday(self):
        for offset in range(7):
            day = START_DAY + timedelta(days=offset)
            with self.subTest(day=day):
                self.assertEqual(self.convert("FREQ=WEEKLY", day=day)["days_of_week"], [str(day.weekday())])

    def test_daily_is_all_seven_days(self):
        self.assertEqual(self.convert("FREQ=DAILY")["days_of_week"], list("0123456"))

    def test_every_weekday_option(self):
        spec = self.convert("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR")
        self.assertEqual(spec["days_of_week"], list("01234"))

    def test_custom_weekly_days_keep_all_chosen_days(self):
        spec = self.convert("FREQ=WEEKLY;BYDAY=SU,MO,TU,TH,SA")
        self.assertEqual(sorted(spec["days_of_week"]), ["0", "1", "3", "5", "6"])

    def test_recurring_payload_shape(self):
        spec = self.convert("FREQ=WEEKLY;BYDAY=TH")
        self.assertTrue(spec["is_recurring"])
        self.assertEqual(spec["kind"], "block")
        self.assertEqual(str(spec["recurring_start_time"]), "13:30:00")
        self.assertEqual(str(spec["recurring_end_time"]), "14:30:00")
        self.assertEqual(spec["effective_from"], START_DAY)
        self.assertIsNone(spec["effective_until"])

    def test_until_utc_datetime_is_last_local_day(self):
        spec = self.convert("FREQ=WEEKLY;UNTIL=20261224T182959Z;BYDAY=TH")
        self.assertEqual(spec["effective_until"], date(2026, 12, 24))

    def test_until_date_only(self):
        spec = self.convert("FREQ=DAILY;UNTIL=20261224")
        self.assertEqual(spec["effective_until"], date(2026, 12, 24))

    def test_until_before_event_start_time_excludes_that_day(self):
        # 04:30Z = 10:00 IST, event starts 13:30 IST, so the 24th has no occurrence.
        spec = self.convert("FREQ=DAILY;UNTIL=20261224T043000Z")
        self.assertEqual(spec["effective_until"], date(2026, 12, 23))

    def test_until_before_first_occurrence_is_skipped(self):
        past = (START_DAY - timedelta(days=1)).strftime("%Y%m%d")
        self.assertIsNone(self.convert(f"FREQ=DAILY;UNTIL={past}"))

    def test_unsupported_rules_are_skipped(self):
        unsupported = [
            "FREQ=WEEKLY;COUNT=13;BYDAY=TH",
            "FREQ=DAILY;COUNT=3",
            "FREQ=WEEKLY;INTERVAL=2;BYDAY=TH",
            "FREQ=DAILY;INTERVAL=2",
            "FREQ=MONTHLY;BYDAY=4TH",
            "FREQ=MONTHLY;BYMONTHDAY=24",
            "FREQ=YEARLY",
            "FREQ=WEEKLY;BYDAY=XX",
        ]
        for rule in unsupported:
            with self.subTest(rule=rule):
                self.assertIsNone(self.convert(rule))

    def test_recurrence_without_rrule_line_is_skipped(self):
        event = timed_event(recurrence=["EXDATE:20261001T080000Z"])
        self.assertIsNone(sync.build_spec_from_event(event))

    def test_exdate_is_ignored_when_rrule_present(self):
        event = timed_event(recurrence=["EXDATE:20261001T080000Z", "RRULE:FREQ=WEEKLY;BYDAY=TH"])
        self.assertEqual(sync.build_spec_from_event(event)["days_of_week"], ["3"])


class SpecBuildingTests(SimpleTestCase):
    def test_timed_one_off_is_a_block(self):
        spec = sync.build_spec_from_event(timed_event("Test one-off"))
        self.assertEqual(spec["kind"], "block")
        self.assertFalse(spec["is_recurring"])
        self.assertEqual(spec["reason"], "Test one-off")
        self.assertEqual(spec["start_datetime"].isoformat()[11:19], "13:30:00")
        self.assertEqual(spec["end_datetime"].isoformat()[11:19], "14:30:00")

    def test_multi_day_all_day_is_leave_ending_2359(self):
        first, last = START_DAY, START_DAY + timedelta(days=1)
        spec = sync.build_spec_from_event(all_day_event("Test leave", first, last))
        self.assertEqual(spec["kind"], "leave")
        self.assertEqual(spec["start_datetime"].isoformat(), f"{first}T00:00:00+05:30")
        self.assertEqual(spec["end_datetime"].isoformat(), f"{last}T23:59:59+05:30")

    def test_single_day_all_day_ends_same_day(self):
        spec = sync.build_spec_from_event(all_day_event("Test leave", START_DAY, START_DAY))
        self.assertEqual(spec["end_datetime"].isoformat(), f"{START_DAY}T23:59:59+05:30")

    def test_timed_out_of_office_is_leave_with_exact_times(self):
        spec = sync.build_spec_from_event(timed_event("Test ooo", eventType="outOfOffice"))
        self.assertEqual(spec["kind"], "leave")
        self.assertEqual(spec["start_datetime"].isoformat()[11:19], "13:30:00")

    def test_recurring_all_day_stays_a_block(self):
        event = all_day_event("Test all-day repeat", START_DAY, START_DAY, recurrence=rrule("FREQ=DAILY"))
        spec = sync.build_spec_from_event(event)
        self.assertEqual(spec["kind"], "block")
        self.assertTrue(spec["is_recurring"])
        self.assertEqual(str(spec["recurring_start_time"]), "00:00:00")
        self.assertEqual(str(spec["recurring_end_time"]), "23:59:59")

    def test_cancelled_free_and_declined_are_skipped(self):
        declined = {"attendees": [{"self": True, "responseStatus": "declined"}]}
        for extra in ({"status": "cancelled"}, {"transparency": "transparent"}, declined):
            with self.subTest(extra=extra):
                self.assertIsNone(sync.build_spec_from_event(timed_event(**extra)))

    def test_declined_by_someone_else_is_kept(self):
        other = {"attendees": [{"self": False, "responseStatus": "declined"}]}
        self.assertIsNotNone(sync.build_spec_from_event(timed_event(**other)))

    def test_fallback_reasons(self):
        block = sync.build_spec_from_event(timed_event(summary=""))
        leave = sync.build_spec_from_event(all_day_event("x", START_DAY, START_DAY, summary=""))
        self.assertEqual(block["reason"], sync.FALLBACK_REASON)
        self.assertEqual(leave["reason"], sync.FALLBACK_LEAVE_REASON)

    def test_reason_is_truncated_to_255(self):
        self.assertEqual(len(sync.build_spec_from_event(timed_event(summary="T" * 400))["reason"]), 255)

    def test_unrecognised_start_shape_is_skipped(self):
        self.assertIsNone(sync.build_spec_from_event({"id": "x", "start": {}, "end": {}}))


class SyncDatabaseTests(TestCase):
    def setUp(self):
        self.center = Center.objects.create(name="Test Sync Center", code="CT-TSYNC")
        user = User.objects.create_user(email="test-sync-associate@example.com")
        UserAccount.objects.create(user=user, account_type=UserType.ASSOCIATE)
        self.user = user
        self.associate = Associate.objects.create(user=user)
        AssociateCenterAssignment.objects.create(
            associate=self.associate, center=self.center, is_active=True
        )
        self.connection = MagicMock()

    def run_sync(self, events):
        with (
            patch(f"{MODULE}.calendar_api.list_events", return_value=events),
            patch(f"{MODULE}.get_valid_access_token", return_value="Test token"),
            patch(f"{MODULE}.apply_availability_exception_hooks", return_value=None),
        ):
            return sync.sync_google_events_to_availability_blocks(self.user, self.connection)

    def counts(self, events):
        result = self.run_sync(events)
        return result["created"], result["replaced"], result["removed"]

    def active_blocks(self, event_id=None):
        blocks = AssociateAvailabilityBlock.objects.filter(associate=self.associate, is_active=True)
        return blocks.filter(google_event_id=event_id) if event_id else blocks.exclude(google_event_id="")

    def active_leaves(self):
        return AssociateLeave.objects.filter(associate=self.associate, is_active=True)

    def add_second_center(self):
        center = Center.objects.create(name="Test Sync Center 2", code="CT-TSYNC2")
        AssociateCenterAssignment.objects.create(
            associate=self.associate, center=center, is_active=True
        )
        return center

    def test_no_associate_profile_is_a_noop(self):
        self.associate.is_active = False
        self.associate.save()
        result = self.run_sync([timed_event()])
        self.assertFalse(result["synced"])
        self.assertEqual(self.active_blocks().count(), 0)

    def test_no_center_assignment_is_a_noop(self):
        AssociateCenterAssignment.objects.filter(associate=self.associate).update(is_active=False)
        self.assertFalse(self.run_sync([timed_event()])["synced"])

    def test_empty_calendar_creates_nothing(self):
        self.assertEqual(self.counts([]), (0, 0, 0))

    def test_one_off_block_created(self):
        self.assertEqual(self.counts([timed_event("Test one-off")]), (1, 0, 0))
        block = self.active_blocks("Test one-off").get()
        self.assertFalse(block.is_recurring)
        self.assertEqual(block.center_id, self.center.pk)
        self.assertEqual(block.reason, "Test one-off")
        self.assertEqual(block.created_by_id, self.user.pk)

    def test_daily_creates_seven_rows(self):
        self.run_sync([timed_event("Test daily", recurrence=rrule("FREQ=DAILY"))])
        days = sorted(self.active_blocks("Test daily").values_list("day_of_week", flat=True))
        self.assertEqual(days, list("0123456"))

    def test_weekly_with_until_sets_effective_until(self):
        event = timed_event("Test custom", recurrence=rrule("FREQ=WEEKLY;UNTIL=20271224T182959Z;BYDAY=SU,MO,TU,TH,SA"))
        self.assertEqual(self.counts([event]), (1, 0, 0))
        blocks = self.active_blocks("Test custom")
        self.assertEqual(sorted(blocks.values_list("day_of_week", flat=True)), ["0", "1", "3", "5", "6"])
        self.assertEqual({b.effective_until for b in blocks}, {date(2027, 12, 24)})
        self.assertEqual({b.effective_from for b in blocks}, {START_DAY})

    def test_unsupported_recurrence_creates_nothing(self):
        event = timed_event("Test monthly", recurrence=rrule("FREQ=MONTHLY;BYDAY=4TH"))
        self.assertEqual(self.counts([event]), (0, 0, 0))
        self.assertEqual(self.active_blocks().count(), 0)

    def test_leave_created_as_single_all_centers_row(self):
        self.add_second_center()
        last = START_DAY + timedelta(days=1)
        self.assertEqual(self.counts([all_day_event("Test leave", START_DAY, last)]), (1, 0, 0))
        leave = self.active_leaves().get()
        self.assertEqual(leave.scope, LeaveScope.ALL_CENTERS)
        self.assertIsNone(leave.center_id)
        self.assertEqual(leave.google_event_id, "Test leave")
        self.assertEqual(timezone.localtime(leave.end_datetime).strftime("%Y-%m-%d %H:%M:%S"), f"{last} 23:59:59")

    def test_blocks_created_at_every_active_center(self):
        self.add_second_center()
        self.run_sync([timed_event("Test one-off")])
        self.assertEqual(self.active_blocks("Test one-off").count(), 2)

    def test_resync_without_changes_writes_nothing(self):
        events = [
            timed_event("Test one-off"),
            timed_event("Test daily", recurrence=rrule("FREQ=DAILY")),
            timed_event("Test until", recurrence=rrule("FREQ=WEEKLY;UNTIL=20271224T182959Z;BYDAY=MO")),
            all_day_event("Test leave", START_DAY, START_DAY),
        ]
        self.assertEqual(self.counts(events), (4, 0, 0))
        ids_before = set(self.active_blocks().values_list("pk", flat=True))
        self.assertEqual(self.counts(events), (0, 0, 0))
        self.assertEqual(set(self.active_blocks().values_list("pk", flat=True)), ids_before)
        self.assertEqual(self.active_leaves().count(), 1)

    def test_edited_time_replaces_block(self):
        self.run_sync([timed_event("Test one-off")])
        old_pk = self.active_blocks("Test one-off").get().pk
        self.assertEqual(self.counts([timed_event("Test one-off", start="15:00:00", end="16:00:00")]), (0, 1, 0))
        block = self.active_blocks("Test one-off").get()
        self.assertNotEqual(block.pk, old_pk)
        self.assertEqual(timezone.localtime(block.start_datetime).strftime("%H:%M"), "15:00")
        self.assertFalse(AssociateAvailabilityBlock.objects.get(pk=old_pk).is_active)

    def test_changed_repeat_days_replaces_block(self):
        self.run_sync([timed_event("Test rec", recurrence=rrule("FREQ=WEEKLY;BYDAY=MO"))])
        self.assertEqual(self.counts([timed_event("Test rec", recurrence=rrule("FREQ=WEEKLY;BYDAY=TU,WE"))]), (0, 1, 0))
        self.assertEqual(sorted(self.active_blocks("Test rec").values_list("day_of_week", flat=True)), ["1", "2"])

    def test_changed_until_replaces_block(self):
        base = "FREQ=WEEKLY;BYDAY=MO;UNTIL="
        self.run_sync([timed_event("Test rec", recurrence=rrule(base + "20271224"))])
        self.assertEqual(self.counts([timed_event("Test rec", recurrence=rrule(base + "20271231"))]), (0, 1, 0))
        self.assertEqual(self.active_blocks("Test rec").get().effective_until, date(2027, 12, 31))

    def test_removing_until_replaces_block(self):
        self.run_sync([timed_event("Test rec", recurrence=rrule("FREQ=DAILY;UNTIL=20271224"))])
        self.assertEqual(self.counts([timed_event("Test rec", recurrence=rrule("FREQ=DAILY"))]), (0, 1, 0))
        self.assertEqual({b.effective_until for b in self.active_blocks("Test rec")}, {None})

    def test_edited_leave_is_replaced(self):
        self.run_sync([all_day_event("Test leave", START_DAY, START_DAY)])
        edited = all_day_event("Test leave", START_DAY, START_DAY + timedelta(days=2))
        self.assertEqual(self.counts([edited]), (0, 1, 0))
        self.assertEqual(self.active_leaves().count(), 1)
        self.assertEqual(AssociateLeave.objects.filter(associate=self.associate).count(), 2)

    def test_deleted_events_are_deactivated_not_deleted(self):
        events = [
            timed_event("Test one-off"),
            timed_event("Test daily", recurrence=rrule("FREQ=DAILY")),
            all_day_event("Test leave", START_DAY, START_DAY),
        ]
        self.run_sync(events)
        self.assertEqual(self.counts([]), (0, 0, 1 + 7 + 1))
        self.assertEqual(self.active_blocks().count(), 0)
        self.assertEqual(self.active_leaves().count(), 0)
        self.assertEqual(AssociateAvailabilityBlock.objects.filter(associate=self.associate).count(), 8)
        self.assertEqual(AssociateLeave.objects.filter(associate=self.associate).count(), 1)

    def test_event_turning_into_all_day_moves_from_block_to_leave(self):
        self.run_sync([timed_event("Test flip")])
        self.assertEqual(self.counts([all_day_event("Test flip", START_DAY, START_DAY)]), (1, 0, 1))
        self.assertEqual(self.active_blocks("Test flip").count(), 0)
        self.assertEqual(self.active_leaves().count(), 1)

    def test_all_day_event_turning_timed_moves_from_leave_to_block(self):
        self.run_sync([all_day_event("Test flip", START_DAY, START_DAY)])
        self.assertEqual(self.counts([timed_event("Test flip")]), (1, 0, 1))
        self.assertEqual(self.active_leaves().count(), 0)
        self.assertEqual(self.active_blocks("Test flip").count(), 1)

    def test_event_marked_free_is_removed(self):
        self.run_sync([timed_event("Test one-off")])
        self.assertEqual(self.counts([timed_event("Test one-off", transparency="transparent")]), (0, 0, 1))

    def test_manually_created_rows_are_never_touched(self):
        manual_block = AssociateAvailabilityBlock.objects.create(
            center=self.center, associate=self.associate, reason="Test manual block",
            start_datetime=timezone.now() + timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=1, hours=1),
        )
        manual_leave = AssociateLeave.objects.create(
            associate=self.associate, scope=LeaveScope.ALL_CENTERS, reason="Test manual leave",
            start_datetime=timezone.now() + timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=2),
        )
        self.run_sync([timed_event("Test one-off")])
        self.assertEqual(self.counts([]), (0, 0, 1))
        manual_block.refresh_from_db()
        manual_leave.refresh_from_db()
        self.assertTrue(manual_block.is_active)
        self.assertTrue(manual_leave.is_active)

    def test_already_ended_one_off_rows_are_not_reported_removed(self):
        ended = timezone.now() - timedelta(days=2)
        block = AssociateAvailabilityBlock.objects.create(
            center=self.center, associate=self.associate, reason="Test ended",
            start_datetime=ended, end_datetime=ended + timedelta(hours=1),
            google_event_id="Test ended block",
        )
        leave = AssociateLeave.objects.create(
            associate=self.associate, scope=LeaveScope.ALL_CENTERS, reason="Test ended",
            start_datetime=ended, end_datetime=ended + timedelta(hours=1),
            google_event_id="Test ended leave",
        )
        self.assertEqual(self.counts([]), (0, 0, 0))
        block.refresh_from_db()
        leave.refresh_from_db()
        self.assertTrue(block.is_active)
        self.assertTrue(leave.is_active)

    def test_newly_assigned_center_gets_blocks_on_next_sync(self):
        events = [timed_event("Test one-off")]
        self.run_sync(events)
        self.add_second_center()
        self.assertEqual(self.counts(events), (0, 1, 0))
        self.assertEqual(self.active_blocks("Test one-off").count(), 2)

    def test_other_associates_rows_are_untouched(self):
        other_user = User.objects.create_user(email="test-other@example.com")
        UserAccount.objects.create(user=other_user, account_type=UserType.ASSOCIATE)
        other = Associate.objects.create(user=other_user)
        other_block = AssociateAvailabilityBlock.objects.create(
            center=self.center, associate=other, reason="Test other",
            start_datetime=timezone.now() + timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=1, hours=1),
            google_event_id="Test other event",
        )
        self.run_sync([timed_event("Test one-off")])
        self.run_sync([])
        other_block.refresh_from_db()
        self.assertTrue(other_block.is_active)

    def test_last_synced_at_and_summary_keys(self):
        result = self.run_sync([timed_event()])
        self.assertEqual(set(result), {"synced", "created", "replaced", "removed", "exception_scan"})
        self.assertIsInstance(self.connection.last_synced_at, datetime)
        self.connection.save.assert_called_once()

    def test_exception_hooks_run_per_row_and_per_center_for_leave(self):
        self.add_second_center()
        events = [timed_event("Test one-off"), all_day_event("Test leave", START_DAY, START_DAY)]
        with (
            patch(f"{MODULE}.calendar_api.list_events", return_value=events),
            patch(f"{MODULE}.get_valid_access_token", return_value="Test token"),
            patch(f"{MODULE}.apply_availability_exception_hooks", return_value=None) as hooks,
        ):
            sync.sync_google_events_to_availability_blocks(self.user, self.connection)
        # 2 block rows (one per center) + 1 leave hook per center.
        self.assertEqual(hooks.call_count, 4)
