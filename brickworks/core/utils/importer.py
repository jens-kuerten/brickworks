import importlib
from typing import Any


def import_object_from_path(attribute_path: str) -> Any:  # noqa: ANN401
    """
    import an object from a path like "module.submodule.object"
    """
    split_path = attribute_path.split(".")
    attribute_name = split_path.pop()
    module_name = ".".join(split_path)

    module = importlib.import_module(module_name)
    obj = getattr(module, attribute_name)

    return obj
