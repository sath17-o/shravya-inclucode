from abc import ABC, abstractmethod

from app.core.config import ProviderMode


class Provider(ABC):
    @property
    @abstractmethod
    def mode(self) -> ProviderMode:
        raise NotImplementedError
