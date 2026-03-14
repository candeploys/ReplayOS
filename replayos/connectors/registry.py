from __future__ import annotations

from pathlib import Path
import importlib.util

from .base import BaseConnector
from .builtin import GmailIMAPConnector, NotionConnector, SlackConnector


def builtin_connectors() -> list[BaseConnector]:
    return [GmailIMAPConnector(), SlackConnector(), NotionConnector()]


def load_plugin_connectors(plugin_dirs: tuple[str, ...]) -> list[BaseConnector]:
    connectors: list[BaseConnector] = []

    for directory in plugin_dirs:
        path = Path(directory).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            continue

        for py_file in sorted(path.glob("*.py")):
            module_name = f"replayos_plugin_{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            build = getattr(module, "build_connector", None)
            if callable(build):
                connector = build()
                if isinstance(connector, BaseConnector):
                    connectors.append(connector)

    return connectors


def all_connectors(plugin_dirs: tuple[str, ...]) -> list[BaseConnector]:
    items = builtin_connectors()
    items.extend(load_plugin_connectors(plugin_dirs))
    return items
