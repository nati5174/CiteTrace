"""Approved research-volume scope; historical main-only parsing stays unchanged."""

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from citeprobe.acquisition_sources import ACLXml, text, xml_root
from citeprobe.pilot_models import PilotItem, PilotRequest

POLICY_ID = "B-ACL-S1-v1"
POLICY_PATH = "docs/research/amendments/b-acl-frame-v1.json"
FIXED = {"P18": ("1",), "P19": ("1",), "2020.acl": ("main",), "2021.acl": ("long", "short")}
EXCLUDED_LABELS = (
    "findings",
    "demonstration",
    "workshop",
    "tutorial",
    "industry",
    "student research",
    "demo",
    "industrial",
)


@dataclass(frozen=True)
class ScopedCollection:
    items: tuple[PilotItem, ...]
    selected_volume_ids: tuple[str, ...]
    excluded_volume_ids: tuple[str, ...]
    source_record_volumes: dict[str, str]


def scoped_collection(body: str, row: PilotRequest, *, limit: int = 2_000_000) -> ScopedCollection:
    from citeprobe.source_limits import validate_request_limit

    validate_request_limit(row.request, limit)
    root = xml_root(body, preserve_comments=True, limit=limit)
    if root.tag != "collection" or root.get("id") != row.collection:
        raise ValueError("Amended scope: pinned collection identity mismatch")
    volumes = root.findall("volume")
    names = [v.get("id") for v in volumes]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("Amended scope: missing or duplicate volume IDs")
    collection = row.collection
    if collection in FIXED:
        selected = FIXED[collection]
        if collection == "2021.acl" and "main" in names:
            raise ValueError("Amended scope: competing 2021 research representation")
    elif collection in {"2022.acl", "2023.acl"}:
        if "main" in names and not ({"long", "short"} & set(names)):
            selected = ("main",)
        elif "main" not in names and {"long", "short"} <= set(names):
            selected = ("long", "short")
        else:
            raise ValueError("Amended scope: ambiguous or incomplete research volume structure")
    else:
        raise ValueError("Collection outside the approved scope amendment")
    if not set(selected) <= set(names):
        raise ValueError("Amended scope: required explicit research volume missing")
    items = []
    record_volumes = {}
    for name in selected:
        volume = next(v for v in volumes if v.get("id") == name)
        title = text(volume, "meta/booktitle").casefold()
        venue = text(volume, "meta/venue").casefold()
        expected_year = {"P18": "2018", "P19": "2019"}.get(collection, collection[:4])
        if (
            volume.get("type") != "proceedings"
            or "annual meeting" not in title
            or "association for computational linguistics" not in title
            or any(label in title or label in venue for label in EXCLUDED_LABELS)
            or text(volume, "meta/year") != expected_year
        ):
            raise ValueError("Amended scope: research proceedings metadata is missing or ambiguous")
        filtered = ET.Element("collection", root.attrib)
        filtered.append(volume)
        records, count = ACLXml().records(
            ET.tostring(filtered, encoding="unicode"), xml_limit=limit
        )
        if not count:
            raise ValueError("Amended scope: empty selected research volume")
        for record in records:
            candidate = ACLXml().candidate(record)
            if not 2018 <= candidate.year <= 2023:
                raise ValueError("Amended scope: canonical year outside B eligibility")
            key = "acl:" + candidate.source_record_id
            if key in record_volumes:
                raise ValueError("Amended scope: duplicate source record ID; never merge")
            record_volumes[key] = name
            items.append(
                PilotItem(
                    source_id=key, group=row.group, candidate=candidate, run_request_key=row.key
                )
            )
    return ScopedCollection(
        tuple(items), selected, tuple(str(n) for n in names if n not in selected), record_volumes
    )
