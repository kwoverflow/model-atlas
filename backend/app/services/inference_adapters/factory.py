from __future__ import annotations

from app.services.inference_adapters.base import InferenceAdapter
from app.services.inference_adapters.mock import MockInferenceAdapter
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.validators import DomainValidationError


def get_inference_adapter(adapter_name: str) -> InferenceAdapter:
    match adapter_name:
        case "mock":
            return MockInferenceAdapter()
        case "openai_compatible":
            return OpenAICompatibleAdapter()
        case _:
            raise DomainValidationError(f"unsupported inference adapter: {adapter_name}")
