from datetime import date, datetime

from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException


def validation_error(message: str) -> None:
    raise G2PRegistryException(
        code=G2PRegistryErrorCodes.REQUEST_VALIDATION_ERROR.value[1],
        message=message,
    )


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_bool(value) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return bool(value)


def is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def fallback_record_name(payload: dict, label: str) -> str:
    """Name for a payload carrying none of the domain's naming fields.

    A DELETE-only change request only carries internal_record_id, and the
    platform renders an empty record_name as "-". Prefer the functional id,
    then a short internal id, so the change request list still says what it is.
    """
    for key in ("functional_record_id", "internal_record_id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return f"{label} {value[:8]}"
    return label


def validate_enum_values(record: dict, fields: dict) -> None:
    """Reject coded values the register model will not accept.

    The platform only validates the row against the pydantic schema when the
    change request is APPROVED (inside the AWE webhook), where a bad code makes
    the approval fail silently and the request stays PENDING forever. Checking
    here surfaces the problem at save time instead. `fields` maps field name
    to its Enum class; blank values are ignored.
    """
    for field, enum_cls in fields.items():
        if field not in record or is_blank(record.get(field)):
            continue
        allowed = {item.value for item in enum_cls}
        if str(record.get(field)) not in allowed:
            validation_error(f"{field} must be one of " + ", ".join(sorted(allowed)))
