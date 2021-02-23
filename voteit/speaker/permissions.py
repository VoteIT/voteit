from voteit.core.registries import permissions


class SpeakerSystemPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.speaker.models import SpeakerListSystem
    >>> find_bad_permission_names(SpeakerSystemPermissions, SpeakerListSystem)

    """

    ADD = permissions.create("speaker.add_speakerlistsystem", "meeting.Meeting")
    CHANGE = permissions.create(
        "speaker.change_speakerlistsystem", "speaker.SpeakerListSystem"
    )
    DELETE = permissions.create(
        "speaker.delete_speakerlistsystem", "speaker.SpeakerListSystem"
    )
    VIEW = permissions.create(
        "speaker.view_speakerlistsystem", "speaker.SpeakerListSystem"
    )


class SpeakerListPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.speaker.models import SpeakerList
    >>> find_bad_permission_names(SpeakerListPermissions, SpeakerList)

    """

    ADD = permissions.create("speaker.add_speakerlist", "speaker.SpeakerListSystem")
    CHANGE = permissions.create("speaker.change_speakerlist", "speaker.SpeakerList")
    DELETE = permissions.create("speaker.delete_speakerlist", "speaker.SpeakerList")
    VIEW = permissions.create("speaker.view_speakerlist", "speaker.SpeakerList")
    ENTER = permissions.create("speaker.enter_speakerlist", "speaker.SpeakerList")
    LEAVE = permissions.create("speaker.leave_speakerlist", "speaker.SpeakerList")
    START = permissions.create("speaker.start_speaker_in_list", "speaker.SpeakerList")
    STOP = permissions.create("speaker.stop_speaker_in_list", "speaker.SpeakerList")
