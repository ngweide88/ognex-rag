class OgnexError(Exception):
    """Base class for expected application errors."""

    status_code = 400


class KnowledgeBaseNotFound(OgnexError):
    status_code = 404