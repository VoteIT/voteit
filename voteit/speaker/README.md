
# Some notes on the design

## Sent information

What's pushed to each channel and why?

### Noteringar

- Reorder får inte påverka nuvarande talare + antal säkra platser
- order_list har "eventual consistency"

## Contexts and their needs

### Agenda item

- All list names
- Changes to speaker list
- User id order (preserve order, don't change when a speaker is started)
- current speaker (on subscribe)

- started or stopped speaker (live)

### Meeting

Speaker system + ändringar (utom aktiv talarlista)

### Room

All speakers within active list, regardless of their state

List activated-message

