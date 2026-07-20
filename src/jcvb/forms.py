"""Anvilor Forms management from the command line.

Form configs are committed JSON documents in forms/<slug>.json — the shape
stored on the ``anvilor_forms`` collection: ``{"anvilor_form": {...}}`` with
the visual config at ``display_config.rui_config`` (the ngx-rui v1 shape:
``{rui_version, model, form}``). Published form OIDs are recorded in
forms/registry.json — commit it after publishing.

Usage:
    uv run python -m jcvb.forms list
    uv run python -m jcvb.forms validate camp-feedback-2026
    uv run python -m jcvb.forms publish camp-feedback-2026
    uv run python -m jcvb.forms url camp-feedback-2026
    uv run python -m jcvb.forms responses camp-feedback-2026

Auth: ANVILOR_API_KEY + ANVILOR_ORG_OID in .env (see .env.example). The API
is plain REST (api-key/org-oid headers), so no anvilor client package is
needed. Eel-operator calls (publish_live) take BSON extended JSON — ObjectIds
travel as {"$oid": "..."}.
"""

import argparse
import json
import os

import requests
from dotenv import dotenv_values

from jcvb._consts import REPO_ROOT

API_BASE = "https://api.anvilor.com"
FORMS_URL = "https://forms.anvilor.com"

FORMS_DIR = REPO_ROOT / "forms"
REGISTRY_PATH = FORMS_DIR / "registry.json"

_FORMS_COLLECTION = "anvilor_forms"
_RESPONSES_COLLECTION = "anvilor_form_responses"
_TIMEOUT_SECONDS = 120


# --- config / registry -----------------------------------------------------


def _auth_headers() -> dict:
    dotenv_vals = dotenv_values(REPO_ROOT / ".env")
    values = {}
    missing = []
    for name in ("ANVILOR_API_KEY", "ANVILOR_ORG_OID"):
        value = os.environ.get(name, dotenv_vals.get(name))
        if not value or value == "REPLACE_ME":
            missing.append(name)
        values[name] = value
    if missing:
        raise SystemExit(
            f"Missing {', '.join(missing)} — set real values in .env "
            "(never commit them; provision the key from the Anvilor portal)."
        )
    return {
        "anvilor-api-key": values["ANVILOR_API_KEY"],
        "anvilor-org-oid": values["ANVILOR_ORG_OID"],
    }


def form_slugs() -> list[str]:
    return sorted(p.stem for p in FORMS_DIR.glob("*.json") if p.stem != "registry")


def load_form_config(slug: str) -> dict:
    path = FORMS_DIR / f"{slug}.json"
    if not path.exists():
        raise SystemExit(f"No such form config: {path} (have: {form_slugs()})")
    return json.loads(path.read_text())


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text())


def record_form_oid(slug: str, form_oid: str) -> None:
    registry = load_registry()
    registry[slug] = {"form_oid": form_oid, "url": f"{FORMS_URL}/{form_oid}"}
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")


def live_url(slug: str) -> str | None:
    entry = load_registry().get(slug)
    return entry["url"] if entry else None


# --- API calls ---------------------------------------------------------------


def _check(result: requests.Response, what: str) -> None:
    if not result.ok:
        raise SystemExit(f"{what} failed ({result.status_code}): {result.text[:300]}")


def create_form(headers: dict, form_config: dict) -> str:
    result = requests.post(
        f"{API_BASE}/api/collections/{_FORMS_COLLECTION}/documents",
        headers=headers,
        json={"data": form_config},
        timeout=_TIMEOUT_SECONDS,
    )
    _check(result, "create_form")
    doc = result.json()["doc"]
    oid = doc.get("_id", {}).get("$oid") if isinstance(doc.get("_id"), dict) else doc.get("_id")
    if not oid:
        raise SystemExit(f"Form created but no _id in response: {doc}")
    return oid


