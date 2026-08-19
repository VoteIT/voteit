from django.dispatch import Signal

# Fired synchronously while an RQ worker builds the initial state for a new
# subscription. Receivers append messages to app_state; whatever they add is
# streamed to the subscribing consumer.
#
# Arguments:
#   sender: the ContextChannel subclass
#   context: the model instance the channel points at
#   user: the subscribing user
#   app_state: an AppState to append messages to
channel_subscribed = Signal()
