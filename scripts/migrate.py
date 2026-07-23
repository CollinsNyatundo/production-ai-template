import logging
import sys
import traceback
from pathlib import Path

from alembic import command
from alembic.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scripts.migrate")


def run_migrations():
    # Verify alembic.ini exists
    alembic_ini_path = Path("alembic.ini")
    if not alembic_ini_path.exists():
        sys.stderr.write(f"alembic.ini not found at {alembic_ini_path.absolute()}\n")
        sys.exit(1)

    alembic_cfg = Config("alembic.ini")

    # Parse command line argument for upgrade/downgrade
    args = sys.argv[1:]
    cmd = args[0] if args else "upgrade"

    try:
        if cmd == "upgrade":
            logger.info("Executing database schema migrations (upgrade head)...")
            command.upgrade(alembic_cfg, "head")
            logger.info("Database migrations upgraded to head successfully.")
        elif cmd == "downgrade":
            logger.info("Executing database schema rollback (downgrade -1)...")
            command.downgrade(alembic_cfg, "-1")
            logger.info("Database migrations rolled back (-1 revision) successfully.")
        else:
            sys.stderr.write(f"Unknown migration action: '{cmd}'. Supported actions: 'upgrade', 'downgrade'\n")
            sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Migration command '{cmd}' failed: {e}\n")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
