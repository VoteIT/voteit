# Narrative model docs

Meant to show the purpose of models and how they relate to each other.
This file is part of the regular test suite too.

## Organisations

Several may exist in one instance. Every meeting has a relation
to an organisation. They may also later on contain templates
and API-points for things that the organisation might need.

    >>> from voteit.organisation.models import Organisation
    >>> org = Organisation.objects.create(title="VoteIT")
    >>> jane = org.users.create(username="jane")

Meeting creators should only have the option to create a meeting
but can't touch anything else.

    >>> from voteit.organisation.rules import is_meeting_creator
    >>> from voteit.organisation.roles import ROLE_MEETING_CREATOR
    >>> org.add_roles(jane, ROLE_MEETING_CREATOR)
    {Meeting creator (meeting_creator)}

    >>> is_meeting_creator(jane, org)
    True


Organisation managers should have access to all
settings and meetings. The rule is_manager checks that.

    >>> from voteit.organisation.rules import is_manager
    >>> from voteit.organisation.roles import ROLE_ORG_MANAGER
    >>> org.add_roles(jane, ROLE_ORG_MANAGER)
    {Organisation manager (org_manager)}

    >>> is_manager(jane, org)
    True

Most permissions checks are done directly from the user model though.

    >>> from voteit.organisation.permissions import OrgPermissions
    >>> jane.has_perm(OrgPermissions.MANAGE, org)
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
    >>> from voteit.meeting.roles import ROLE_PARTICIPANT
    >>> is_participant(jane, meeting)
    False

    >>> meeting.add_roles(jane, ROLE_PARTICIPANT)
    {Participant (pa)}

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
