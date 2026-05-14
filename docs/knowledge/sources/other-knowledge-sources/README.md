# Other Knowledge Sources Archive

Archived on: 2026-03-31

Filename normalization completed on: 2026-05-14

This folder is a local mixed-source archive of PS4 PKG/PFS references. It combines raw snapshots, derived indexes, and extracted link inventories so the original sources can be rechecked without having to rediscover them.

## How To Use This Folder

- Start with `source-manifest.md` for source provenance, export dates, and re-export targets.
- Use `shadpkg-howworks-raw.md` for the deepest PKG and PFS decryption walkthrough in this folder.
- Use `psdevwiki-pfs-index.md` for a compact PFS format summary derived from the archived wiki page.
- Use the HTML snapshots when page context, revision identity, or embedded references matter.

## Provenance Table

| Local file | Role | Upstream source | Upstream publication or revision | Archived on | Re-export from |
| --- | --- | --- | --- | --- | --- |
| `psdevwiki-pkg-files.html` | Full HTML snapshot of the PSDevWiki PKG files page | [psdevwiki.com/ps4/PKG_files](https://www.psdevwiki.com/ps4/PKG_files) | Permanent revision `oldid=296676` | 2026-03-31 | `https://www.psdevwiki.com/ps4/PKG_files` |
| `psdevwiki-pfs.html` | Full HTML snapshot of the PSDevWiki PFS page | [psdevwiki.com/ps4/PFS](https://www.psdevwiki.com/ps4/PFS) | Permanent revision `oldid=296886` | 2026-03-31 | `https://www.psdevwiki.com/ps4/PFS` |
| `psdevwiki-pfs-index.md` | Human-curated PFS implementation summary derived from the HTML snapshot | Derived from `psdevwiki-pfs.html` | Captures revision `oldid=296886` | 2026-03-31 | Rebuild from `psdevwiki-pfs.html` or re-export the wiki page |
| `psdevwiki-pfs-links.txt` | Extracted readable link inventory from the PFS page | Derived from `psdevwiki-pfs.html` | Captures links present in revision `oldid=296886` | 2026-03-31 | Rebuild from `psdevwiki-pfs.html` |
| `psdevwiki-pfs-hrefs.txt` | Extracted raw href inventory from the PFS page | Derived from `psdevwiki-pfs.html` | Captures hrefs present in revision `oldid=296886` | 2026-03-31 | Rebuild from `psdevwiki-pfs.html` |
| `shadpkg-howworks-github-blob.html` | GitHub-rendered HTML view of the ShadPKG HOWWORKS document | [github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md](https://github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md) | Same article as the raw markdown, dated 2025-05-23 | 2026-03-31 | `https://github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md` |
| `shadpkg-howworks-raw.md` | Raw markdown export of the ShadPKG HOWWORKS document | [raw.githubusercontent.com/seregonwar/ShadPKG/main/docs/HOWWORKS.md](https://raw.githubusercontent.com/seregonwar/ShadPKG/main/docs/HOWWORKS.md) | Document dated 2025-05-23 by SeregonWar | 2026-03-31 | `https://raw.githubusercontent.com/seregonwar/ShadPKG/main/docs/HOWWORKS.md` |
| `wololo-ps4-fpkg-writeup-by-flatz.html` | HTML snapshot of the Wololo article hosting Flatz's FPKG writeup | [wololo.net/ps4-fpkg-writeup-by-flatz](https://wololo.net/ps4-fpkg-writeup-by-flatz/) | Published 2023-10-03, modified 2023-10-05 | 2026-03-31 | `https://wololo.net/ps4-fpkg-writeup-by-flatz/` |

## File Notes

### PSDevWiki PFS Set

- `psdevwiki-pfs.html` is the source-of-truth snapshot for the PFS page.
- `psdevwiki-pfs-index.md` distills the PFS page into implementation-focused notes on headers, inodes, dirents, root discovery, flat path table behavior, and encryption context.
- `psdevwiki-pfs-links.txt` and `psdevwiki-pfs-hrefs.txt` preserve outbound links and raw hrefs from the same revision for later audit.

### PSDevWiki PKG Set

- `psdevwiki-pkg-files.html` is a full snapshot of the PKG files page and is useful as a format overview and tool catalog.

### ShadPKG Set

- `shadpkg-howworks-raw.md` is the highest-value technical artifact in this folder for implementation work. It covers PKG headers, key derivation, AES-CBC, HMAC-SHA256, AES-XTS, PFSC, and file extraction flow.
- `shadpkg-howworks-github-blob.html` is the same document rendered through GitHub's web UI. Keep it when GitHub page context is useful; otherwise prefer the raw markdown.

### Wololo / Flatz Set

- `wololo-ps4-fpkg-writeup-by-flatz.html` is a preserved article snapshot that republishes a Flatz fake PKG writeup. It is most useful for historical context, exploit framing, and FPKG-specific notes rather than primary format specification.

## Duplication And Trust Notes

- The two ShadPKG files are format variants of the same upstream document.
- The three `psdevwiki-pfs-*` helper files are derivatives of `psdevwiki-pfs.html`, not independent sources.
- PSDevWiki pages are reverse-engineering references and should be treated as strong but not final authority.
- The ShadPKG markdown is the most complete cryptographic walkthrough in this archive, but it still reflects the author's analysis and implementation assumptions.

## Related Durable Docs

- Provenance manifest: `source-manifest.md`
- Repository-level summary: `../other-knowledge-sources.md`

Use the manifest when you want to refresh or re-export any of the archived sources.
