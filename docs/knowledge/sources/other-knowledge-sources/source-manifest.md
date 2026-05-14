# Other Knowledge Sources Manifest

Archive date: 2026-03-31

Filename normalization date: 2026-05-14

This manifest exists to make re-export straightforward. It separates original source identity from derived local artifacts.

| Local file | Kind | Source domain | Upstream URL | Upstream publication or revision | Archived on | Relationship |
| --- | --- | --- | --- | --- | --- | --- |
| `psdevwiki-pkg-files.html` | HTML snapshot | `psdevwiki.com` | [psdevwiki.com/ps4/PKG_files](https://www.psdevwiki.com/ps4/PKG_files) | Permanent revision `oldid=296676` | 2026-03-31 | Primary source |
| `psdevwiki-pfs.html` | HTML snapshot | `psdevwiki.com` | [psdevwiki.com/ps4/PFS](https://www.psdevwiki.com/ps4/PFS) | Permanent revision `oldid=296886` | 2026-03-31 | Primary source |
| `psdevwiki-pfs-index.md` | Derived markdown index | local derivative | Rebuild from `psdevwiki-pfs.html` | Mirrors revision `oldid=296886` | 2026-03-31 | Derived from `psdevwiki-pfs.html` |
| `psdevwiki-pfs-links.txt` | Derived link inventory | local derivative | Rebuild from `psdevwiki-pfs.html` | Mirrors revision `oldid=296886` | 2026-03-31 | Derived from `psdevwiki-pfs.html` |
| `psdevwiki-pfs-hrefs.txt` | Derived href inventory | local derivative | Rebuild from `psdevwiki-pfs.html` | Mirrors revision `oldid=296886` | 2026-03-31 | Derived from `psdevwiki-pfs.html` |
| `shadpkg-howworks-github-blob.html` | HTML snapshot | `github.com` | [github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md](https://github.com/seregonwar/ShadPKG/blob/main/docs/HOWWORKS.md) | Same document as raw markdown, dated 2025-05-23 | 2026-03-31 | Alternate rendering of the raw markdown |
| `shadpkg-howworks-raw.md` | Raw markdown | `raw.githubusercontent.com` | [raw.githubusercontent.com/seregonwar/ShadPKG/main/docs/HOWWORKS.md](https://raw.githubusercontent.com/seregonwar/ShadPKG/main/docs/HOWWORKS.md) | Document dated 2025-05-23 by SeregonWar | 2026-03-31 | Primary source |
| `wololo-ps4-fpkg-writeup-by-flatz.html` | HTML snapshot | `wololo.net` | [wololo.net/ps4-fpkg-writeup-by-flatz](https://wololo.net/ps4-fpkg-writeup-by-flatz/) | Published 2023-10-03, modified 2023-10-05 | 2026-03-31 | Primary source |

## Re-export Checklist

1. Re-fetch the upstream URL.
2. Preserve a permanent revision or publication date when the site exposes one.
3. Regenerate any derived markdown or link inventories from the refreshed primary file.
4. Update `README.md` and `../other-knowledge-sources.md` if the source content or provenance changed.
