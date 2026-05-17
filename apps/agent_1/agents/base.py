from abc import ABC, abstractmethod


class BaseAgent(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, context: dict) -> str:
        """Run the agent with the given alert context. Returns analysis string."""
        pass
