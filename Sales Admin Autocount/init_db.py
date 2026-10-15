"""
Initialize the database with schema and seed data.
Run this script to set up the database for the first time.
For existing databases, applies lightweight migrations (ALTER TABLE ADD COLUMN)
so schema changes don't require dropping data.
"""
from sqlalchemy import text, inspect
from database import init_database, get_db_engine, Base
from config import settings
import sys


# Lightweight migrations for schema changes made after the initial release.
# Each entry: (table, column, SQLite column definition)
MIGRATIONS = [
    ("staff_allowlist", "telegram_user_id", "ALTER TABLE staff_allowlist ADD COLUMN telegram_user_id VARCHAR(20)"),
    ("conversation_states", "participant_id", "ALTER TABLE conversation_states ADD COLUMN participant_id VARCHAR(20) NOT NULL DEFAULT ''"),
]


def migrate_existing_database(engine):
    """
    Apply column migrations to tables that already exist.
    SQLite supports ADD COLUMN (not column drops/renames); the participant_phone
    -> participant_id rename is handled by adding the new column and copying data.
    """
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    with engine.connect() as conn:
        for table, column, ddl in MIGRATIONS:
            if table not in existing_tables:
                continue

            existing_columns = [c["name"] for c in inspector.get_columns(table)]

            # Special case: legacy participant_phone data is copied into participant_id
            if table == "conversation_states" and "participant_phone" in existing_columns and "participant_id" not in existing_columns:
                conn.execute(text(ddl))
                conn.execute(text("UPDATE conversation_states SET participant_id = participant_phone"))
                conn.commit()
                print(f"  Migrated {table}: added {column}, copied participant_phone data")
                continue

            if column not in existing_columns:
                conn.execute(text(ddl))
                conn.commit()
                print(f"  Migrated {table}: added {column}")
            else:
                print(f"  {table}.{column} already present - skipped")


def main():
    print(f"Initializing database at: {settings.database_url}")

    try:
        engine = init_database(settings.database_url)
        print("Database schema created successfully.")
        print("\nTables created:")
        for table_name in Base.metadata.tables.keys():
            print(f"  - {table_name}")

        print("\nApplying migrations if needed:")
        migrate_existing_database(engine)

        print("\nNext steps:")
        print("1. Add staff members to the staff_allowlist table")
        print("2. Seed glossary entries for shortform/term resolution")
        print("3. Seed SKU index entries (pending SAP integration)")
        print("4. Seed price reference table (admin-maintained)")

    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
