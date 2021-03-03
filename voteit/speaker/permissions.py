from voteit.core.permission import ModelPermissions
from voteit.core.permission import Permission as P


class SpeakerSystemPermissions(ModelPermissions):
    model = "speaker_system"
    ADD = P("speaker.add_speakerlistsystem", context="meeting")
    CHANGE = P("speaker.change_speakerlistsystem")
    DELETE = P("speaker.delete_speakerlistsystem")
    VIEW = P("speaker.view_speakerlistsystem")


class SpeakerListPermissions(ModelPermissions):
    model = "speaker_list"
    ADD = P("speaker.add_speakerlist", context="speaker_system")
    CHANGE = P("speaker.change_speakerlist")
    DELETE = P("speaker.delete_speakerlist")
    VIEW = P("speaker.view_speakerlist")
    ENTER = P("speaker.enter_speakerlist")
    LEAVE = P("speaker.leave_speakerlist")
    START = P("speaker.start_speaker_in_list")
    STOP = P("speaker.stop_speaker_in_list")
