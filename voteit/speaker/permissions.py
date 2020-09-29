

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


class SpeakerPermissions:
    """ Add here is essentially enter list, while delete will be remove from list
        if user hasn't spoken or is ongoing.
    """
    ADD = "voteit.speaker.add_speaker"  # Checked against speaker list
    CHANGE = "voteit.speaker.change_speaker"
    DELETE = "voteit.speaker.delete_speaker"
    VIEW = "voteit.speaker.view_speaker"
