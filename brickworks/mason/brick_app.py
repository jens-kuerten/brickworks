import os
from pathlib import Path

import tomli
import tomli_w
import typer

from brickworks.core.constants import BASE_DIR
from brickworks.core.module_loader import ModuleJsonContent

brick_app = typer.Typer()


def _create_python_module(path: str) -> None:
    """
    Create a Python module by creating an empty __init__.py file.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    (p / "__init__.py").touch()


def _add_brick_to_toml(name: str, namespace: str) -> None:
    """
    Add the brick to the pyproject.toml file under entry points.
    """
    toml_path = os.path.join(BASE_DIR, "pyproject.toml")
    with open(toml_path, "rb") as f:
        config = tomli.load(f)

    # Ensure the necessary sections exist
    config.setdefault("project", {}).setdefault("entry-points", {}).setdefault("brickworks.modules", {})
    config.setdefault("tool", {}).setdefault("setuptools", {}).setdefault("packages", {}).setdefault(
        "find", {}
    ).setdefault("include", [])

    # Add the new module to the entry points, so that we can discovery it as a brick
    entry_points = config["project"]["entry-points"]["brickworks.modules"]
    entry_points[f"{namespace}_{name}"] = f"{namespace}.{name}"

    # Ensure the module is included in the setuptools packages find section
    include_list = config["tool"]["setuptools"]["packages"]["find"]["include"]
    include_list.append(f"{namespace}.{name}")

    # Write the updated data back to the TOML file
    with open(toml_path, "wb") as file:
        file.write(tomli_w.dumps(config).encode())


def _create_namespace_package(namespace: str) -> None:
    """
    Create a namespace package for the given namespace.
    Does nothing if the namespace already exists.
    """
    namespace_dir = os.path.join(BASE_DIR, namespace)
    if not os.path.exists(namespace_dir):
        os.makedirs(namespace_dir)
    if not os.path.exists(os.path.join(namespace_dir, "__init__.py")):
        with open(os.path.join(namespace_dir, "__init__.py"), "w"):
            pass


@brick_app.command()
def create(name: str, namespace: str = "app") -> None:
    """Create a new brick."""
    typer.echo(f"Creating brick: {namespace}.{name}")

    # make sure the namespace packages folder exists
    _create_namespace_package(namespace)

    # Create the brick directory
    brick_dir = f"{BASE_DIR}/{namespace}/{name}"
    try:
        _create_python_module(brick_dir)
    except FileExistsError:
        typer.echo(f"Path {brick_dir} already exists")
        return

    # create the brick.json file
    module_json_content = ModuleJsonContent()
    with open(os.path.join(brick_dir, "brick.json"), "w", encoding="UTF-8") as f:
        f.write(module_json_content.model_dump_json(indent=4))

    # create the models, schemas and routers modules
    for mod in ("models", "schemas", "routers"):
        _create_python_module(os.path.join(brick_dir, mod))

    # add the brick to the pyproject.toml file
    _add_brick_to_toml(name, namespace)
    typer.echo(f"Brick {namespace}.{name} created successfully.")
    typer.echo("Don't forget to install the project with `pip install -e .`")
