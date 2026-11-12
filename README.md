# wp-media-doctor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/wp-media-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/wp-media-doctor/issues)

A zero-dependency Python CLI that audits a WordPress media
library CSV export for the problems that bloat a site and
hurt its search ranking and accessibility: images with
missing or weak alt text, oversized originals, duplicate
files by content hash, images nothing on the site links to,
and files in formats WordPress does not serve well.

Missing alt text is the most common WordPress accessibility
failure, and it is also an SEO failure: search engines read
alt text to understand an image. Oversized originals are
the most common cause of slow pages, because WordPress
serves the full-size file whenever a theme or block asks for
it. Duplicates pile up because the same image gets uploaded
again under a new name instead of being reused. Media
library plugins audit all of this inside the dashboard;
this tool is the offline audit of the exported list, so a
site owner can check a backup or a staging copy without
installing anything on the live site.

## Install

Requires Python 3.10 or newer. No dependencies beyond the
standard library.

```bash
pip install wp-media-doctor
```

Or run it straight from the source checkout:

```bash
python3 wp_media_doctor.py examples/media.csv --as-of 2026-11-12 --used-file examples/used.txt
```

## Input format

A CSV export with a header row, as produced by a media
library export plugin or assembled from the wp_posts table.
Columns used: `id`, `file`, `url`, `alt_text`, `width`,
`height`, `size_bytes`, `mime`, `hash`, and `uploaded`.
The aliases `filename`, `file_url`, `alt`, `size`, `mime_type`,
`md5`, and `upload_date` are accepted too. A UTF-8 BOM
header is handled. Dates are accepted as YYYY-MM-DD,
YYYY-MM-DD HH:MM:SS, ISO datetime, YYYY/MM/DD, or
DD/MM/YYYY.

```csv
id,file,url,alt_text,width,height,size_bytes,mime,hash,uploaded
1,hero.jpg,https://example.com/wp-content/uploads/2026/01/hero.jpg,Team photo at the office,2400,1600,850000,image/jpeg,aaa111,2026-01-10
2,banner.png,https://example.com/wp-content/uploads/2026/02/banner.png,,1920,600,1200000,image/png,bbb222,2026-02-01
3,IMG_4521.jpg,https://example.com/wp-content/uploads/2026/03/IMG_4521.jpg,IMG_4521.jpg,4000,3000,3500000,image/jpeg,ccc333,2026-03-05
```

The usage list for the unused-image check is a plain text
file, one image URL or file name per line, as found in site
content. Lines starting with `#` are comments. Matching
works on the full URL, the full file name, or the base name
of either, so a list of URLs matches a file column and a
list of file names matches a URL column.

```
# Image URLs and file names found in site content
https://example.com/wp-content/uploads/2026/01/hero.jpg
https://example.com/wp-content/uploads/2026/02/banner.png
logo.svg
```

## What it checks

Errors, the ones that are a live accessibility,
performance, or data problem:

* `missing-alt`: an image with no alt text at all. Screen
  readers and search engines cannot describe it.
* `oversized`: a file above `--max-size` (default 1,000,000
  bytes). Oversized originals are the most common cause of
  slow pages.
* `unsupported-format`: a format outside JPEG, PNG, WebP,
  GIF, AVIF, and SVG, for example TIFF, HEIC, or PDF. The
  file should be converted to JPEG, PNG, WebP, or AVIF.
* `duplicate-file`: a content hash that already appears in
  the export. The row is kept, because each duplicate is a
  separate attachment that can be deleted.
* `empty-file`: a file of 0 bytes, so it holds no image.
* `invalid-size`: a size that is not a number of bytes, or
  a negative size.
* `missing-size`: no file size recorded, so the file cannot
  be checked for bloat.
* `missing-file`: a row with no file name, so the media
  file cannot be identified.
* `missing-url`: a row with no URL, so the media file
  cannot be found on the site.
* `malformed-row`: a row with the wrong number of fields.
  The row is skipped and reported, never a crash.

Warnings, files worth following up:

* `weak-alt`: alt text that describes nothing about the
  image: the file name itself, a camera or screenshot file
  name pattern such as `IMG_4521` or `screenshot-2024-05-01`,
  a bare generic word such as `image`, `photo`, or `logo`
  (optionally numbered), or alt text shorter than 3
  characters.
* `long-alt`: alt text above `--max-alt` (default 125
  characters), the recommended maximum for screen readers.
* `large-dimensions`: a width above `--max-width` (default
  2560 px).
