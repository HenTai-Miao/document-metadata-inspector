"""Isolated external metadata parser adapters."""

from document_metadata_inspector.workers.apache import ApacheWorker
from document_metadata_inspector.workers.exiftool import ExifToolWorker

__all__ = ("ApacheWorker", "ExifToolWorker")
