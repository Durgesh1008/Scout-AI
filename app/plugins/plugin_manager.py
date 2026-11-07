import importlib
import pkgutil
import logging
from typing import List, Dict, Any
import app.plugins

logger = logging.getLogger(__name__)


def list_plugins() -> List[str]:
    """Dynamically scan and list all installed plugin modules."""
    return [
        m.name for m in pkgutil.iter_modules(app.plugins.__path__)
        if m.name not in {"plugin_manager", "base", "__init__"}
    ]


def get_plugin_info() -> List[Dict[str, str]]:
    """Get metadata for all available plugins."""
    plugins = []
    for name in list_plugins():
        try:
            module = importlib.import_module(f"app.plugins.{name}")
            instance = getattr(module, "plugin_instance", None)
            if instance:
                plugins.append({"name": instance.name, "description": instance.description})
            else:
                plugins.append({"name": name, "description": "Custom modular plugin"})
        except Exception as e:
            logger.warning(f"Failed to load plugin info for {name}: {e}")
    return plugins


def run_plugin(name: str, **kwargs) -> Dict[str, Any]:
    """Execute a plugin by name safely."""
    available = list_plugins()
    if name not in available:
        raise ValueError(f"Unknown plugin '{name}'. Available: {available}")

    module = importlib.import_module(f"app.plugins.{name}")
    if not hasattr(module, "run"):
        raise ValueError(f"Plugin '{name}' must expose a run() entrypoint.")

    return module.run(**kwargs)
