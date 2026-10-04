from dataclasses import dataclass
from datetime import date

from openg2p_registry_core.models import ChangeActionEnum, GenderEnum, RecordStatusEnum
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain_validation_utils import as_int, parse_date

CHILDREN_MAX_AGE = 17
ELDERLY_MIN_AGE = 60

ROSTER_AFFECTING_FIELDS = frozenset(
    {
        "link_internal_record_id",
        "record_status",
        "birth_date",
        "estimated_age",
        "gender",
    }
)

CHANGED_PERSON_KIND_MEMBER = "member"
CHANGED_PERSON_KIND_FARMER = "farmer"


@dataclass(frozen=True)
class HouseholdRosterAggregates:
    size_of_group: int
    number_of_children: int
    number_of_elderly_members: int
    number_of_female_members: int
    number_of_male_members: int


def normalize_link(value) -> str | None:
    if value is None or value == "":
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _gender_value(value) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "value"):
        value = value.value
    normalized = str(value).strip().upper()
    return normalized or None


def has_roster_affecting_changes(change_payload: dict) -> bool:
    return any(key in change_payload for key in ROSTER_AFFECTING_FIELDS)


def person_payload(existing: dict, change_payload: dict) -> dict:
    overlay = {
        key: value
        for key, value in change_payload.items()
        if key in ROSTER_AFFECTING_FIELDS
        or key in {"internal_record_id", "foundational_id", "first_name", "last_name"}
    }
    return {**existing, **overlay}


def affected_household_ids(old_link: str | None, new_link: str | None) -> set[str]:
    household_ids: set[str] = set()
    if old_link:
        household_ids.add(old_link)
    if new_link:
        household_ids.add(new_link)
    return household_ids


def calculate_age(birth_date: date, today: date | None = None) -> int | None:
    if not birth_date:
        return None
    today = today or date.today()
    return (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )


def resolve_person_age(person: dict, today: date | None = None) -> int | None:
    birth_date = parse_date(person.get("birth_date"))
    if birth_date is not None:
        return calculate_age(birth_date, today)
    return as_int(person.get("estimated_age"))


def is_active_person(person: dict) -> bool:
    record_status = person.get("record_status") or RecordStatusEnum.ACTIVE.value
    if hasattr(record_status, "value"):
        record_status = record_status.value
    return str(record_status).strip().upper() == RecordStatusEnum.ACTIVE.value


def roster_identity_key(person: dict) -> str:
    foundational_id = _normalize_text(person.get("foundational_id"))
    if foundational_id:
        return f"id:{foundational_id}"
    first_name = _normalize_text(person.get("first_name"))
    last_name = _normalize_text(person.get("last_name"))
    birth_date = parse_date(person.get("birth_date"))
    birth_key = birth_date.isoformat() if birth_date else ""
    if first_name or last_name or birth_key:
        return f"person:{first_name}|{last_name}|{birth_key}"
    record_id = person.get("internal_record_id")
    return f"record:{record_id}" if record_id else f"anon:{id(person)}"


def union_roster_people(
    members: list[dict],
    farmers: list[dict],
    *,
    overlay_person: dict | None = None,
    overlay_household_id: str | None = None,
) -> list[dict]:
    by_key: dict[str, dict] = {}
    for farmer in farmers:
        if not is_active_person(farmer):
            continue
        by_key[roster_identity_key(farmer)] = farmer
    for member in members:
        if not is_active_person(member):
            continue
        by_key[roster_identity_key(member)] = member
    if (
        overlay_person
        and is_active_person(overlay_person)
        and normalize_link(overlay_person.get("link_internal_record_id")) == overlay_household_id
    ):
        by_key[roster_identity_key(overlay_person)] = overlay_person
    return list(by_key.values())


def compute_household_roster_counts(
    people: list[dict],
    today: date | None = None,
) -> HouseholdRosterAggregates:
    size_of_group = 0
    number_of_children = 0
    number_of_elderly_members = 0
    number_of_male_members = 0
    number_of_female_members = 0

    for person in people:
        if not is_active_person(person):
            continue

        size_of_group += 1
        age = resolve_person_age(person, today)
        if age is not None:
            if age <= CHILDREN_MAX_AGE:
                number_of_children += 1
            if age >= ELDERLY_MIN_AGE:
                number_of_elderly_members += 1

        gender = _gender_value(person.get("gender"))
        if gender == GenderEnum.MALE.value:
            number_of_male_members += 1
        elif gender == GenderEnum.FEMALE.value:
            number_of_female_members += 1

    return HouseholdRosterAggregates(
        size_of_group=size_of_group,
        number_of_children=number_of_children,
        number_of_elderly_members=number_of_elderly_members,
        number_of_female_members=number_of_female_members,
        number_of_male_members=number_of_male_members,
    )


def apply_household_roster_counts(household, aggregates: HouseholdRosterAggregates) -> None:
    household.size_of_group = aggregates.size_of_group
    household.number_of_children = aggregates.number_of_children
    household.number_of_elderly_members = aggregates.number_of_elderly_members
    household.number_of_female_members = aggregates.number_of_female_members
    household.number_of_male_members = aggregates.number_of_male_members


