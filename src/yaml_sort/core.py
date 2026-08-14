"""
yaml_sort — deterministic YAML key ordering.

Reads a YAML document, parses it into a block-structure tree (mappings and
sequences), sorts sibling mapping keys alphabetically bottom-up, and re-emits.
In the default ``list_indent=None`` ("keep") mode every byte is preserved
exactly. Passing ``list_indent=N`` re-indents sequence items so they sit N
spaces to the right of their parent mapping key (0 = aligned, 2 = indented).

The parser understands lists, folded plain scalars, quoted scalars, and
comments/gaps, and preserves them verbatim. It is deliberately *not* a
`yaml.load`/`yaml.dump` round-trip, because that would rewrite the whole file
(re-quoting, re-indenting, dropping comments) and destroy the diff-cleanliness
the tool exists to provide.

Notable behaviour:

* Mapping keys are sorted alphabetically, bottom-up, including inside list
  items and nested maps.
* List items are *ordered* — a sequence's order is meaningful and is never
  changed.
* For a list item that opens a mapping (e.g. ``- api_key: none`` followed by
  ``base_url:``…), the "anchor" key fused to the ``- `` is sorted along with
  its siblings, and the ``- `` re-fuses to whichever key sorts first, keeping
  every list entry fully alphabetical.
"""

from __future__ import annotations

import re


# ── line helpers ─────────────────────────────────────────────────────────────

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_gap(line: str) -> bool:
    """Blank, comment, document marker, or directive line."""
    s = line.strip()
    if not s:
        return True
    if s.startswith("#"):
        return True
    if s in ("---", "..."):
        return True
    if s.startswith("%"):
        return True
    return False


_KEY_RE = re.compile(r"^(?:['\"]([^'\"]+)['\"]|([^#:\s][^:]*?))\s*:")


def _is_key_line(line: str) -> bool:
    """True if *line* is a mapping key line (not a list item, comment, etc.)."""
    stripped = line.lstrip()
    if not stripped or stripped.startswith("- "):
        return False
    return bool(_KEY_RE.match(stripped))


def _extract_key(line: str) -> str:
    stripped = line.lstrip()
    m = _KEY_RE.match(stripped)
    return (m.group(1) or m.group(2)) if m else stripped.rstrip(":\n")


def _strip_indent(line: str) -> str:
    """Return the line with its leading whitespace removed (keeps the rest)."""
    return line.lstrip(" ")


# ── tree model ───────────────────────────────────────────────────────────────

class Container:
    """A mapping ('map') or sequence ('seq') made of ordered blocks.

    A mapping that represents a list item (a ``- key:`` line fused to the
    ``- `` dash) has ``dash_first=True``: its first key is emitted with a
    ``- `` prefix at ``seq_indent``, and the remaining keys at its own indent.
    """

    def __init__(self, kind: str, indent: int):
        self.kind = kind              # 'map' | 'seq'
        self.indent = indent          # indent of this container's header lines
        self.dash_first = False       # map whose first key carries the `- `
        self.seq_indent = 0           # indent of the dash when dash_first
        self.blocks: list = []        # KeyBlock | ItemBlock | Container | Gap

    def sort(self) -> None:
        """Sort mapping keys alphabetically, bottom-up. Sequences are ordered."""
        for b in self.blocks:
            if isinstance(b, Container):
                b.sort()
            elif isinstance(b, (KeyBlock, ItemBlock)) and isinstance(b.value, Container):
                b.value.sort()
        if self.kind == "map":
            self._sort_map_keys()

    def _sort_map_keys(self) -> None:
        """Rebuild a mapping with keys alphabetised, keeping each gap with the
        key it followed in the original text (trailing-gap semantics)."""
        leading_gap: list[str] = []
        pairs: list[tuple[KeyBlock, list[str]]] = []   # (key, trailing_gap)
        cur: tuple[KeyBlock, list[str]] | None = None
        for b in self.blocks:
            if isinstance(b, Gap):
                if cur is None:
                    leading_gap.extend(b.lines)
                else:
                    cur[1].extend(b.lines)
            else:
                cur = (b, [])
                pairs.append(cur)
        pairs.sort(key=lambda p: p[0].name)
        new_blocks: list = []
        if leading_gap:
            new_blocks.append(Gap(leading_gap))
        for kb, trailing in pairs:
            new_blocks.append(kb)
            if trailing:
                new_blocks.append(Gap(trailing))
        self.blocks = new_blocks


class Gap:
    """A run of blank/comment/directive lines kept verbatim."""

    def __init__(self, lines: list[str]):
        self.lines = lines


class KeyBlock:
    def __init__(self, name: str, header: str, cont: list[str] | None = None):
        self.name = name
        self.header = header          # header line text minus leading indent
        self.cont = cont or []        # folded plain-scalar continuation lines
        self.value = None             # Container | None
        self.dash_anchor = False      # True if emitted with a `- ` prefix
        self.anchor_indent = 0        # indent of the enclosing seq when anchor


