from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class SpeakerSystemPermissions(ModelPermissions):
    model = "speaker_system"
    ADD = P("speaker.add_speakerlistsystem", context="room")
    CHANGE = P("speaker.change_speakerlistsystem")
    DELETE = P("speaker.delete_speakerlistsystem")
    VIEW = P("speaker.view_speakerlistsystem")
    # While related to "change", manage is still active when something is archived and thus not changable.
    MANAGE = P("speaker.manage_speakerlistsystem")
    CHANGE_ROLES = P("speaker.change_roles_speakerlistsystem")
    VIEW_ROLES = P("speaker.view_roles_speakerlistsystem")


class SpeakerListPermissions(ModelPermissions):
    model = "speaker_list"
    ADD = P("speaker.add_speakerlist", context="speaker_system")
    CHANGE = P("speaker.change_speakerlist")
    DELETE = P("speaker.delete_speakerlist")
    VIEW = P("speaker.view_speakerlist")
    SHUFFLE = P("speaker.shuffle_speakerlist")


class SpeakerPermissions(ModelPermissions):
    model = "speaker"
    ADD = P("speaker.add_speaker", context="speaker_list")
    ENTER = P(
        "speaker.enter_speaker", context="speaker_list"
    )  # Same as add, but only for acting user
    LEAVE = P("speaker.leave_speaker")
    CHANGE = P("speaker.change_speaker")
    DELETE = P("speaker.delete_speaker")
    VIEW = P("speaker.view_speaker")
    START = P("speaker.start_speaker")
    STOP = P("speaker.stop_speaker")
    UNDO = P("speaker.undo_speaker")
