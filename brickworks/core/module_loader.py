import contextlib
import importlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import entry_points
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from brickworks.core.models.base_dbmodel import BaseDBModel
from brickworks.core.models.base_view import BaseView

logger = logging.getLogger(__name__)


def discover_modules(group: str = "brickworks.modules") -> list[str]:
    """
    Discover modules registered under the specified entry point group.
    To make modules discoverable, they should be registered in the pyproject.toml file like this:
    [project.entry-points."brickworks.modules"]
    app_mymodule = "app.mymodule"

    You only need to register local bricks in the pyproject.toml file.
    Bricks installed as packages don't need to be registered in the pyproject.toml file, because
    packages register their entry points in their own pyproject.toml file.
    """

    return [ep.value for ep in entry_points(group=group)]


@dataclass
class Module:
    path: str
    routers: list[str]
    python_module: object
    middlewares: list[str]


class ModuleJsonContent(BaseModel):
    routers: list[str] = []
    middlewares: list[str] = []
    loadme: list[str] = []


@lru_cache
def load_modules() -> list[Module]:
    """
    Load all modules from the pyproject.toml file.
    """
    module_names = discover_modules()

    modules = []
    for module in module_names:
        python_module = importlib.import_module(module)
        module_json_path = _get_module_json_path(module)
        with open(module_json_path, encoding="UTF-8") as f:
            module_json_content = ModuleJsonContent.model_validate(json.load(f))
            modules.append(
                Module(
                    path=module,
                    python_module=python_module,
                    routers=module_json_content.routers,
                    middlewares=module_json_content.middlewares,
                )
            )

            # import modules from loadme
            for loadme in module_json_content.loadme:
                importlib.import_module(loadme)
    logger.info(f"Loaded {len(modules)} modules: {[module.path for module in modules]}")
    return modules


# lru cache so we don't load models if they are already loaded
@lru_cache
def load_models() -> None:
    modules = load_modules()
    for module in modules:
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(module.path + ".models")


T = TypeVar("T")


def get_all_subclasses(cls: type[T]) -> set[type[T]]:
    subclasses = set(cls.__subclasses__())
    for subclass in list(subclasses):
        subclasses.update(get_all_subclasses(subclass))
    return subclasses


@lru_cache
def get_models_by_fqpn() -> dict[str, type[BaseDBModel]]:
    models = get_all_subclasses(BaseDBModel)
    # remove abstract models
    models_filtered = [model for model in models if hasattr(model, "__tablename__")]

    return {model.fqpn(): model for model in models_filtered}


@lru_cache
def get_views() -> list[type[BaseView]]:
    views = get_all_subclasses(BaseView)
    # remove abstract views
    views_filtered = [view for view in views if hasattr(view, "__select__")]
    return views_filtered


def _get_module_json_path(module_name: str) -> str:
    module = importlib.import_module(module_name)
    if module.__file__ is None:
        raise ValueError(f"Module {module_name} does not have a __file__ attribute.")
    module_dir = Path(module.__file__).parent
    bricks_json_path = module_dir / "brick.json"
    return str(bricks_json_path)
