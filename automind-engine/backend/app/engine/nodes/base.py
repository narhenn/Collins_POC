from abc import ABC, abstractmethod


class BaseNodeExecutor(ABC):
    @abstractmethod
    async def execute(self, config: dict, variables: dict, **kwargs) -> dict:
        """Execute the node and return output variables."""
        pass
