import os


def get_database_url() -> str:
    """Return the Postgres connection string for the active environment.

    Local dev (Docker):
        postgresql://admin:admin1234@localhost:5432/barcelona-real-state
    Production:
        Supabase connection string, supplied via DATABASE_URL.

    Swapping environments is a connection-string change only — no code change.
    """
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://admin:admin1234@localhost:5432/barcelona-real-state",
    )