* `missing-dimensions`: no width or height recorded, so the
  image dimensions could not be checked.
* `invalid-dimensions`: a width or height that is not a
  number, or zero or negative.
* `duplicate-url`: a URL that already appears in the
  export. The row is kept.
* `unknown-format`: no mime type and no recognised file
  extension, so the format could not be checked.
* `unused-image`: an image in no `--used-file` entry, so
  nothing on the site links to it. Only checked when a
  usage list is supplied.
* `invalid-date`: an upload date that is not a recognised
  date.
* `future-date`: an upload date in the future.

Non-image files such as PDFs skip the alt text and
dimension checks, because those rules do not apply to
them; they are still flagged as unsupported formats.

## Usage

```bash
python3 wp_media_doctor.py examples/media.csv --as-of 2026-11-12 --used-file examples/used.txt
```

Captured output:

```
ERROR [oversized] banner.png: file is 1200000 bytes, above the maximum of 1000000 bytes
ERROR [missing-alt] banner.png: image has no alt text, so screen readers and search engines cannot describe it
ERROR [oversized] IMG_4521.jpg: file is 3500000 bytes, above the maximum of 1000000 bytes
WARNING [large-dimensions] IMG_4521.jpg: width 4000 px is above the maximum of 2560 px
WARNING [weak-alt] IMG_4521.jpg: alt text 'IMG_4521.jpg' describes nothing about the image
WARNING [unused-image] team-photo.jpg: image appears in no supplied usage list entry, so nothing on the site links to it
ERROR [unsupported-format] old-scan.tiff: format image/tiff is not a supported web image format, convert it to JPEG, PNG, WebP, or AVIF
ERROR [oversized] old-scan.tiff: file is 2200000 bytes, above the maximum of 1000000 bytes
WARNING [unused-image] old-scan.tiff: image appears in no supplied usage list entry, so nothing on the site links to it
ERROR [duplicate-file] product-a.jpg: content hash aaa111 matches another file in this export, so this is a duplicate upload
WARNING [weak-alt] product-b.jpg: alt text 'x' describes nothing about the image
WARNING [weak-alt] screenshot-2024-05-01.png: alt text 'screenshot-2024-05-01' describes nothing about the image
ERROR [unsupported-format] brochure.pdf: format application/pdf is not a supported web image format, convert it to JPEG, PNG, WebP, or AVIF
WARNING [unused-image] brochure.pdf: image appears in no supplied usage list entry, so nothing on the site links to it
ERROR [empty-file] empty.png: file is 0 bytes, so it holds no image
ERROR [invalid-size] badsize.jpg: size 'not-a-number' is not a number of bytes
ERROR [malformed-row] row 14: row has 3 fields but the header has 10, so the row was skipped
WARNING [future-date] future.jpg: upload date 2027-01-01 is in the future
WARNING [long-alt] longalt.jpg: alt text is 160 characters, above the recommended maximum of 125
WARNING [missing-dimensions] nodims.jpg: no width or height recorded, so the image dimensions could not be checked
WARNING [duplicate-url] hero-copy.jpg: URL https://example.com/wp-content/uploads/2026/01/hero.jpg already appears in this export

Per format:
application/pdf: 1 image, 150000 bytes
image/jpeg: 10 images, 7450000 bytes
image/png: 3 images, 1900000 bytes
image/svg+xml: 1 image, 45000 bytes
image/tiff: 1 image, 2200000 bytes

Images: 16, total size: 11745000 bytes, findings: 21, errors: 10, warnings: 11
```

The sample has 16 images after the malformed row is left
out, totalling 11,745,000 bytes. Three images are unused:
team-photo.jpg, old-scan.tiff, and brochure.pdf. The 4,000
px wide IMG_4521.jpg is both oversized at 3.5 MB and weak
on alt text, because its alt text is its own file name.
product-a.jpg is a byte-for-byte duplicate of hero.jpg
under a different name, caught by its content hash.

The reference date defaults to today. `--as-of` pins it, so
the future-date check above is reproducible; without it
the check moves as time passes.

Add `--deletable` to print, after the summary, the list of
files the audit considers safe to delete:

```bash
python3 wp_media_doctor.py examples/media.csv --as-of 2026-11-12 --used-file examples/used.txt --deletable
```

```
Images: 16, total size: 11745000 bytes, findings: 21, errors: 10, warnings: 11

Safe to delete (report only, nothing is deleted):
- old-scan.tiff: unused and oversized and unsupported format
- product-a.jpg: duplicate of an earlier upload of the same content hash
```

