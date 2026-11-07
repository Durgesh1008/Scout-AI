from abc import ABC, abstractmethod
from typing import Dict, Any


class BasePlugin(ABC):
    """Abstract Base Class that every Scout-AI plugin must implement."""
    name: str = "BasePlugin"
    description: str = "Plugin Description"

    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the plugin task and return structured results."""
        pass
