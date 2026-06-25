"""Create database tables. Run: python3 init_db.py"""

from db import DATABASE_URL, init_db


def main() -> None:
    init_db()
    print(f"Database ready: {DATABASE_URL}")


if __name__ == "__main__":
    main()