def update_form(headers: dict, form_oid: str, form_config: dict) -> None:
    result = requests.patch(
        f"{API_BASE}/api/collections/{_FORMS_COLLECTION}/documents/{form_oid}",
        headers=headers,
        json={"update_dict": {"/anvilor_form": form_config["anvilor_form"]}},
        timeout=_TIMEOUT_SECONDS,
    )
    _check(result, "update_form")


def publish_form(headers: dict, form_oid: str, notes: str) -> None:
    # eval endpoint takes BSON extended JSON — the ObjectId as {"$oid": ...}
    result = requests.post(
        f"{API_BASE}/api/collections/{_FORMS_COLLECTION}/eval",
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps(
            {
                "operator_name": "publish_live",
                "args": {
                    "doc_oid": {"$oid": form_oid},
                    "deployment_key": "live",
                    "notes": notes,
                },
            }
        ),
        timeout=_TIMEOUT_SECONDS,
    )
    _check(result, "publish_live")


def fetch_responses(headers: dict, form_oid: str) -> list[dict]:
    docs, page_num, page_data = [], 1, {}
    while True:
        result = requests.get(
            f"{API_BASE}/api/collections/{_RESPONSES_COLLECTION}/documents",
            headers=headers,
            params={
                "target_page_num": page_num,
                "page_data": json.dumps(page_data),
                "criteria": json.dumps(
                    {"response.anvilor_form_oid": {"$oid": form_oid}}
                ),
            },
            timeout=_TIMEOUT_SECONDS,
        )
        _check(result, "fetch_responses")
        payload = result.json()
        docs.extend(payload["docs"])
        page_data = payload["page_data"]
        if len(payload["docs"]) < page_data.get("page_size", 0):
            return docs
        page_num += 1


# --- local validation --------------------------------------------------------
# Mirrors the platform's vocabulary + consistency rules so a bad config fails
# here instead of rendering broken. Two shapes are supported:
#   * v1 (display_config.rui_config = {rui_version, model, form}) — the newer
#     ngx-rui instance config; the live renderer *prefers* it when present.
#   * v0 (display_config.rui_generation, raw generator → root_control) — the
#     legacy ngx-rui shape built around anvilor_forms:standard_layout. This is
#     what actually renders live today, so it's the default we publish.

# --- v1 ngx-rui vocabulary
_V1_KINDS = {
    "vbox": "layout",
    "hbox": "layout",
    "panel": "layout",
    "tabs": "layout",
    "iterative_cards": "iterative",
    "iterative_sidebar": "iterative",
    "raw_content": "display",
    "button": "display",
    "single_line_text": "input",
    "multi_line_text": "input",
    "standard_number": "input",
    "numeric_stepper": "input",
    "standard_us_phone": "input",
    "standard_checkbox": "input",
    "standard_date": "input",
    "standard_datetime": "input",
    "standard_file_upload": "input",
    "standard_address": "input",
    "single_select_dropdown": "select",
    "multi_select_dropdown": "select",
    "standard_radio_buttons": "select",
    "multi_select_checkboxes": "select",
    "button_toggle": "select",
    "likert": "likert",  # select-ish, but takes rows + scale
}

# --- v0 ngx-rui vocabulary (superset used by the legacy renderer)
_V0_KINDS = {
    "anvilor_forms:standard_layout": "layout",
    "anvilor_forms:form_layout": "layout",
    "anvilor_forms:submit_button_panel": "layout",
    "panel": "layout",
    "flexbox": "layout",
    "raw_content": "display",
    "button": "display",
    "anvilor_forms:submit_button": "display",
    "single_line_text": "input",
    "multi_line_text": "input",
    "standard_number": "input",
    "numeric_stepper": "input",
    "standard_us_phone": "input",
    "standard_checkbox": "input",
    "standard_date": "input",
    "standard_datetime": "input",
    "file_attachment": "input",
    "standard_address": "input",  # binds via base_field_path, not field
    "single_select_dropdown": "select",
    "multi_select_dropdown": "select",
    "standard_radio_buttons": "select",
    "multi_select_checkboxes": "select",
    "button_toggle": "select",
    "likert": "likert",
}

