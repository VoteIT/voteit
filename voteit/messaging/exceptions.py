
class UnsupportedMessageType(Exception):
    """ Exception that will sooner or later cause connection to close with status 1007
    """
    pass
