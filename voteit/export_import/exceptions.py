class ImportFileError(Exception):
    """
    Something went wrong when reading a file
    """


class SignatureVerificationFailed(ValueError):
    """
    Payload -meta doesn't match signature
    """
