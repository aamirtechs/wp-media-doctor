# Changelog

## Unreleased

* `--deletable` prints, after the summary, the files the
  audit considers safe to delete: duplicate uploads beyond
  the first of each content hash, and unused images that are
  also oversized or in an unsupported format. Each line
  names the reason; the list is a report only, and an unused
  image that is otherwise clean stays off it.

## 1.0.0 - 2026-11-12

Initial release.

* WordPress media library audit over a CSV export (id,
  file, url, alt_text, width, height, size_bytes, mime,
  hash, uploaded): missing or weak alt text, oversized
  originals, duplicate files by content hash, unused images
  against a supplied usage list, and unsupported formats.
* Alt text rules: missing alt is an error; weak alt is a
  warning for alt text that is the file name, a camera or
  screenshot file name pattern, a bare generic word such as
  image or photo, or shorter than 3 characters; alt text
  above --max-alt (default 125 characters) is a long-alt
  warning.
* Size and dimension rules: oversized files above --max-size
  (default 1,000,000 bytes), empty files, invalid, negative,
  and missing sizes, widths above --max-width (default 2560
  px), and missing or invalid dimensions.
* Duplicate and format rules: duplicate content hashes are
  errors and duplicate URLs are warnings, both kept in the
  analysis; TIFF, HEIC, PDF, and other formats outside
  JPEG, PNG, WebP, GIF, AVIF, and SVG are unsupported-format
  errors; mime is inferred from the file extension when the
  mime column is blank.
* Unused-image check against a --used-file list of image
  URLs or file names found in site content, matched on full
  URL, full file name, or base name; skipped with a note
  when no usage list is supplied.
* Data errors reported and skipped, never a crash: missing
  files and URLs, malformed rows, invalid and future upload
  dates. Non-image files skip the alt text and dimension
  checks.
* A per-format table counts images and bytes by mime type,
  and the summary reports images, total size, findings,
  errors, warnings, and unused images.
* Text and --json output, --out file output, and a --check CI
  gate that exits 1 on errors (and on warnings with --strict).
  --as-of pins the reference date, --max-size, --max-width,
  and --max-alt tune the thresholds.
* Zero dependencies, Python 3.10 or newer.
