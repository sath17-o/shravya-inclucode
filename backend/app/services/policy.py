from abc import ABC, abstractmethod

from app.contracts.enums import ArtifactStatus, QualityStatus


class GenerationPolicyService(ABC):
    """Phase 1 boundary for central quality and stale-artifact authorization."""

    @abstractmethod
    def artifact_status(self, quality_status: QualityStatus, is_stale: bool) -> ArtifactStatus:
        raise NotImplementedError
