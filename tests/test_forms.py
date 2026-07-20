import json

import pytest

from jcvb import forms


def _slugs():
    return forms.form_slugs()


def _rui(slug):
    return forms.load_form_config(slug)["anvilor_form"]["display_config"]


def test_form_configs_exist():
    assert "camp-feedback-2026" in _slugs()


@pytest.mark.parametrize("slug", _slugs())
def test_form_config_validates(slug):
    assert forms.validate_form_config(forms.load_form_config(slug)) == []


def test_camp_feedback_is_v0_standard_layout():
    """We publish the legacy (v0) shape — it's what the live renderer uses —
    and must NOT carry a v1 rui_config (the renderer would prefer it)."""
    dc = _rui("camp-feedback-2026")
    assert "rui_config" not in dc
    root = dc["rui_generation"]["raw_generator_data"]["root_control"]
    assert root["control"] == "anvilor_forms:standard_layout"


def test_camp_feedback_has_brand_gradient_background():
    dc = _rui("camp-feedback-2026")
    bg = dc.get("background_color", "")
    assert "linear-gradient" in bg
    assert "#0A0203" in bg and "#C4B781" in bg


def test_camp_feedback_allows_anonymous_submissions():
    doc = forms.load_form_config("camp-feedback-2026")
    assert doc["anvilor_form"]["disable_anonymous_submissions"] is False


def test_registry_is_valid_json_when_present():
    if forms.REGISTRY_PATH.exists():
        registry = json.loads(forms.REGISTRY_PATH.read_text())
        for slug, entry in registry.items():
            assert slug in _slugs()
            assert entry["url"].startswith(forms.FORMS_URL)


def test_v0_validation_catches_unknown_control_and_missing_field():
    doc = forms.load_form_config("camp-feedback-2026")
    root = doc["anvilor_form"]["display_config"]["rui_generation"][
        "raw_generator_data"
    ]["root_control"]
    # break a select's control name and strip a field binding (body_controls
    # interleave raw_content labels with the field controls, so fields are odd
    # indices under each panel)
    overall = root["items"][1]["body_controls"][1]
    assert overall["control"] == "button_toggle"
    overall["control"] = "bogus_control"
    liked_most = root["items"][2]["body_controls"][1]
    assert liked_most["control"] == "multi_line_text"
    del liked_most["field"]
    errors = forms.validate_form_config(doc)
    assert any("unknown control" in e for e in errors)
    assert any("requires a 'field'" in e for e in errors)


def test_v1_validation_still_supported():
    """The validator dispatches on shape; a minimal v1 config still checks out."""
    doc = {
        "anvilor_form": {
            "title": "t",
            "display_config": {
                "rui_config": {
                    "rui_version": "v1",
                    "model": {"type": "object", "properties": {"a": {"type": "string"}}},
                    "form": {
                        "control": "vbox",
                        "items": [{"control": "single_line_text", "field": "/a"}],
                    },
                }
            },
        }
    }
    assert forms.validate_form_config(doc) == []
