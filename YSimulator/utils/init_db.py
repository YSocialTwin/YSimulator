"""
Database initialization script for YSimulator.

This script creates and initializes databases with the complete schema
for SQLite, PostgreSQL, or MySQL backends. It can be run standalone or
called programmatically by the server.
"""

import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import models
from YSimulator.YServer.classes.models import Base


def create_database_engine(db_config: dict, config_path: Path = None):
    """
    Create SQLAlchemy engine based on database configuration.

    Args:
        db_config: Database configuration dictionary
        config_path: Path to configuration directory (for SQLite)

    Returns:
        SQLAlchemy engine instance

    Raises:
        ValueError: If database configuration is invalid
    """
    db_type = db_config.get("type", "sqlite")

    if db_type == "sqlite":
        sqlite_config = db_config.get("sqlite", {})
        db_filename = sqlite_config.get("filename", "simulation.db")

        # If config_path provided, use it; otherwise use current directory
        if config_path:
            db_path = config_path / db_filename
        else:
            db_path = Path(db_filename)

        connection_string = f"sqlite:///{db_path}"

    elif db_type == "postgresql":
        pg_config = db_config.get("postgresql", {})
        host = pg_config.get("host", "localhost")
        port = pg_config.get("port", 5432)
        database = pg_config.get("database", "ysimulator")
        username = pg_config.get("username", "postgres")
        password = pg_config.get("password", "")

        # URL encode password to handle special characters
        encoded_password = quote_plus(password) if password else ""

        if encoded_password:
            connection_string = (
                f"postgresql+psycopg2://{username}:{encoded_password}@{host}:{port}/{database}"
            )
        else:
            connection_string = f"postgresql+psycopg2://{username}@{host}:{port}/{database}"

    elif db_type == "mysql":
        mysql_config = db_config.get("mysql", {})
        host = mysql_config.get("host", "localhost")
        port = mysql_config.get("port", 3306)
        database = mysql_config.get("database", "ysimulator")
        username = mysql_config.get("username", "root")
        password = mysql_config.get("password", "")

        # URL encode password to handle special characters
        encoded_password = quote_plus(password) if password else ""

        if encoded_password:
            connection_string = (
                f"mysql+pymysql://{username}:{encoded_password}@{host}:{port}/{database}"
            )
        else:
            connection_string = f"mysql+pymysql://{username}@{host}:{port}/{database}"

    else:
        raise ValueError(f"Unsupported database type: {db_type}")

    # Create engine
    engine = create_engine(connection_string, echo=False)
    return engine


def initialize_database(db_config: dict, config_path: Path = None, logger=None):
    """
    Initialize database by creating all tables.

    Args:
        db_config: Database configuration dictionary
        config_path: Path to configuration directory (for SQLite)
        logger: Optional logger instance

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create engine
        engine = create_database_engine(db_config, config_path)

        # Create all tables
        Base.metadata.create_all(engine)

        if logger:
            logger.info(
                f"Database initialized successfully",
                extra={"extra_data": {"db_type": db_config.get("type", "sqlite")}},
            )
        else:
            logging.info(f"✅ Database initialized successfully ({db_config.get('type', 'sqlite')})")

        return True

    except Exception as e:
        if logger:
            logger.error(f"Failed to initialize database: {e}")
        else:
            logging.error(f"❌ Failed to initialize database: {e}")
        return False


def database_exists(db_config: dict, config_path: Path = None) -> bool:
    """
    Check if database already exists.

    Args:
        db_config: Database configuration dictionary
        config_path: Path to configuration directory (for SQLite)

    Returns:
        True if database exists, False otherwise
    """
    db_type = db_config.get("type", "sqlite")

    if db_type == "sqlite":
        sqlite_config = db_config.get("sqlite", {})
        db_filename = sqlite_config.get("filename", "simulation.db")

        if config_path:
            db_path = config_path / db_filename
        else:
            db_path = Path(db_filename)

        return db_path.exists()

    else:
        # For PostgreSQL/MySQL, try to connect and check if tables exist
        try:
            engine = create_database_engine(db_config, config_path)
            # Check if at least one table exists
            from sqlalchemy import inspect

            inspector = inspect(engine)
            tables = inspector.get_table_names()
            return len(tables) > 0
        except Exception:
            return False


def main():
    """Main entry point for standalone script execution."""
    parser = argparse.ArgumentParser(
        description="Initialize YSimulator database with complete schema"
    )
    parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgresql", "mysql"],
        default="sqlite",
        help="Database backend type (default: sqlite)",
    )
    parser.add_argument(
        "--config-path",
        type=str,
        help="Path to configuration directory (for SQLite)",
    )

    # SQLite options
    parser.add_argument(
        "--sqlite-filename", default="simulation.db", help="SQLite database filename"
    )

    # PostgreSQL options
    parser.add_argument("--pg-host", default="localhost", help="PostgreSQL host")
    parser.add_argument("--pg-port", type=int, default=5432, help="PostgreSQL port")
    parser.add_argument("--pg-database", default="ysimulator", help="PostgreSQL database name")
    parser.add_argument("--pg-user", default="postgres", help="PostgreSQL username")
    parser.add_argument("--pg-password", default="", help="PostgreSQL password")

    # MySQL options
    parser.add_argument("--mysql-host", default="localhost", help="MySQL host")
    parser.add_argument("--mysql-port", type=int, default=3306, help="MySQL port")
    parser.add_argument("--mysql-database", default="ysimulator", help="MySQL database name")
    parser.add_argument("--mysql-user", default="root", help="MySQL username")
    parser.add_argument("--mysql-password", default="", help="MySQL password")

    args = parser.parse_args()

    # Build database configuration
    db_config = {"type": args.db_type}

    if args.db_type == "sqlite":
        db_config["sqlite"] = {"filename": args.sqlite_filename}
    elif args.db_type == "postgresql":
        db_config["postgresql"] = {
            "host": args.pg_host,
            "port": args.pg_port,
            "database": args.pg_database,
            "username": args.pg_user,
            "password": args.pg_password,
        }
    elif args.db_type == "mysql":
        db_config["mysql"] = {
            "host": args.mysql_host,
            "port": args.mysql_port,
            "database": args.mysql_database,
            "username": args.mysql_user,
            "password": args.mysql_password,
        }

    # Get config path
    config_path = Path(args.config_path) if args.config_path else None

    # Initialize database
    logging.info(f"Initializing {args.db_type} database...")
    success = initialize_database(db_config, config_path)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
