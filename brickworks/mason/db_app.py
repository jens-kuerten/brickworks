import asyncio
import logging
import subprocess  # nosec
from argparse import Namespace
from pathlib import Path

import typer
from alembic import command, script
from alembic.config import Config
from alembic.util.exc import AutogenerateDiffsDetected
from sqlalchemy import text

from brickworks.core import db
from brickworks.core.constants import BASE_DIR, CORE_DIR
from brickworks.core.db import get_db_url
from brickworks.core.module_loader import load_modules

logger = logging.getLogger(__name__)


db_app = typer.Typer()


@db_app.command()
def drop(schema: str) -> None:
    """Drop the database schema."""
    asyncio.run(_drop_schema(schema))


@db_app.command()
def upgrade(message: str | None = None) -> None:
    """Create and apply database migrations."""
    typer.echo("Upgrading database")
    if has_changes():
        make_migration(message)

    _migrate()


@db_app.command()
def migrate(schema: str = "") -> None:
    """Run database migrations."""
    typer.echo("Running database migrations")
    _migrate(schema)


@db_app.command()
def downgrade(levels: int = 1) -> None:
    """Downgrade database migrations."""
    typer.echo("Downgrading database")
    command.downgrade(get_config(), f"-{levels}")

    # delete the migration files
    migration_dir = Path(BASE_DIR) / "migrations"
    migration_files = sorted([f for f in migration_dir.iterdir() if f.suffix == ".py"], reverse=True)
    for i in range(levels):
        if i < len(migration_files):
            migration_files[i].unlink()
        else:
            break


@db_app.command()
def squash(force: bool = False) -> None:
    """
    Squashes the database migrations of the current branch.
    Will not work on main or master branch unless --force is used.
    This is useful for cleaning up the migration history and reducing the number of migrations.
    """
    typer.echo("Merging database migrations")
    branch = get_current_git_branch()
    if not force and branch in ("main", "master"):
        # This is a safety check to prevent squashing migrations on the main branch,
        # which is usually a bad idea because squashing on main would break deployed instances
        typer.echo("Cannot squash migrations on main or master branch. Use --force to override.")
        return

    levels = count_branch_revisions(branch)
    typer.echo(f"Squashing {levels} migrations")
    if levels == 0:
        typer.echo("No migrations to squash")
        return
    downgrade(levels)
    upgrade()


def count_branch_revisions(branch: str) -> int:
    """Count the number of revisions in the given branch."""
    sc = script.ScriptDirectory.from_config(get_config())
    revisions = sc.walk_revisions()
    count = 0
    for rev in revisions:
        if rev.path.endswith(branch + ".py"):
            count += 1
        else:
            # stop counting when we reach a revision that doesn't belong to the branch
            return count
    return count


def get_config() -> Config:
    config = Config(str(Path(CORE_DIR) / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", get_db_url())
    config.set_main_option("script_location", str(Path(CORE_DIR) / "migration"))
    config.set_main_option("version_locations", str(Path(BASE_DIR) / "migrations"))
    return config


def _migrate(schema: str = "") -> None:
    """Run database migrations."""
    config = get_config()
    x = ["mode=migrate"]
    if schema:
        x.append(f"schema={schema}")
    config.cmd_opts = Namespace(x=x)
    command.upgrade(config, "head")


def make_migration(message: str | None = None) -> None:
    """Create a new database migration."""
    load_modules()

    if not message:
        message = get_current_git_branch()

    config = get_config()
    config.cmd_opts = Namespace(autogenerate=True, message=message)

    command.revision(config, autogenerate=True, message=message)


def has_changes() -> bool:
    """
    Check if there are any migrations to be made.
    Returns true if there are unmigrated changes.
    """
    load_modules()
    config = get_config()
    try:
        command.check(config=config)
    except AutogenerateDiffsDetected:
        return True
    return False


def get_current_git_branch() -> str:
    try:
        # Run the git command to get the current branch name
        result = subprocess.run(  # nosec
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True
        )
        # Return the branch name (strip out any extra whitespace)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        typer.echo("Failed to get current git branch. Make sure you are in a git repository.")
        return ""


async def _drop_schema(schema: str) -> None:
    """Drop the database schema."""
    typer.echo(f"Dropping database schema: {schema}")
    async with db(commit_on_exit=True):
        await db.session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
