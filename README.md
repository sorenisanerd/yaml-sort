# yaml-sort

Deterministic YAML key ordering. Sorts mapping keys alphabetically (bottom-up)
while preserving comments and byte-for-byte formatting, so running it produces
no diff when a file is already sorted.

Designed to keep `chezmoi`-managed config diffs clean.

## Why not just `yaml.load` → sort → `yaml.dump`?

A library round-trip rewrites the whole file: it drops comments, re-quotes
strings, re-indents everything, and normalizes flow/block style. That adds
diff noise on every run. `yaml-sort` instead parses the *block structure* and
re-emits it verbatim, moving only what it needs to (mapping keys).

## Features

- Sorts mapping keys alphabetically, bottom-up — including inside list items
  and nested maps.
- Never reorders list items (sequence order is meaningful).
- For a list item that opens a map (`- api_key: none` then `base_url:`…), the
  anchor key fused to the `- ` is sorted with its siblings and the `- `
  re-fuses to whichever key sorts first, keeping every list entry fully
  alphabetical.
- `--list-indent keep` (default): preserve existing indentation byte-for-byte.
- `--list-indent N`: re-indent sequence items N spaces right of their parent key
  (0 = aligned, 2 = conventional indented style).
- `--check`, `--diff`, `--stdin` modes.

## Install

```sh
pip install yaml-sort        # from PyPI (once published)
# or, from a checkout:
pip install -e .
```

## Usage

```
yaml-sort <file>                  Sort file in-place
yaml-sort <file> --check          Exit 0 if sorted, 1 if not
yaml-sort <file> --diff           Show what would change
yaml-sort <file> --list-indent 2  Also re-indent lists 2 spaces under their key
yaml-sort --stdin                 Read stdin, write sorted to stdout
```

## Library use

```python
from yaml_sort import sort_text

sorted_yaml = sort_text(raw_text)            # byte-preserving
sorted_yaml = sort_text(raw_text, 2)         # re-indent lists to 2 spaces
```

## Development

```sh
pip install -e .[dev]
pytest
```
