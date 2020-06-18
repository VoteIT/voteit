# Workflow states

A lot of models in VoteIT have workflows. Some of those states
are related to the state of another model. For instance a closed meeting
can't have ongoing agenda items.

Here's a table of the allowed combinations of state. This should be
enforced in code.

## Meeting -> Agenda Item state combinations

    Note: Private states aren't allowed in archiving/archived
    They have to be removed or handled before archiving.
    Archived meetings also set all agenda items as archived,
    so permission checks that care about state
    are only needed against archived-state on agenda items.

| Meeting       | Agenda Item
|---	        |---
| upcoming      | private, upcoming
| ongoing       | private, upcoming, ongoing, closed
| closed        | closed, private
| archiving     | closed, archived (during process of archiving)
| archived      | archived


## Agenda Item -> Poll


| Agenda Item   | Poll
|---	        |---
| upcoming      | private, upcoming
| ongoing       | (any state)
| closed        | closed
| archived      | closed


## Agenda Item -> Proposal


| Agenda Item   | Proposal
|---	        |---
| upcoming      | (any state)
| ongoing       | (any state)
| closed        | (any state)
| archived      | unhandled, approved, denied, retracted. <br> (any of the "finished" states)
