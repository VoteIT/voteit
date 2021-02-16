from voteit.core.registries import permissions


class SpeakerSystemPermissions:
    ADD = permissions.create("voteit.speaker.add_speaker_system", "meeting.Meeting")
    CHANGE = permissions.create(
        "voteit.speaker.change_speaker_system", "speaker.SpeakerListSystem"
    )
    DELETE = permissions.create(
        "voteit.speaker.delete_speaker_system", "speaker.SpeakerListSystem"
    )
    VIEW = permissions.create(
        "voteit.speaker.view_speaker_system", "speaker.SpeakerListSystem"
    )


class SpeakerListPermissions:
    ADD = permissions.create(
        "voteit.speaker.add_speaker_list", "speaker.SpeakerListSystem"
    )
    CHANGE = permissions.create(
        "voteit.speaker.change_speaker_list", "speaker.SpeakerList"
    )
    DELETE = permissions.create(
        "voteit.speaker.delete_speaker_list", "speaker.SpeakerList"
    )
    VIEW = permissions.create("voteit.speaker.view_speaker_list", "speaker.SpeakerList")
    ENTER = permissions.create(
        "voteit.speaker.enter_speaker_list", "speaker.SpeakerList"
    )
    LEAVE = permissions.create(
        "voteit.speaker.leave_speaker_list", "speaker.SpeakerList"
    )
    START = permissions.create(
        "voteit.speaker.start_speaker_in_list", "speaker.SpeakerList"
    )
    STOP = permissions.create(
        "voteit.speaker.stop_speaker_in_list", "speaker.SpeakerList"
    )