class ItemBlock:
    def __init__(self, header: str, cont: list[str] | None = None):
        self.header = header          # header line text minus leading indent
        self.cont = cont or []        # folded plain-scalar continuation lines
        self.value = None             # Container | None


# ── parser ───────────────────────────────────────────────────────────────────

def _inline_value(line: str) -> bool:
    """True if *line* has an inline scalar value after its key/`-` prefix.

    e.g. `catgirl: You are...` → True; `models:` → False.
    """
    h = line.lstrip()
    if h.startswith("- "):
        h = h[2:].lstrip()
    m = _KEY_RE.match(h)
    if not m or m.end() >= len(h):
        return False
    rest = h[m.end():].lstrip()
    return bool(rest) and not rest.startswith("#")


def _value_quoted(line: str) -> bool:
    """True if the inline value of *line* is single- or double-quoted.

    Quoted scalars may wrap onto deeper lines containing colons, so their
    continuations must be consumed verbatim.
    """
    h = line.lstrip()
    if h.startswith("- "):
        h = h[2:].lstrip()
    m = _KEY_RE.match(h)
    if not m or m.end() >= len(h):
        return False
    rest = h[m.end():].lstrip()
    return rest[:1] in ("'", '"')


def _split_item_header(header: str):
    """For a `- ...` item header, return (name, has_inline) if it opens a map.

    `- api_key: none` → ('api_key', True); `- value` (no colon) → None.
    """
    h = header[2:].lstrip()
    m = _KEY_RE.match(h)
    if not m:
        return None
    name = m.group(1) or m.group(2)
    return name, _inline_value("- " + h)


def _gather_cont(lines, idx: int, indent: int, quoted: bool = False):
    """Collect folded plain-scalar continuation lines deeper than *indent*.

    Returns (cont_lines, next_idx). Stops at a gap, a line at/below *indent*,
    or (for plain scalars) a key/item line. For *quoted* scalars, every deeper
    line is consumed verbatim regardless of colons.
    """
    cont: list[str] = []
    i = idx
    while i < len(lines):
        line = lines[i]
        if _is_gap(line) or _indent(line) <= indent:
            break
        if not quoted:
            s = line.lstrip()
            if _is_key_line(line) or s.startswith("- "):
                break
        cont.append(line[indent:])
        i += 1
    return cont, i


def parse_block(lines, idx: int, indent: int, kind: str):
    """Parse a single mapping key or sequence item at *indent*.

    Returns (KeyBlock|ItemBlock|Container, next_idx).
    """
    raw = lines[idx]
    i = idx + 1
    header = _strip_indent(raw)

    if kind == "map":
        name = _extract_key(raw)
        has_inline = _inline_value(raw)
        quoted = _value_quoted(raw)
        item_key = None
    else:
        item_key = _split_item_header(header)
        name = item_key[0] if item_key else None
        has_inline = item_key[1] if item_key else False
        quoted = _value_quoted(raw)

    cont: list[str] = []
    value = None
    anchor_block = None
    dash_map = None

    j = i
    while j < len(lines) and _is_gap(lines[j]):
        j += 1

    if j < len(lines):
        nind = _indent(lines[j])
        s = lines[j].lstrip()
        next_is_block = nind > indent and (_is_key_line(lines[j]) or s.startswith("- "))

        if kind == "seq" and item_key is not None and next_is_block and not quoted:
            # A list item that opens a mapping.
            ckind = "seq" if s.startswith("- ") else "map"
            if ckind == "map":
                cmap, i = parse_container(lines, i, nind, "map")
                if has_inline:
                    # `- api_key: none` then `base_url:…`: the anchor key is a
                    # sibling of the deeper keys. Represent as one dash_first
                    # map so the anchor participates in sorting.
                    anchor = KeyBlock(item_key[0], header[2:].lstrip())
                    cmap.blocks.insert(0, anchor)
                    cmap.dash_first = True
                    cmap.seq_indent = indent
                    dash_map = cmap
                else:
                    # `- api_key:` (empty value) then deeper keys: the deeper
                    # map is the anchor's value; the anchor stays pinned.
                    anchor = KeyBlock(item_key[0], header[2:].lstrip())
                    anchor.dash_anchor = True
                    anchor.anchor_indent = indent
                    anchor.value = cmap
                    anchor_block = anchor
            else:
                value, i = parse_container(lines, i, nind, ckind)
        elif next_is_block and not has_inline:
            # Child container for a key with no inline value (e.g. `models:`
            # followed by an indented/aligned sequence, or a nested map).
            ckind = "seq" if s.startswith("- ") else "map"
            value, i = parse_container(lines, i, nind, ckind)
        elif nind > indent:
            # Deeper plain text → folded scalar continuation.
            cont, i = _gather_cont(lines, i, indent, quoted=quoted)
        elif (nind == indent and kind == "map"
              and s.startswith("- ") and not has_inline):
            # Aligned sequence value (items at the same indent as the key).
            value, i = parse_container(lines, i, indent, "seq")

    if dash_map is not None:
        return dash_map, i
    if anchor_block is not None:
        return anchor_block, i
    blk = KeyBlock(name, header, cont) if kind == "map" else ItemBlock(header, cont)
    blk.value = value
    return blk, i