Nothing is deleted; the list is a report only, and each
line names the reason. A file is listed when it is a
duplicate beyond the first upload of its content hash, or
when it is an unused image that is also oversized or in an
unsupported format. An unused image that is otherwise clean,
such as team-photo.jpg above, is left off the list, because
an unused image may still be wanted. With `--json` the same
list appears as a `deletable` array of file and reason
objects.

Use it as a CI gate: `--check` exits 1 when any error is
found, and 0 otherwise. On the sample above it exits 1:

```bash
python3 wp_media_doctor.py examples/media.csv --as-of 2026-11-12 --used-file examples/used.txt --check
```

On `examples/clean.csv`, three clean images, it exits 0:

```
Per format:
image/jpeg: 2 images, 1750000 bytes
image/svg+xml: 1 image, 45000 bytes

Images: 3, total size: 1795000 bytes, findings: 0, errors: 0, warnings: 0
Note: no --used-file supplied, so unused-image checks were skipped.
All media clean.
```

With `--strict`, `--check` also fails on warnings.
`examples/warnings-only.csv` has three warnings, a generic
`photo` alt, a file with no dimensions, and a future upload
date, so it passes `--check` (exit 0) and fails
`--check --strict` (exit 1).

`--json` emits the summary, per-format table, and findings
as JSON:

```bash
python3 wp_media_doctor.py examples/media.csv --as-of 2026-11-12 --used-file examples/used.txt --json
```

Captured output (first findings and summary):

```json
[
  {
    "file": "banner.png",
    "rule": "oversized",
    "severity": "error",
    "message": "file is 1200000 bytes, above the maximum of 1000000 bytes"
  },
  {
    "file": "banner.png",
    "rule": "missing-alt",
    "severity": "error",
    "message": "image has no alt text, so screen readers and search engines cannot describe it"
  },
  {
    "file": "IMG_4521.jpg",
    "rule": "oversized",
    "severity": "error",
    "message": "file is 3500000 bytes, above the maximum of 1000000 bytes"
  }
]
```

```json
{
  "images": 16,
  "total_size_bytes": 11745000,
  "formats": 5,
  "findings": 21,
  "errors": 10,
  "warnings": 11,
  "unused": 3,
  "used_file": true
}
```

`--out` writes the report to a file instead of printing it.

## Options

| Flag | Meaning |
| --- | --- |
| `--used-file` | File listing image URLs or file names found in site content, one per line |
| `--max-size` | Maximum file size in bytes before an image counts as oversized (default: 1000000) |
| `--max-width` | Maximum image width in pixels before an image counts as large (default: 2560) |
| `--max-alt` | Maximum alt text length in characters (default: 125) |
| `--as-of` | Reference date as YYYY-MM-DD (default: today) |
| `--json` | Emit JSON instead of text |
| `--deletable` | After the summary, list the files safe to delete, each with its reason (report only) |
| `--check` | Exit 1 if any error is found |
| `--strict` | With --check, also exit 1 on warnings |
| `--out` | Write the report to a file |

## Edge cases

* Without `--used-file`, the unused-image check is skipped
  and a note line says so; every other check still runs.
* A duplicate hash or duplicate URL row is kept in the
  analysis, because each duplicate is a separate attachment
  that can be deleted. Only the finding marks it.
* A file exactly `--max-size` bytes, or exactly
  `--max-width` px wide, is not flagged; only above the
  limit is flagged. Alt text exactly `--max-alt`
  characters is not long.
* A mime type is taken from the `mime` column when present,
  and otherwise inferred from the file extension. A file
  with neither gets an unknown-format warning instead of an
  error.
* A non-image file skips the alt text and dimension checks,
  because those rules do not apply to it.
* A blank line in the file is skipped silently. A row with
  too many or too few fields is a malformed-row error and is
  skipped; the rest of the file is still analyzed.
* Hash and URL duplicate matching is case-insensitive.
* Size values may contain commas, as in `"1,200,000"`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

91 tests, all passing: alt text rules including the
filename, camera, screenshot, generic-word, short, and long
cases, size and dimension limits and their boundaries,
duplicate hashes and URLs, every supported and unsupported
format, mime inference from extensions, the usage list
including URL and base-name matching, malformed rows,
missing columns, header aliases, BOM headers, invalid,
missing, and future dates, sample counts, JSON output
shape, `--check` and `--strict` exit codes, and the
`--deletable` safe-to-delete list. The same 91 tests pass
under pytest.

## License

MIT. See [LICENSE](LICENSE).