_BOUND_KINDS = ("input", "select", "likert")


def validate_form_config(doc: dict) -> list[str]:
    """Validate a committed form config. Dispatches on the config shape."""
    form_body = doc.get("anvilor_form")
    if not isinstance(form_body, dict):
        return ["top-level 'anvilor_form' object is required"]
    errors: list[str] = []
    if not form_body.get("title"):
        errors.append("anvilor_form.title is required")
    display = form_body.get("display_config") or {}
    if isinstance(display.get("rui_config"), dict):
        return errors + _validate_v1(display["rui_config"])
    if isinstance(display.get("rui_generation"), dict):
        return errors + _validate_v0(display["rui_generation"])
    return errors + [
        "display_config needs either rui_config (v1) or rui_generation (v0)"
    ]


def _validate_v1(rui: dict) -> list[str]:
    errors: list[str] = []
    if rui.get("rui_version") != "v1":
        errors.append("rui_config.rui_version must be 'v1'")
    model = rui.get("model") or {}
    properties = model.get("properties") or {}
    for required_key in model.get("required", []):
        if required_key not in properties:
            errors.append(f"model.required lists unknown property '{required_key}'")
    form = rui.get("form")
    if not isinstance(form, dict):
        return errors + ["rui_config.form is required"]

    seen_fields: dict[str, str] = {}

    def walk(node: dict, where: str) -> None:
        control = node.get("control")
        kind = _V1_KINDS.get(control)
        if kind is None:
            errors.append(f"{where}: unknown control '{control}'")
            return
        field = node.get("field")
        if kind in _BOUND_KINDS and not field:
            errors.append(f"{where}: control '{control}' requires a 'field'")
        if field:
            if field in seen_fields:
                errors.append(
                    f"{where}: field '{field}' already bound at {seen_fields[field]}"
                )
            seen_fields[field] = where
            if field.lstrip("/") not in properties:
                errors.append(f"{where}: field '{field}' not in model properties")
        if kind == "select":
            _check_select_options(node, control, where, errors)
        if kind == "likert" and not (node.get("rows") and node.get("scale")):
            errors.append(f"{where}: likert requires 'rows' and 'scale'")
        if control == "raw_content" and not node.get("content"):
            errors.append(f"{where}: raw_content requires 'content'")
        for i, child in enumerate(node.get("items") or []):
            walk(child, f"{where}.items[{i}]")
        for i, tab in enumerate(node.get("tabs") or []):
            if tab.get("form"):
                walk(tab["form"], f"{where}.tabs[{i}].form")

    walk(form, "form")
    if not any(f.lstrip("/") in properties for f in seen_fields):
        errors.append("the form has no input controls bound to model properties")
    return errors


