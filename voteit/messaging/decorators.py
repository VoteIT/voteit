"""
Decorators for registries.
"""
def channel(*args, **kwars):
    from voteit.messaging.registries import channel_registry

    return channel_registry(*args, **kwars)


def outgoing(*args, **kwars):
    from voteit.messaging.registries import outgoing_messages

    return outgoing_messages(*args, **kwars)


def incoming(*args, **kwars):
    from voteit.messaging.registries import incoming_messages

    return incoming_messages(*args, **kwars)
