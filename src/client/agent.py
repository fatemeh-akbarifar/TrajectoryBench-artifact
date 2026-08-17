from typing import List

from src.typings import AgentOutput


class AgentClient:
    def __init__(self, *args, **kwargs):
        pass

    def inference(self, history: List[dict]) -> str:
        raise NotImplementedError()

    def inference_with_metadata(self, history: List[dict]) -> AgentOutput:
        """Run inference while preserving compatibility with text-only agents."""
        return AgentOutput(content=self.inference(history))
