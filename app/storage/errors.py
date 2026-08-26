"""Fail-closed storage errors with stable, path-free classifications."""


class StorageError(RuntimeError):
    code = "SQLITE_STORAGE_ERROR"

    def __init__(self, message: str = "SQLite storage operation failed.") -> None:
        super().__init__(message)


class SQLiteRuntimeUnsafeError(StorageError):
    code = "SQLITE_RUNTIME_UNSAFE"


class SQLiteWalUnavailableError(StorageError):
    code = "SQLITE_WAL_UNAVAILABLE"


class SQLiteBusyError(StorageError):
    code = "SQLITE_BUSY"


class SQLiteSchemaUnsupportedError(StorageError):
    code = "SQLITE_SCHEMA_UNSUPPORTED"


class SQLiteIntegrityError(StorageError):
    code = "SQLITE_INTEGRITY_FAILED"


class SQLiteMigrationError(StorageError):
    code = "SQLITE_MIGRATION_FAILED"


class SQLiteMigrationAmbiguousIdentityError(SQLiteMigrationError):
    code = "SQLITE_MIGRATION_AMBIGUOUS_IDENTITY"


class SQLiteBackupError(StorageError):
    code = "SQLITE_BACKUP_FAILED"


class SQLiteActivationError(StorageError):
    code = "SQLITE_ACTIVATION_FAILED"
