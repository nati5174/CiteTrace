"""Constructed study metadata and mocked observations; never empirical evidence."""

from datetime import UTC, timedelta

from citeprobe.analysis_models import StudyManifest
from citeprobe.lookup_inputs import fingerprint
from citeprobe.models import Dataset
from citeprobe.resolution_models import LookupBundle


def synthetic_study(
    dataset: Dataset,
    bundles: tuple[LookupBundle, ...],
    *,
    ages: tuple[int, ...] | None = None,
    hours: float = 1,
) -> StudyManifest:
    end = max(result.finished_at for bundle in bundles for result in bundle.results)
    reference = end.astimezone(UTC).date()
    ages = ages or tuple(3 for _ in dataset.citations)
    return StudyManifest.model_validate(
        {
            "dataset_fingerprint": fingerprint(dataset.model_dump(mode="json")),
            "citation_ids": [c.citation_id for c in dataset.citations],
            "sampling_method": "SIMULATED convenience sample; not observed research",
            "verification_method": "SIMULATED verification events and publication dates "
            "for software tests",
            "collection_started_at": (end - timedelta(hours=hours)).isoformat(),
            "collection_finished_at": end.isoformat(),
            "reference_date": reference.isoformat(),
            "lookup_bundle_ids": [
                fingerprint(bundle.model_dump(mode="json")) for bundle in bundles
            ],
            "preprint_dates": [
                {
                    "citation_id": c.citation_id,
                    "publication_date": (reference - timedelta(days=age)).isoformat(),
                    "provenance": c.provenance.model_dump(mode="json"),
                }
                for c, age in zip(dataset.citations, ages, strict=True)
            ],
        }
    )
