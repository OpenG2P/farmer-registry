"""Pure parsing/selection helpers for the cr_create flow.

Kept separate from cr_create_locustfile.py so the business logic of picking
a page/record/tab/section/field and computing the field's new value can be
read (and tested) independently of the actual HTTP calls.
"""
from __future__ import annotations

import random
import uuid
from typing import Any, Optional

from shared.config import HOUSEHOLD_IDS


def response_payload(response_json: dict) -> Any:
    return (response_json or {}).get("response_body", {}).get("response_payload")


def response_status(response_json: dict) -> Optional[str]:
    return (response_json or {}).get("response_header", {}).get("response_status")


def response_error_code(response_json: dict) -> Optional[str]:
    return (response_json or {}).get("response_header", {}).get("response_error_code")


def total_pages(search_response_json: dict) -> int:
    pagination = (search_response_json or {}).get("response_body", {}).get("pagination_response") or {}
    return pagination.get("number_of_pages") or 1


def choose_internal_record_id(search_response_json: dict) -> Optional[str]:
    results = response_payload(search_response_json) or []
    if not results:
        return None
    return random.choice(results)["internal_record_id"]


def extract_ordered_tab_ids(tabs_response_json: dict) -> list[str]:
    """tab_id list sorted ascending by tab_order, so tabs are visited in UI order."""
    tabs = response_payload(tabs_response_json) or []
    ordered_tabs = sorted(tabs, key=lambda tab: tab["tab_order"])
    return [tab["tab_id"] for tab in ordered_tabs]


def extract_tab_section_ids(tab_sections_response_json: dict) -> list[str]:
    """section_id list sorted ascending by section_order, for one tab."""
    sections = response_payload(tab_sections_response_json) or []
    ordered = sorted(sections, key=lambda section: section.get("section_order", 0))
    return [section["section_id"] for section in ordered]


def section_ui_schema_from_tab_sections(tab_sections_response_json: dict, section_id: str) -> dict:
    """section_ui_schema for one section, already embedded in get_tab_sections' response
    (section_data.section_ui_schema per tab-section) -- the real staff-portal UI reads it
    from there too, it doesn't call get_section_ui_schema separately. Reshaped into the
    same {'response_body': {'response_payload': {...}}} envelope static_enum_options /
    api_enum_attribute_id expect, so those helpers don't need to change.
    """
    sections = response_payload(tab_sections_response_json) or []
    for section in sections:
        if section.get("section_id") == section_id:
            section_data = section.get("section_data") or {}
            return {
                "response_body": {
                    "response_payload": {
                        "section_id": section_id,
                        "section_ui_schema": section_data.get("section_ui_schema"),
                    }
                }
            }
    return {}


def build_section_metadata(all_sections_response_json: dict) -> dict[str, dict]:
    """section_id -> {is_core_section, section_register_id, documents_required},
    from the register-wide section list (G2PRegisterSectionData)."""
    sections = response_payload(all_sections_response_json) or []
    return {
        section["section_id"]: {
            "is_core_section": bool(section.get("is_core_section")),
            "section_register_id": section.get("section_register_id"),
            "documents_required": bool(section.get("documents_required")),
        }
        for section in sections
    }


def old_field_value(
    tab_records_response_json: dict, section_register_id: str, field_name: str
) -> tuple[Optional[str], Any]:
    """(internal_record_id, current value) of field_name on the first record of this
    section's register group within a tab's get_tab_records response.

    get_tab_records groups records by section_register_id (sections sharing a
    register are deduplicated), not by section_id, so that's the match key.
    Returns (None, None) if the group or a record isn't there (e.g. no crop/
    land/livestock entry seeded yet for this record).
    """
    groups = response_payload(tab_records_response_json) or []
    for group in groups:
        if group.get("section_register_id") != section_register_id:
            continue
        records = group.get("records") or []
        if not records:
            return None, None
        record = records[0]
        return record.get("internal_record_id"), record.get(field_name)
    return None, None


def _find_widget(node: Any, field_name: str) -> Optional[dict]:
    if isinstance(node, dict):
        # plain-widget fields use widget-id; is_list sections render as a single
        # "table" widget whose per-column fields are keyed by column-key instead.
        if node.get("widget-id") == field_name or node.get("column-key") == field_name:
            return node
        for value in node.values():
            found = _find_widget(value, field_name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_widget(item, field_name)
            if found is not None:
                return found
    return None


def _widget_data_source(section_ui_schema_response_json: dict, field_name: str) -> Optional[dict]:
    payload = response_payload(section_ui_schema_response_json) or {}
    schema = payload.get("section_ui_schema") or {}
    widget = _find_widget(schema, field_name)
    if not widget:
        return None
    return widget.get("widget-data-source") or {}


def static_enum_options(section_ui_schema_response_json: dict, field_name: str) -> Optional[list[dict]]:
    """[{'label':..., 'value':...}, ...] for field_name, if its widget declares a static enum."""
    source = _widget_data_source(section_ui_schema_response_json, field_name)
    if source and source.get("type") == "static":
        return source.get("options")
    return None


def api_enum_attribute_id(section_ui_schema_response_json: dict, field_name: str) -> Optional[str]:
    """attribute_id for field_name's widget, if its allowed values come from get_attribute_values."""
    source = _widget_data_source(section_ui_schema_response_json, field_name)
    if source and source.get("type") == "api":
        return (source.get("params") or {}).get("attribute_id")
    return None


def attribute_value_options(attribute_values_response_json: dict) -> list[dict]:
    """get_attribute_values' response_payload, reshaped to the same {'label','value'} shape
    static_enum_options returns, keyed the way the widget's labelKey/valueKey (value_display/
    value_id) says to — so generate_new_value doesn't need to care which source produced it.
    """
    values = response_payload(attribute_values_response_json) or []
    return [{"label": value.get("value_display"), "value": value.get("value_id")} for value in values]


def generate_new_value(
    field_name: str,
    old_value: Any,
    enum_options: Optional[list[dict]],
    search_anchor: Optional[str] = None,
) -> Any:
    """A value guaranteed to differ from old_value where possible.

    When search_anchor is set, free-text values include it so
    search_in_change_request(`%<anchor>%`) finds CRs on non-farmer sections
    (land/crop/…), whose payload search_text would otherwise never contain
    the farmer first_name anchors from seed_manifest.
    """
    if enum_options:
        candidates = [option["value"] for option in enum_options if option.get("value") != old_value]
        return random.choice(candidates) if candidates else enum_options[0]["value"]
    if field_name == "link_internal_record_id":
        candidates = [household_id for household_id in HOUSEHOLD_IDS if household_id != old_value]
        return random.choice(candidates) if candidates else random.choice(HOUSEHOLD_IDS)
    if field_name == "head_count":
        candidates = [count for count in range(1, 21) if count != old_value]
        return random.choice(candidates)
    if field_name == "functional_record_id":
        return str(uuid.uuid4())
    suffix = f"{field_name}_updated_{random.randint(1000, 9999)}"
    if search_anchor:
        return f"{search_anchor}{suffix}"
    return suffix


def build_change_payload(internal_record_id: str, field_name: str, new_value: Any) -> list[dict]:
    return [{"internal_record_id": internal_record_id, "edit_action": "UPDATE", field_name: new_value}]
