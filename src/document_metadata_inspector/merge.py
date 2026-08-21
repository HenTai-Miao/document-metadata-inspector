"""Non-overwriting merge rules for independent parser evidence."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING

from document_metadata_inspector.models import (
    EvidenceObservation,
    EvidenceStatus,
    FrozenModel,
    ParserStatus,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from document_metadata_inspector.models import JsonValue, ParserRun


class MergedEvidence(FrozenModel):
    """Contain deterministic observations plus explicit coverage/conflict warnings."""

    observations: tuple[EvidenceObservation, ...] = ()
    warnings: tuple[str, ...] = ()


def _stable_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _observation_key(observation: EvidenceObservation) -> tuple[str, ...]:
    return (
        observation.canonical_name,
        observation.raw_name,
        _stable_json(observation.normalized_value),
        _stable_json(observation.raw_value),
        observation.value_type,
        observation.source_kind,
        observation.location,
        observation.parser_name,
        observation.parser_version,
    )


def _parser_warning(run: ParserRun) -> str:
    suffix = f":{run.error_code}" if run.error_code else ""
    return f"parser_status:{run.parser_name}:{run.status.value}{suffix}"


def _status_priority(status: EvidenceStatus) -> int:
    priorities = {
        EvidenceStatus.OBSERVED: 0,
        EvidenceStatus.CORROBORATED: 1,
        EvidenceStatus.CONFLICT: 2,
        EvidenceStatus.UNKNOWN: 3,
        EvidenceStatus.REDACTED: 4,
    }
    return priorities[status]


def _merge_duplicate(
    current: EvidenceObservation,
    duplicate: EvidenceObservation,
) -> EvidenceObservation:
    status = max((current.status, duplicate.status), key=_status_priority)
    warnings = tuple(sorted(set(current.warnings) | set(duplicate.warnings)))
    if status is current.status and warnings == current.warnings:
        return current
    return current.model_copy(update={"status": status, "warnings": warnings})


def _collect_unique(
    results: Sequence[ParserRun],
) -> tuple[list[EvidenceObservation], set[str]]:
    ordered_runs = sorted(
        results,
        key=lambda run: (run.parser_name, run.parser_version, run.status.value),
    )
    unique: dict[tuple[str, ...], EvidenceObservation] = {}
    warnings: set[str] = set()
    for run in ordered_runs:
        if run.status is not ParserStatus.SUCCEEDED:
            warnings.add(_parser_warning(run))
        warnings.update(
            f"parser_warning:{run.parser_name}:{warning}" for warning in run.warnings
        )
        for observation in sorted(run.observations, key=_observation_key):
            key = _observation_key(observation)
            current = unique.get(key)
            unique[key] = (
                observation
                if current is None
                else _merge_duplicate(current, observation)
            )
    return list(unique.values()), warnings


def _annotate_group(
    observations: list[EvidenceObservation],
    canonical_name: str,
    indexes: list[int],
    warnings: set[str],
) -> None:
    by_value: dict[str, list[int]] = defaultdict(list)
    for index in indexes:
        key = _stable_json(observations[index].normalized_value)
        by_value[key].append(index)

    corroborated = {
        index
        for value_indexes in by_value.values()
        if len({observations[item].parser_name for item in value_indexes}) > 1
        for index in value_indexes
    }
    parser_values: dict[str, set[str]] = defaultdict(set)
    for value, value_indexes in by_value.items():
        for index in value_indexes:
            parser_values[observations[index].parser_name].add(value)
    distinct_value_sets = {tuple(sorted(values)) for values in parser_values.values()}
    has_conflict = len(parser_values) > 1 and len(distinct_value_sets) > 1
    if has_conflict:
        warnings.add(f"parser_value_conflict:{canonical_name}")

    for index in indexes:
        observation = observations[index]
        status = observation.status
        item_warnings = set(observation.warnings)
        if index in corroborated:
            status = max(
                (status, EvidenceStatus.CORROBORATED),
                key=_status_priority,
            )
        elif has_conflict:
            status = max(
                (status, EvidenceStatus.CONFLICT),
                key=_status_priority,
            )
        if has_conflict:
            item_warnings.add("parser_value_conflict")
        if status is observation.status and item_warnings == set(observation.warnings):
            continue
        observations[index] = observation.model_copy(
            update={
                "status": status,
                "warnings": tuple(sorted(item_warnings)),
            }
        )


def _annotate_evidence(
    observations: list[EvidenceObservation],
    warnings: set[str],
) -> None:
    by_canonical: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, observation in enumerate(observations):
        embedded = (
            ".embedded." in observation.canonical_name
            or observation.location.startswith("embedded[")
            or observation.source_kind.endswith("_embedded")
        )
        namespace = f"embedded:{observation.location}" if embedded else "document"
        by_canonical[(observation.canonical_name, namespace)].append(index)
    for (canonical_name, _), indexes in by_canonical.items():
        _annotate_group(observations, canonical_name, indexes, warnings)


def merge_parser_results(results: Sequence[ParserRun]) -> MergedEvidence:
    """Deduplicate only identical provenance and retain every conflicting value."""
    observations, warnings = _collect_unique(results)
    _annotate_evidence(observations, warnings)

    observations.sort(key=_observation_key)
    return MergedEvidence(
        observations=tuple(observations),
        warnings=tuple(sorted(warnings)),
    )


__all__ = ("MergedEvidence", "merge_parser_results")
