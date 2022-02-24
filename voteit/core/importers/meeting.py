from django.db import transaction
from django.utils.timezone import now

from voteit.core.importers.base import BaseImport
from voteit.core.importers.base import BaseImporter
from voteit.core.utils import get_model_shortname


class MeetingImport(BaseImport):
    name = settings_key = "meeting"


class MeetingImporter(BaseImporter):
    import_class = MeetingImport

    def run(self):
        # We need to muck about with all objects so keeping them in memory (or later in a temp file) is required :/
        all_objects = list(self.load_objects())
        deserialized_meeting = None

        # Walk
        for deserialized in all_objects:
            name = get_model_shortname(deserialized.object)
            if name == "meeting":
                if name in self.objects_to_handle:
                    raise ValueError("Multiple meetings found in file")
                deserialized_meeting = deserialized
            self.add_obj_to_handle(deserialized)
        if deserialized_meeting is None:
            raise ValueError("No meeting found")

        import_order = ["meeting", "agenda_item", "speaker_system", "meeting_group"]
        # FIXME: Figure out ordering from relations that need to be replaced instead.

        with transaction.atomic():
            self.update_special_fields(deserialized_meeting)
            # FIXME: Set title?
            deserialized_meeting.object.title = (
                deserialized_meeting.object.title + f"-copy-{now().date()}"
            )
            self.save_obj(deserialized_meeting)
            [
                import_order.append(x)
                for x in self.objects_to_handle
                if x not in import_order
            ]
            import_order.pop(0)  # Meeting already handled
            for name in import_order:
                items = self.objects_to_handle[name]
                for deserialized in items.values():
                    self.update_special_fields(deserialized)
                    self.save_obj(deserialized)
            self.update_deferred()
        self.stream.close()
