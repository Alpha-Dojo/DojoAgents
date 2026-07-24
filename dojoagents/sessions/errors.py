from __future__ import annotations


class SessionError(RuntimeError):
    code = "session_error"
    retryable = False


class SessionNotFoundError(SessionError):
    code = "session_not_found"


class SessionAccessDeniedError(SessionError):
    code = "session_access_denied"


class SessionConflictError(SessionError):
    code = "session_conflict"


class SessionLeaseLostError(SessionError):
    code = "session_lease_lost"


class SessionStoreUnavailableError(SessionError):
    code = "session_store_unavailable"
    retryable = True


class SessionDataCorruptError(SessionError):
    code = "session_data_corrupt"


class HarnessSessionIncompatibleError(SessionError):
    code = "harness_session_incompatible"


class BlobStoreError(SessionError):
    code = "blob_store_error"
    retryable = True


class SessionsDisabledError(SessionError):
    code = "sessions_disabled"