def _apply_changed_person(
    store: dict[str, dict],
    person_id: str | None,
    payload: dict | None,
    household_id: str,
    deleted: bool,
) -> None:
    if not person_id:
        if deleted or payload is None:
            return
        person_id = str(payload.get("internal_record_id") or roster_identity_key(payload))
    if deleted:
        store.pop(person_id, None)
        return
    if payload is None:
        return
    effective_link = normalize_link(payload.get("link_internal_record_id"))
    if effective_link == household_id and is_active_person(payload):
        store[person_id] = payload
    elif person_id in store:
        del store[person_id]


async def recompute_household_roster_for_household(
    session: AsyncSession,
    household_internal_record_id: str,
    *,
    changed_person_id: str | None = None,
    changed_person_payload: dict | None = None,
    changed_person_deleted: bool = False,
    changed_person_kind: str | None = None,
) -> None:
    from ...models.farmer import G2PRegisterFarmer
    from ...models.household import G2PRegisterHousehold
    from ...models.household_member import G2PRegisterHouseholdMember

    household = await session.get(G2PRegisterHousehold, household_internal_record_id)
    if not household:
        return

    members_result = await session.execute(
        select(G2PRegisterHouseholdMember).where(
            G2PRegisterHouseholdMember.link_internal_record_id == household_internal_record_id
        )
    )
    members_by_id = {
        member.internal_record_id: member.to_dict()
        for member in members_result.scalars().all()
    }

    farmers_result = await session.execute(
        select(G2PRegisterFarmer).where(
            G2PRegisterFarmer.link_internal_record_id == household_internal_record_id
        )
    )
    farmers_by_id = {
        farmer.internal_record_id: farmer.to_dict()
        for farmer in farmers_result.scalars().all()
    }

    if changed_person_kind == CHANGED_PERSON_KIND_FARMER:
        _apply_changed_person(
            farmers_by_id,
            changed_person_id,
            changed_person_payload,
            household_internal_record_id,
            changed_person_deleted,
        )
    elif changed_person_kind == CHANGED_PERSON_KIND_MEMBER:
        _apply_changed_person(
            members_by_id,
            changed_person_id,
            changed_person_payload,
            household_internal_record_id,
            changed_person_deleted,
        )

    people = union_roster_people(
        list(members_by_id.values()),
        list(farmers_by_id.values()),
        overlay_person=None if changed_person_deleted else changed_person_payload,
        overlay_household_id=household_internal_record_id,
    )
    aggregates = compute_household_roster_counts(people)
    apply_household_roster_counts(household, aggregates)


async def recompute_household_for_ingested_row(session: AsyncSession, register_row) -> None:
    link_internal_record_id = normalize_link(
        getattr(register_row, "link_internal_record_id", None)
    )
    if not link_internal_record_id:
        return
    await recompute_household_roster_for_household(session, link_internal_record_id)


async def recompute_households_for_change_request(
    session: AsyncSession,
    change_request,
    *,
    model,
    changed_person_kind: str,
) -> None:
    from openg2p_registry_core.models import G2PRegisterChangeRequestPayload

    payload_obj = await session.get(
        G2PRegisterChangeRequestPayload, change_request.change_request_id
    )
    if not payload_obj or not payload_obj.change_payload:
        return

    records = payload_obj.change_payload
    if isinstance(records, dict):
        records = [records]

    for record in records:
        if not isinstance(record, dict):
            continue
        action = record.get("edit_action")
        if action == ChangeActionEnum.NO_CHANGE.value:
            continue

        record_id = record.get("internal_record_id") or change_request.internal_record_id
        existing = await session.get(model, record_id) if record_id else None
        existing_dict = existing.to_dict() if existing else {}

        if action not in {
            ChangeActionEnum.ADD.value,
            ChangeActionEnum.DELETE.value,
        } and not has_roster_affecting_changes(record):
            continue

        old_link = normalize_link(existing_dict.get("link_internal_record_id"))
        if action == ChangeActionEnum.DELETE.value:
            household_ids = {old_link} if old_link else set()
            merged = person_payload(existing_dict, record) if existing_dict else dict(record)
            deleted = True
        else:
            merged = person_payload(existing_dict, record) if existing_dict else dict(record)
            if record_id and not merged.get("internal_record_id"):
                merged["internal_record_id"] = record_id
            if "link_internal_record_id" in record:
                new_link = normalize_link(record.get("link_internal_record_id"))
            else:
                new_link = old_link or normalize_link(merged.get("link_internal_record_id"))
            household_ids = affected_household_ids(old_link, new_link)
            deleted = not is_active_person(merged)

        if not household_ids:
            continue

        overlay_person_id = merged.get("internal_record_id") or record_id
        for household_id in household_ids:
            await recompute_household_roster_for_household(
                session,
                household_id,
                changed_person_id=overlay_person_id,
                changed_person_payload=merged,
                changed_person_deleted=deleted,
                changed_person_kind=changed_person_kind,
            )
