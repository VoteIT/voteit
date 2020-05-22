# Narrative model docs

Ment to show the purpose of models and how they relate to each other.
This file is part of the regular test suite too.

Since most thins relate to user, we'll create a user first.

    >>> from django.contrib.auth.models import User
    >>> jane = User.objects.create(username="jane")

## Organisations

Several may exist in one instance. Every meeting has a relation
to an organisation. They may also later on contain templates
and API-points for things that the organisation might need.

    >>> from voteit.organisation.models import Organisation
    >>> org = Organisation.objects.create(title="VoteIT")

Organisations have managers - they should have access to all
settings and meetings. The rule is_manager checks that.

    >>> from voteit.organisation.rules import is_manager
    >>> org.managers.add(jane)
    >>> org.save()
    >>> is_manager(jane, org)
    True

Meeting creators should only have the option to create a meeting
but can't touch anything else.

    >>> from voteit.organisation.rules import is_meeting_creator
    >>> org.meeting_creators.add(jane)
    >>> org.save()
    >>> is_meeting_creator(jane, org)
    True

## Meetings

The base for most actions within VoteIT. Most objects can't exist
without a relation to a meeting. They have a relation
to the organisation they belong to

    >>> from voteit.meeting.models import Meeting
    >>> meeting = Meeting.objects.create(organisation=org)
    >>> meeting in org.meetings.all()
    True

A user who's a participant of a meeting is checked against the
rule is_participant. Any user who interacts with something within
a meeting should pass that rule first.

    >>> from voteit.meeting.rules import is_participant
    >>> is_participant(jane, meeting)
    False

    >>> meeting.participants.add(jane)
    >>> meeting.save()
    >>> is_participant(jane, meeting)
    True

Meetings also have relations to electoral registers, but
we haven't got there yet - they're part of the poll structure.

    >>> meeting.get_latest_er()


## Agenda items

Organises proposals, discussion posts and polls...
To be continued...

## Discussion posts

## Proposals

# Polls

