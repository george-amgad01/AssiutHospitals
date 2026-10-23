"""Emergency-department capacity and specialties.

قدرة أقسام الطوارئ والتخصصات المتاحة في كل مستشفى.

OSM does not publish the number of free emergency places or the specialty
list, so this data comes from a separate file.  The repository ships a
**SYNTHETIC** file (clearly labelled) so the tool can be exercised; replacing
it with real owner-provided values requires no code change.

بيانات OSM لا تحتوي على عدد الأماكن الشاغرة أو التخصصات، لذلك تُقرأ من ملف
منفصل. الملف المرفق وصفي (SYNTHETIC) وموسوم بوضوح، ويمكن استبداله ببيانات
حقيقية دون تغيير الكود.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Set

from .dataset import Dataset, HospitalRecord


@dataclass(frozen=True)
class Capacity:
    """One facility's emergency state."""

    slug: str
    emergency_department: bool
    beds_total: int
    beds_free: int
    specialties: FrozenSet[str]
    note: str = ""

    @property
    def has_free_place(self) -> bool:
        """Is at least one emergency place currently free?

        هل يوجد مكان شاغر في قسم الطوارئ الآن؟
        """
        return self.emergency_department and self.beds_free > 0

    def has_specialty(self, specialty: str) -> bool:
        """Does the facility provide ``specialty``?

        هل يتوفر التخصص المطلوب؟
        """
        return specialty in self.specialties

    def as_dict(self) -> Dict[str, object]:
        return {
            "slug": self.slug,
            "emergency_department": self.emergency_department,
            "beds_total": self.beds_total,
            "beds_free": self.beds_free,
            "specialties": sorted(self.specialties),
            "note": self.note,
        }


@dataclass
class CapacityBook:
    """All capacity records plus the provenance of the data."""

    source: str = "UNSET"
    notice: str = ""
    catalog: List[str] = field(default_factory=list)
    by_slug: Dict[str, Capacity] = field(default_factory=dict)
    clinics_as_emergency: bool = True
    errors: List[str] = field(default_factory=list)

    @property
    def synthetic(self) -> bool:
        """True when the values are synthetic (must be shown in every output).

        هل البيانات وصفية (غير حقيقية)؟ يجب إظهار ذلك في كل مخرجات.
        """
        return self.source.upper().startswith("SYNTHETIC")

    def get(self, slug: str) -> Optional[Capacity]:
        return self.by_slug.get(slug)

    def effective_emergency(self, record: HospitalRecord) -> bool:
        """Emergency capability after applying the clinic policy.

        القدرة على استقبال الطوارئ بعد تطبيق سياسة العيادات.
        """
        capacity = self.by_slug.get(record.slug)
        if capacity is None or not capacity.emergency_department:
            return False
        if record.hospital.category == "clinic" and not self.clinics_as_emergency:
            return False
        return True

    def as_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "notice": self.notice,
            "synthetic": self.synthetic,
            "catalog": list(self.catalog),
            "clinics_as_emergency": self.clinics_as_emergency,
            "errors": list(self.errors),
        }


def load_capacity(
    path: Path,
    dataset: Dataset,
    clinics_as_emergency: bool = True,
) -> CapacityBook:
    """Load and validate ``data/emergency_capacity.json``.

    يقرأ الملف ويتحقق من وجود كل مستشفى، ومنطقية الأرقام، وصحة التخصصات.
    الأخطاء تُعاد في ``book.errors`` ولا تُصلح تلقائياً.
    """
    with open(path, "r", encoding="utf-8-sig") as fh:
        raw = json.load(fh)

    book = CapacityBook(
        source=str(raw.get("source", "UNSET")),
        notice=str(raw.get("notice", "")),
        catalog=[str(item) for item in (raw.get("specialties_catalog") or [])],
        clinics_as_emergency=clinics_as_emergency,
    )
    catalog: Set[str] = set(book.catalog)
    known_slugs = {record.slug for record in dataset.hospitals}

    items = raw.get("hospitals") or {}
    for slug, item in items.items():
        specialties = frozenset(str(s) for s in (item.get("specialties") or []))
        capacity = Capacity(
            slug=str(slug),
            emergency_department=bool(item.get("emergency_department", True)),
            beds_total=int(item.get("beds_total", 0)),
            beds_free=int(item.get("beds_free", 0)),
            specialties=specialties,
            note=str(item.get("note", "")),
        )
        book.by_slug[capacity.slug] = capacity

        if slug not in known_slugs:
            book.errors.append("capacity entry for unknown hospital: {0}".format(slug))
        if capacity.beds_total < 0 or capacity.beds_free < 0:
            book.errors.append("{0}: negative bed count".format(slug))
        if capacity.beds_free > capacity.beds_total:
            book.errors.append(
                "{0}: beds_free ({1}) exceeds beds_total ({2})".format(
                    slug, capacity.beds_free, capacity.beds_total
                )
            )
        unknown = specialties - catalog
        if unknown:
            book.errors.append(
                "{0}: specialties not in catalog: {1}".format(
                    slug, ", ".join(sorted(unknown))
                )
            )

    for record in dataset.hospitals:
        if record.slug not in book.by_slug:
            book.errors.append("missing capacity entry: {0}".format(record.slug))

    return book
