# Knowledge base overview

This section collects the source-backed reference material used to understand PFS, PKG, and the surrounding tooling.

## Source map

| Source | Focus | Reuse mode |
| --- | --- | --- |
| `related-projects/liborbispkg.md` | LibOrbisPkg architecture, PFS pipeline, structures | Symlinked into the docs tree |
| `related-projects/pkgtool.md` | PKG container behavior and implementation notes | Symlinked into the docs tree |
| `related-projects/shadowmountplus.md` | PS5 mount flow and filesystem workflow | Symlinked into the docs tree |
| `related-projects/other-knowledge-sources.md` | Provenance and archive index | Symlinked into the docs tree |

## How this section is maintained

Run the sync script before building the site so MkDocs can read the canonical markdown from the source tree.

```bash
python scripts/sync_docs_sources.py
```

## Reading order

1. Start with the direct source pages under [PFS and PKG Sources](../knowledge/sources/liborbispkg.md).
2. Use the source index for provenance and the archived references.
3. Return to the command docs when you want to connect the research back to mkpfs itself.