def _validate_v0(rui_generation: dict) -> list[str]:
    errors: list[str] = []
    if rui_generation.get("generator_kind") != "raw":
        errors.append("rui_generation.generator_kind must be 'raw'")
    root = (rui_generation.get("raw_generator_data") or {}).get("root_control")
    if not isinstance(root, dict):
        return errors + ["rui_generation.raw_generator_data.root_control is required"]

    seen_fields: dict[str, str] = {}
    bound_count = 0

    # v0 nests child controls under several keys; flexbox/layout items wrap the
    # real def under a "control" object, so normalize before inspecting.
    child_keys = ("items", "body_controls", "post_submit", "post_close", "pre_open")

    def walk(node: dict, where: str) -> None:
        nonlocal bound_count
        inner = node.get("control")
        definition = inner if isinstance(inner, dict) else node
        control = definition.get("control")
        kind = _V0_KINDS.get(control)
        if kind is None:
            errors.append(f"{where}: unknown control '{control}'")
            return
        field = definition.get("field")
        if kind in _BOUND_KINDS and control != "standard_address" and not field:
            errors.append(f"{where}: control '{control}' requires a 'field'")
        if field:
            bound_count += 1
            if field in seen_fields:
                errors.append(
                    f"{where}: field '{field}' already bound at {seen_fields[field]}"
                )
            seen_fields[field] = where
        if kind == "select":
            _check_select_options(definition, control, where, errors)
        if kind == "likert" and not (definition.get("rows") and definition.get("scale")):
            errors.append(f"{where}: likert requires 'rows' and 'scale'")
        if control == "raw_content" and not definition.get("content"):
            errors.append(f"{where}: raw_content requires 'content'")
        for key in child_keys:
            value = definition.get(key)
            children = value if isinstance(value, list) else [value] if value else []
            for i, child in enumerate(children):
                if isinstance(child, dict):
                    walk(child, f"{where}.{key}[{i}]")

    walk(root, "root_control")
    if bound_count == 0:
        errors.append("the form has no input controls bound to fields")
    return errors


def _check_select_options(node: dict, control: str, where: str, errors: list) -> None:
    options = node.get("select_options") or []
    if not options:
        errors.append(f"{where}: control '{control}' requires select_options")
    values = [o.get("value") for o in options]
    if len(values) != len(set(map(str, values))):
        errors.append(f"{where}: select_options values must be unique")


# --- commands ----------------------------------------------------------------


def cmd_list(_args) -> int:
    registry = load_registry()
    for slug in form_slugs():
        entry = registry.get(slug)
        status = entry["url"] if entry else "(not published)"
        print(f"{slug}  {status}")
    return 0


def cmd_validate(args) -> int:
    errors = validate_form_config(load_form_config(args.slug))
    for error in errors:
        print(f"error: {error}")
    if not errors:
        print(f"{args.slug}: OK")
    return 1 if errors else 0


def cmd_publish(args) -> int:
    config = load_form_config(args.slug)
    errors = validate_form_config(config)
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    headers = _auth_headers()
    registry_entry = load_registry().get(args.slug)
    if registry_entry:
        oid = registry_entry["form_oid"]
        update_form(headers, oid, config)
        print(f"Updated form {oid}")
    else:
        oid = create_form(headers, config)
        record_form_oid(args.slug, oid)
        print(f"Created form {oid} — recorded in forms/registry.json; commit it")
    publish_form(headers, oid, notes=args.notes)
    print(f"Published: {FORMS_URL}/{oid}")
    return 0


def cmd_url(args) -> int:
    url = live_url(args.slug)
    if not url:
        raise SystemExit(
            f"{args.slug} has no recorded form_oid — "
            f"run `uv run python -m jcvb.forms publish {args.slug}` first"
        )
    print(url)
    return 0


def cmd_responses(args) -> int:
    entry = load_registry().get(args.slug)
    if not entry:
        raise SystemExit(f"{args.slug} is not published yet")
    docs = fetch_responses(_auth_headers(), entry["form_oid"])
    data = [
        (doc.get("response") or {}).get("response_data") or {} for doc in docs
    ]
    print(json.dumps(data if args.data_only else docs, indent=2, default=str))
    print(f"# {len(docs)} responses", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="jcvb.forms", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="list form configs and their live URLs")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("validate", help="validate a form config locally")
    p.add_argument("slug")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("publish", help="create/update + publish a form live")
    p.add_argument("slug")
    p.add_argument("--notes", default="published via jcvb.forms CLI")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("url", help="print a published form's live URL")
    p.add_argument("slug")
    p.set_defaults(func=cmd_url)

    p = sub.add_parser("responses", help="dump submitted responses as JSON")
    p.add_argument("slug")
    p.add_argument("--data-only", action="store_true")
    p.set_defaults(func=cmd_responses)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
