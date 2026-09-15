import argparse

from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.db.session import SessionLocal
from app.seeds import load_divisions, load_sources


def initialize_database() -> None:
    settings = get_settings()
    command.upgrade(Config("alembic.ini"), "head")
    with SessionLocal.begin() as session:
        divisions = load_divisions(session, settings.division_seed_path)
        sources = load_sources(session, settings.source_config_path)
    print(f"database initialized: divisions={divisions}, sources={sources}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="exam-finding")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="创建数据库并导入基础配置")
    args = parser.parse_args()
    if args.command == "init-db":
        initialize_database()


if __name__ == "__main__":
    main()