def parse_container(lines, idx: int, indent: int, kind: str):
    """Parse a container whose header lines are at *indent*.

    Returns (Container, next_idx). Stops when a line drops below *indent* or a
    line at *indent* is the wrong type for this container.
    """
    cont = Container(kind, indent)
    i = idx
    pending_gap: list[str] = []

    while i < len(lines):
        line = lines[i]
        ind = _indent(line)

        if _is_gap(line):
            pending_gap.append(line)
            i += 1
            continue

        if ind < indent:
            break

        if ind == indent:
            if kind == "map" and _is_key_line(line):
                block_lines = pending_gap
                pending_gap = []
                if block_lines:
                    cont.blocks.append(Gap(block_lines))
                blk, i = parse_block(lines, i, indent, "map")
                cont.blocks.append(blk)
            elif kind == "seq" and line.lstrip().startswith("- "):
                block_lines = pending_gap
                pending_gap = []
                if block_lines:
                    cont.blocks.append(Gap(block_lines))
                blk, i = parse_block(lines, i, indent, "seq")
                cont.blocks.append(blk)
            else:
                # Wrong type at this indent → container ends here.
                break
        else:  # ind > indent
            # Continuation not attached to a block; stop to be safe.
            break

    if pending_gap:
        cont.blocks.append(Gap(pending_gap))
    return cont, i


def parse_document(text: str):
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines) and _is_gap(lines[i]):
        i += 1
    if i >= len(lines):
        # Comment-only / blank document: preserve the gaps verbatim.
        root = Container("map", 0)
        if lines:
            root.blocks.append(Gap(lines))
        return root, lines
    s = lines[i].strip()
    kind = "seq" if s.startswith("- ") else "map"
    indent = _indent(lines[i])
    root, _ = parse_container(lines, i, indent, kind)
    # Attach any leading gaps to the root.
    if i > 0:
        root.blocks.insert(0, Gap(lines[:i]))
    return root, lines


# ── emitter ──────────────────────────────────────────────────────────────────

def _emit_keep(node: Container, out: list[str]) -> None:
    first = True
    for b in node.blocks:
        if isinstance(b, Gap):
            out.extend(b.lines)
            continue
        if isinstance(b, Container):
            _emit_keep(b, out)
            continue
        if node.dash_first and first:
            out.append(" " * node.seq_indent + "- " + b.header)
            for c in b.cont:
                out.append(" " * node.seq_indent + c)
        elif isinstance(b, KeyBlock) and b.dash_anchor:
            out.append(" " * b.anchor_indent + "- " + b.header)
            for c in b.cont:
                out.append(" " * b.anchor_indent + c)
        else:
            out.append(" " * node.indent + b.header)
            for c in b.cont:
                out.append(" " * node.indent + c)
        first = False
        if isinstance(b.value, Container):
            _emit_keep(b.value, out)


def _emit_reindent(node: Container, indent: int, list_indent: int, out: list[str]) -> None:
    """Re-indent sequences to *list_indent* spaces under their parent key.

    Mapping nesting always steps by 2; a sequence's items are placed at the
    parent line's indent plus *list_indent* (0 → aligned, 2 → indented).
    """
    first = True
    for b in node.blocks:
        if isinstance(b, Gap):
            out.extend(b.lines)
            continue
        if isinstance(b, Container):
            # A dash_first list-item map nested in a sequence: its dash sits at
            # the seq's target indent.
            _emit_reindent(b, indent, list_indent, out)
            continue
        if node.dash_first and first:
            key_indent = indent
            prefix = "- "
        elif isinstance(b, KeyBlock) and b.dash_anchor:
            key_indent = indent
            prefix = "- "
        else:
            key_indent = indent + (2 if node.dash_first else 0)
            prefix = ""
        out.append(" " * key_indent + prefix + b.header)
        for c in b.cont:
            out.append(" " * key_indent + c)
        first = False
        if isinstance(b.value, Container):
            child = key_indent + (2 if b.value.kind == "map" else list_indent)
            _emit_reindent(b.value, child, list_indent, out)


def sort_text(text: str, list_indent=None) -> str:
    root, _ = parse_document(text)
    root.sort()
    out: list[str] = []
    if list_indent is None:                    # keep (byte-exact)
        _emit_keep(root, out)
    else:
        _emit_reindent(root, root.indent, list_indent, out)
    return "".join(out)
