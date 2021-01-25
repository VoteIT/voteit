class SpeakerSystemPermissions:
    ADD = "voteit.speaker.add_speaker_system"  # We don't know about this perm yet
    CHANGE = "voteit.speaker.change_speaker_system"
    DELETE = "voteit.speaker.delete_speaker_system"
    VIEW = "voteit.speaker.view_speaker_system"


class SpeakerListPermissions:
    ADD = "voteit.speaker.add_speaker_list"  # Checked against speaker system
    CHANGE = "voteit.speaker.change_speaker_list"
    DELETE = "voteit.speaker.delete_speaker_list"
    VIEW = "voteit.speaker.view_speaker_list"
    ENTER = "voteit.speaker.enter_speaker_list"
    LEAVE = "voteit.speaker.leave_speaker_list"
    START = "voteit.speaker.start_speaker_in_list"
    STOP = "voteit.speaker.stop_speaker_in_list"
