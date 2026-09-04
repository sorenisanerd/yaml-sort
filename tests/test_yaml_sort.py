"""Unit tests for yaml-sort's core sorting/emission behaviour.

Each case is a pair of fixture files under ``tests/fixtures/``:

    <case>.in.yaml       input document
    <case>.out.yaml      expected output  (REQUIRED for every case, even when
                                           it equals the input)

``.out.yaml`` is mandatory so there is no ambiguity about what a case asserts.
``test_fixture_pairing`` enforces that every ``.in.yaml`` has a matching
``.out.yaml`` (and vice versa), and that every case in the tables below has
both files.

The ``list_indent`` column is the value to pass to
:func:`~yaml_sort.sort_text` (None means leave it default).

Reading from files (rather than inline strings) keeps expected output readable
with no escaping.
"""

import pytest

from yaml_sort import sort_text

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def _read(name, suffix):
    return (FIXTURES / f"{name}.{suffix}").read_text()


def _call(name, list_indent, **kw):
    kwargs = {"list_indent": list_indent} if list_indent is not None else {}
    kwargs.update(kw)
    return sort_text(_read(name, "in.yaml"), **kwargs)


# ── all cases: (name, list_indent) ───────────────────────────────────────────
CASES = [
    # basic key sorting
    ("sort_top_level_keys", None),
    ("already_sorted", None),
    ("stability", None),
    ("nested_map_sort", None),
    ("deep_nested_sort", None),
    # sequence handling (order preserved)
    ("list_order_preserved", None),
    ("list_of_scalars", None),
    ("nested_list_preserved", None),
    ("aligned_list_under_key", None),
    # anchor behaviour
    ("anchor_sorts", None),
    ("anchor_already_first", None),
    ("anchor_no_inline_value", None),
    ("keys_inside_list_items", None),
    # comments and gaps
    ("comments_preserved", None),
    ("blank_lines", None),
    ("comment_in_list_item", None),
    ("inline_comment", None),
    # trailing footer comments
    ("trailing_comment_stays_bottom", None),
    ("trailing_comment_nested", None),
    ("trailing_comment_after_nested", None),
    # scalars and quoting
    ("folded_plain_scalar", None),
    ("quoted_scalar_with_colon", None),
    ("quoted_empty_scalar", None),
    ("comment_only", None),
    ("trailing_newline", None),
    ("unicode", None),
    ("quoted_keys", None),
    ("empty_map_value", None),
    ("flow_style", None),
    # list-indent modes
    ("list_indent_zero", 0),
    ("list_indent_two", 2),
    ("list_indent_nested", 2),
    ("list_indent_valid", 2),
]


@pytest.mark.parametrize("name,list_indent", CASES)
def test_case(name, list_indent):
    expected = _read(name, "out.yaml")
    assert _call(name, list_indent) == expected


@pytest.mark.parametrize("name,list_indent", CASES)
def test_case_is_idempotent(name, list_indent):
    # Sorting the already-sorted output must be a fixed point.
    once = _call(name, list_indent)
    kwargs = {"list_indent": list_indent} if list_indent is not None else {}
    assert sort_text(once, **kwargs) == once


# ── fixture integrity ─────────────────────────────────────────────────────────

def test_fixture_pairing():
    """Every .in.yaml has a matching .out.yaml and vice versa."""
    ins = sorted(FIXTURES.glob("*.in.yaml"))
    outs = sorted(FIXTURES.glob("*.out.yaml"))
    in_names = {p.name[: -len(".in.yaml")] for p in ins}
    out_names = {p.name[: -len(".out.yaml")] for p in outs}
    assert in_names == out_names, (
        f"mismatched fixtures: only-in={in_names - out_names or None}, "
        f"only-out={out_names - in_names or None}"
    )


def test_every_case_has_fixtures():
    """Every case in CASES has both files present."""
    for name, _ in CASES:
        assert (FIXTURES / f"{name}.in.yaml").is_file(), f"missing {name}.in.yaml"
        assert (FIXTURES / f"{name}.out.yaml").is_file(), f"missing {name}.out.yaml"


def test_no_orphan_fixtures():
    """Every fixture pair is referenced by CASES."""
    paired = {p.name[: -len(".in.yaml")] for p in FIXTURES.glob("*.in.yaml")}
    referenced = {name for name, _ in CASES}
    assert paired == referenced, (
        f"unreferenced fixtures: {paired - referenced or None}, "
        f"referenced-but-missing: {referenced - paired or None}"
    )


# ── properties / standalone ──────────────────────────────────────────────────

def test_empty_document():
    assert sort_text("") == ""


def test_list_indent_reindented_output_is_valid_yaml():
    yaml = pytest.importorskip("yaml")
    src = _read("list_indent_valid", "in.yaml")
    a = yaml.safe_load(src)
    b = yaml.safe_load(sort_text(src, list_indent=2))
    assert a == b
