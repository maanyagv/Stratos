"""Data Ingestion subsystem for STRATOS.

Exports IngestionPipeline, DataSourceRegistry, DataValidator, and CoverageReporter.
"""

from stratos.ingestion.pipeline import IngestionPipeline, IngestionResult
from stratos.ingestion.registry import DataSourceRegistry
from stratos.ingestion.validator import CoverageReporter, DataValidator

__all__ = [
    "CoverageReporter",
    "DataSourceRegistry",
    "DataValidator",
    "IngestionPipeline",
    "IngestionResult",
]
