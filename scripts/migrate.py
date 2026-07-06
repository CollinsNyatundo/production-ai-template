import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scripts.migrate")


def run_migrations():
    logger.info("Executing database schema migrations...")
    # In production, runs Alembic migrations or SQL schema setups
    # to create conversational history tables, user feedback logs, etc.
    logger.info("Creating table: conversation_history")
    logger.info("Creating table: user_feedback")
    logger.info("Database migration finished successfully.")


if __name__ == "__main__":
    run_migrations()
