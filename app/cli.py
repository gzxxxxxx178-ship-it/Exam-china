import argparse
import asyncio
import json

from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.db.session import SessionLocal
from app.seeds import load_divisions, load_sources
from app.services.ingestion import run_source


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
    run_parser = subparsers.add_parser("run-source", help="运行一个已启用的采集来源")
    run_parser.add_argument("source_key")
    run_parser.add_argument("--max-items", type=int, default=20)
    run_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "init-db":
        initialize_database()
    elif args.command == "run-source":
        with SessionLocal() as session:
            result = asyncio.run(
                run_source(
                    session,
                    get_settings(),
                    args.source_key,
                    max_items=args.max_items,
                    dry_run=args.dry_run,
                )
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
