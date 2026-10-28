"""Éligibilité et conformité dérivée (RM-021, RM-030, RM-036, US-1.25 A2) : fonction pure."""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.assignment.eligibility import compliance, end_instant, evaluate
from app.fleet.contracts import DocumentFact, VehicleFacts
from app.workforce.contracts import DriverFacts, LicenseFact, QualificationFact

SITE = uuid.uuid4()
CATEGORY = uuid.uuid4()
CONAKRY, LAGOS = ZoneInfo("Africa/Conakry"), ZoneInfo("Africa/Lagos")
NOW = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)


def _vehicle(status: str = "AVAILABLE", licenses: frozenset[str] = frozenset({"C"})) -> VehicleFacts:
    return VehicleFacts(uuid.uuid4(), SITE, status, "P-1", CATEGORY, True, True, licenses)


def _driver(
    *,
    expiry: date = date(2030, 1, 1),
    license_status: str = "VALID",
    qualification_to: date | None = None,
    qualification_status: str = "VALID",
    qualification_site: uuid.UUID | None = None,
) -> DriverFacts:
    return DriverFacts(
        uuid.uuid4(),
        SITE,
        "ACTIVE",
        "NOM Prénom",
        "M-1",
        (LicenseFact(uuid.uuid4(), "C", license_status, date(2015, 1, 1), expiry),),
        (
            QualificationFact(
                uuid.uuid4(),
                CATEGORY,
                qualification_site,
                qualification_status,
                date(2020, 1, 1),
                qualification_to,
            ),
        ),
    )


def _codes(
    vehicle: VehicleFacts, driver: DriverFacts, end: datetime | None = None, tz: ZoneInfo = CONAKRY
) -> list[str]:
    ev = evaluate(vehicle, driver, start=NOW, end=end, tz=tz, warning_days=30)
    return [r.code for r in ev.reasons]


def test_eligible_pair_records_retained_documents() -> None:
    ev = evaluate(_vehicle(), _driver(), start=NOW, end=None, tz=CONAKRY, warning_days=30)
    assert ev.eligible and len(ev.license_ids) == 1 and len(ev.qualification_ids) == 1
    assert [(w.code, w.date) for w in ev.warnings] == [("NEXT_EXPIRY", date(2030, 1, 1))]


def test_qualification_expired_and_expires_before_end() -> None:
    assert _codes(_vehicle(), _driver(qualification_to=date(2026, 5, 31))) == ["DRIVER_QUALIFICATION_EXPIRED"]
    assert _codes(_vehicle(), _driver(qualification_status="REVOKED")) == ["DRIVER_QUALIFICATION_EXPIRED"]
    short = _driver(qualification_to=date(2026, 6, 10))
    assert _codes(_vehicle(), short, end=NOW + timedelta(days=20)) == [
        "DRIVER_QUALIFICATION_EXPIRES_BEFORE_END"
    ]
    other_site = _driver(qualification_site=uuid.uuid4())
    assert _codes(_vehicle(), other_site) == ["DRIVER_QUALIFICATION_MISSING"]


def test_end_boundary_follows_site_timezone() -> None:
    """Permis échu le 10/06 : valable jusqu'au 11/06 00:00 heure du site (RM-021, D-23)."""
    driver = _driver(expiry=date(2026, 6, 10))
    limit_lagos = end_instant(date(2026, 6, 10), LAGOS)  # 10/06 23:00 UTC
    assert _codes(_vehicle(), driver, end=limit_lagos, tz=LAGOS) == []
    assert _codes(_vehicle(), driver, end=limit_lagos + timedelta(seconds=1), tz=LAGOS) == [
        "DRIVER_LICENSE_EXPIRES_BEFORE_END"
    ]
    # Même fin, site à UTC+0 : encore couvert (la borne est une heure plus tard).
    assert _codes(_vehicle(), driver, end=limit_lagos + timedelta(seconds=1), tz=CONAKRY) == []


def test_statuses_and_category_without_driver() -> None:
    vehicle = VehicleFacts(uuid.uuid4(), SITE, "IN_MAINTENANCE", "P-2", CATEGORY, False, False, frozenset())
    driver = _driver()
    driver = DriverFacts(
        driver.driver_id, SITE, "SUSPENDED", "N", "M", driver.licenses, driver.authorizations
    )
    assert _codes(vehicle, driver) == [
        "DRIVER_NOT_ACTIVE",
        "VEHICLE_NOT_AVAILABLE",
        "VEHICLE_CATEGORY_WITHOUT_DRIVER",
    ]


def test_compliance_flips_when_license_expires_during_assignment() -> None:
    """US-1.25 A2 : franchir l'échéance avec l'horloge injectée rend l'affectation non conforme."""
    driver = _driver(expiry=date(2026, 6, 10))
    before = compliance(
        _vehicle(), driver, now=datetime(2026, 6, 10, 23, 59, tzinfo=UTC), tz=CONAKRY, warning_days=30
    )
    after = compliance(
        _vehicle(), driver, now=datetime(2026, 6, 11, 0, 0, tzinfo=UTC), tz=CONAKRY, warning_days=30
    )
    assert before == ([], before[1]) and [w.code for w in before[1]] == ["LICENSE_EXPIRING"]
    assert [r.code for r in after[0]] == ["LICENSE_EXPIRED"]
    revoked = _driver(qualification_status="REVOKED")
    assert [r.code for r in compliance(_vehicle(), revoked, now=NOW, tz=CONAKRY, warning_days=30)[0]] == [
        "QUALIFICATION_EXPIRED"
    ]


# --- Documents exigés du véhicule (D-42) -----------------------------------------------------------------


def _with_documents(*docs: DocumentFact, block_missing: bool = False) -> VehicleFacts:
    return replace(
        _vehicle(),
        required_documents=frozenset({"INSURANCE", "REGISTRATION"}),
        documents=docs,
        missing_documents_block=block_missing,
    )


def _doc(doc_type: str, until: date | None, status: str = "VALID") -> DocumentFact:
    return DocumentFact(uuid.uuid4(), doc_type, status, None, until)


def test_undated_document_never_covers_a_required_type() -> None:
    """Défense en profondeur : seule la carte grise peut être sans échéance (revue de 0016)."""
    vehicle = _with_documents(_doc("INSURANCE", None), _doc("REGISTRATION", None))
    ev = evaluate(vehicle, _driver(), start=NOW, end=None, tz=CONAKRY, warning_days=30)
    assert [r.code for r in ev.reasons] == ["VEHICLE_DOCUMENT_EXPIRED"]


def test_missing_document_warns_or_blocks_by_policy() -> None:
    dated = _doc("INSURANCE", date(2030, 1, 1))
    warn = evaluate(_with_documents(dated), _driver(), start=NOW, end=None, tz=CONAKRY, warning_days=30)
    assert warn.eligible and "VEHICLE_DOCUMENT_MISSING" in [w.code for w in warn.warnings]
    block = evaluate(
        _with_documents(dated, block_missing=True),
        _driver(),
        start=NOW,
        end=None,
        tz=CONAKRY,
        warning_days=30,
    )
    assert [r.code for r in block.reasons] == ["VEHICLE_DOCUMENT_MISSING"]
