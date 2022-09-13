
# Some notes on the design

## Sent information

What's pushed to each channel and why?

### Meeting

* Any changes to speaker list system (this includes indication of active speaker list, but not the contents of it.)
* Deleted speaker lists, since both agenda and speaker systems need to know about them.
  (And the deleted state isn't sent via subscribe)
 

### Agenda Item

* Speaker List - combined message with order and details about current speaker

### Speaker list system

* The active speaker list - combined message with order and details about current speaker
* Changes to speaker object if it's at least started and within an active list
* All speaker objects that have been started at least
