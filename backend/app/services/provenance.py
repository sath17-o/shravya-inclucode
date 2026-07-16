from abc import ABC, abstractmethod


class ProvenanceService(ABC):
    """Phase 1 boundary for recording source links on generated artifacts."""

    @abstractmethod
    def mark_dependents_stale(self, source_id: str, reason: str) -> int:
        raise NotImplementedError
