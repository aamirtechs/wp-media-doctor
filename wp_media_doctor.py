"""WordPress media library CSV audit CLI.

Reads a WordPress media library CSV export (from a media
library export plugin, or assembled from the wp_posts table)
and audits it for the problems that bloat a site and hurt
its search ranking and accessibility: images with missing or
weak alt text, oversized originals, duplicate files by
content hash, images nothing on the site links to, and files
in formats WordPress does not serve well.

Missing alt text is the most common WordPress accessibility
failure, and it is also an SEO failure: search engines read
alt text to understand an image. Oversized originals are the
most common cause of slow pages, because WordPress serves
the full-size file whenever a theme or block asks for it.
Duplicates pile up because the same image gets uploaded
again under a new name instead of being reused. Media
library plugins audit all of this inside the dashboard;
this tool is the offline audit of the exported list, so a
site owner can check a backup or a staging copy without
installing anything on the live site.

Each problem is a finding with a file name, a rule name, a
severity (error or warning), and a message. Errors are the
ones that are a live accessibility, performance, or data
problem; warnings are files worth following up. --check
exits 1 when any error is found, and --strict also fails
on warnings.

Zero dependencies, Python 3.10 or newer, standard library only.

Usage:
    python3 wp_media_doctor.py examples/media.csv --as-of 2026-11-12
    python3 wp_media_doctor.py media.csv --used-file used.txt --json --check
    python3 wp_media_doctor.py media.csv --max-size 500000 --max-width 1920
    python3 wp_media_doctor.py media.csv --used-file used.txt --deletable
"""

import argparse
import csv
import datetime
import json
import os
import re
import sys

__version__ = "1.0.0"

SUPPORTED_MIMES = frozenset((
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "image/avif", "image/svg+xml",
))

EXTENSION_MIMES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".gif": "image/gif", ".avif": "image/avif",
    ".svg": "image/svg+xml", ".bmp": "image/bmp",
    ".tif": "image/tiff", ".tiff": "image/tiff",
    ".heic": "image/heic", ".heif": "image/heif",
    ".psd": "image/vnd.adobe.photoshop",
    ".pdf": "application/pdf",
}

GENERIC_ALTS = frozenset((
    "image", "photo", "picture", "img", "pic", "logo",
    "banner", "icon", "header", "thumbnail",
))

FILENAME_ALT_RE = re.compile(
    r"^(img|dsc|dscn|screenshot|photo|image|picture|pic|p|wp)"
    r"[-_ ]?\d{2,}([-_ ]\d{2,})*(\.\w+)?$",
    re.IGNORECASE)

GENERIC_ALT_RE = re.compile(
    r"^(image|photo|picture|img|pic|logo|banner|icon|header"
    r"|thumbnail)([-_ ]\d+)?(\.\w+)?$",
    re.IGNORECASE)

DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
    "%Y/%m/%d", "%d/%m/%Y",
)

# Header aliases: the export column names this tool accepts.
COLUMN_ALIASES = {
    "file": ("file", "filename", "file_name", "name"),
    "url": ("url", "file_url", "link", "guid"),
    "alt_text": ("alt_text", "alt", "alttext"),
    "width": ("width",),
    "height": ("height",),
    "size_bytes": ("size_bytes", "size", "filesize", "file_size"),
    "mime": ("mime", "mime_type", "type"),
    "hash": ("hash", "content_hash", "md5", "sha256"),
    "uploaded": ("uploaded", "upload_date", "date", "uploaded_at"),
}

REQUIRED_COLUMNS = ("file", "url")

DEFAULT_MAX_SIZE = 1000000
DEFAULT_MAX_WIDTH = 2560
DEFAULT_MAX_ALT = 125


class Finding:
    """One audit finding for one file or for the library."""

    def __init__(self, name, rule, severity, message):
        self.name = name
        self.rule = rule
        self.severity = severity
        self.message = message

    def as_dict(self):
        """Return the finding as a plain dict."""
        return {"file": self.name, "rule": self.rule,
                "severity": self.severity, "message": self.message}

    def __str__(self):
        return "%s [%s] %s: %s" % (self.severity.upper(), self.rule,
                                   self.name, self.message)


def parse_date(value):
    """Parse a date string, or return None when it is invalid.

    Accepted formats are YYYY-MM-DD, YYYY-MM-DD HH:MM:SS, ISO
    datetime with T, YYYY/MM/DD, and DD/MM/YYYY. A blank value
    returns None.
    """
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(value):
    """Parse an integer string, tolerating commas and spaces.

    Returns None when the value is blank or not an integer.
    """
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def is_image_mime(mime):
    """Return True when the mime type is an image type."""
    return mime.startswith("image/")


def mime_for_file(filename, mime):
    """Return the effective mime type for one row.

    The mime column wins when present. Otherwise the type is
    inferred from the file extension. Returns an empty string
    when neither gives a type.
    """
    if mime:
        return mime.strip().lower()
    _, ext = os.path.splitext(filename or "")
    return EXTENSION_MIMES.get(ext.lower(), "")


def is_weak_alt(alt, filename):
    """Return True when the alt text is weak.

    Weak means the alt text is the file name itself, a
    camera or screenshot file name pattern, a bare generic
    word such as "image" or "photo" (optionally numbered),
    or shorter than 3 characters. Any of those tells a
    screen reader and a search engine nothing about the
    image.
    """
    text = alt.strip()
    if len(text) < 3:
        return True
    lowered = text.lower()
    base, _ = os.path.splitext(filename or "")
    if lowered == (filename or "").lower() \
            or lowered == base.lower():
        return True
    if FILENAME_ALT_RE.match(text):
        return True
    if GENERIC_ALT_RE.match(text):
        return True
    if lowered in GENERIC_ALTS:
        return True
    return False


def resolve_columns(header):
    """Map export header names to the canonical column names.

    Returns a dict of canonical name to header index, or None
    when a required column is missing. Header matching is
    case-insensitive and ignores surrounding spaces.
    """
    lowered = [name.strip().lower() for name in header]
    resolved = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                resolved[canonical] = lowered.index(alias)
                break
    for required in REQUIRED_COLUMNS:
        if required not in resolved:
            return None
    return resolved


def load_used_file(path):
    """Read a usage list file and return the set of entries.

    One entry per line: an image URL or a file name found in
    site content. Blank lines and lines starting with # are
    ignored. Raises FileNotFoundError or OSError on read
    failure.
    """
    entries = set()
    with open(path, encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#"):
                entries.add(line)
    return entries


def is_used(file, url, entries):
    """Return True when an image appears in the usage list.

    Matches on the full URL, the full file name, or the base
    name of either, so a list of URLs matches a file column
    and a list of file names matches a URL column.
    """
    if url in entries or file in entries:
        return True
    used_basenames = {os.path.basename(entry)
                      for entry in entries}
    if os.path.basename(file) in used_basenames:
        return True
    if os.path.basename(url) in used_basenames:
        return True
    return False


class MediaFile:
    """One media file, parsed from one CSV row."""

    def __init__(self, file, url, alt_text, width, height,
                 size_bytes, mime, file_hash, uploaded):
        self.file = file
        self.url = url
        self.alt_text = alt_text
        self.width = width
        self.height = height
        self.size_bytes = size_bytes
        self.mime = mime
        self.hash = file_hash
        self.uploaded = uploaded


def load_media(path, as_of, max_size, max_width, max_alt,
               used_entries):
    """Read the media CSV and return (files, findings, used).

    A malformed row is reported and skipped, never a crash.
    A duplicate hash or URL is reported and the row is kept,
    because each duplicate is a separate attachment that can
    be deleted. When no usage list is supplied, the
    unused-image check is skipped.
    """
    files = []
    findings = []
    seen_hashes = set()
    seen_urls = set()
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("file is empty, no header row found")
        columns = resolve_columns(header)
        if columns is None:
            raise ValueError(
                "missing required column: one of file, url is "
                "absent from the header")
        expected = len(header)
        for line_no, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != expected:
                findings.append(Finding(
                    "row %d" % line_no, "malformed-row", "error",
                    "row has %d fields but the header has %d, so "
                    "the row was skipped" % (len(row), expected)))
                continue

            def cell(name):
                if name in columns:
                    return row[columns[name]].strip()
                return ""

            file = cell("file")
            url = cell("url")
            alt_text = cell("alt_text")
            mime = mime_for_file(file, cell("mime"))
            display = file or url or "row %d" % line_no
            if not file:
                findings.append(Finding(
                    display, "missing-file", "error",
                    "row has no file name, so the media file "
                    "cannot be identified"))
            if not url:
                findings.append(Finding(
                    display, "missing-url", "error",
                    "row has no URL, so the media file cannot be "
                    "found on the site"))
            if url:
                lowered_url = url.lower()
                if lowered_url in seen_urls:
                    findings.append(Finding(
                        display, "duplicate-url", "warning",
                        "URL %s already appears in this export"
                        % url))
                else:
                    seen_urls.add(lowered_url)
            file_hash = cell("hash")
            if file_hash:
                lowered_hash = file_hash.lower()
                if lowered_hash in seen_hashes:
                    findings.append(Finding(
                        display, "duplicate-file", "error",
                        "content hash %s matches another file in "
                        "this export, so this is a duplicate upload"
                        % file_hash))
                else:
                    seen_hashes.add(lowered_hash)
            if mime:
                if mime not in SUPPORTED_MIMES:
                    findings.append(Finding(
                        display, "unsupported-format", "error",
                        "format %s is not a supported web image "
                        "format, convert it to JPEG, PNG, WebP, "
                        "or AVIF" % mime))
            else:
                findings.append(Finding(
                    display, "unknown-format", "warning",
                    "no mime type and no recognised file "
                    "extension, so the format could not be "
                    "checked"))
            size_text = cell("size_bytes")
            size = None
            if size_text:
                size = parse_int(size_text)
                if size is None:
                    findings.append(Finding(
                        display, "invalid-size", "error",
                        "size %r is not a number of bytes"
                        % size_text))
                elif size < 0:
                    findings.append(Finding(
                        display, "invalid-size", "error",
                        "size %d is negative" % size))
                elif size == 0:
                    findings.append(Finding(
                        display, "empty-file", "error",
                        "file is 0 bytes, so it holds no image"))
                elif size > max_size:
                    findings.append(Finding(
                        display, "oversized", "error",
                        "file is %d bytes, above the maximum of "
                        "%d bytes" % (size, max_size)))
            else:
                findings.append(Finding(
                    display, "missing-size", "error",
                    "no file size recorded, so the file cannot be "
                    "checked for bloat"))
            width_text = cell("width")
            height_text = cell("height")
            width = parse_int(width_text) if width_text else None
            height = parse_int(height_text) if height_text else None
            if is_image_mime(mime):
                if (width_text and width is None) \
                        or (height_text and height is None):
                    findings.append(Finding(
                        display, "invalid-dimensions", "warning",
                        "width or height %r is not a number"
                        % (width_text or height_text)))
                elif width is not None and width <= 0 \
                        or height is not None and height <= 0:
                    findings.append(Finding(
                        display, "invalid-dimensions", "warning",
                        "width or height is zero or negative"))
                elif width is None and height is None:
                    findings.append(Finding(
                        display, "missing-dimensions", "warning",
                        "no width or height recorded, so the "
                        "image dimensions could not be checked"))
                elif width is not None and width > max_width:
                    findings.append(Finding(
                        display, "large-dimensions", "warning",
                        "width %d px is above the maximum of %d px"
                        % (width, max_width)))
            if is_image_mime(mime):
                if not alt_text:
                    findings.append(Finding(
                        display, "missing-alt", "error",
                        "image has no alt text, so screen readers "
                        "and search engines cannot describe it"))
                elif len(alt_text) > max_alt:
                    findings.append(Finding(
                        display, "long-alt", "warning",
                        "alt text is %d characters, above the "
                        "recommended maximum of %d"
                        % (len(alt_text), max_alt)))
                elif is_weak_alt(alt_text, file):
                    findings.append(Finding(
                        display, "weak-alt", "warning",
                        "alt text %r describes nothing about the "
                        "image" % alt_text))
            uploaded_text = cell("uploaded")
            uploaded = parse_date(uploaded_text)
            if uploaded_text and uploaded is None:
                findings.append(Finding(
                    display, "invalid-date", "warning",
                    "upload date %r is not a recognised date"
                    % uploaded_text))
            elif uploaded is not None and uploaded > as_of:
                findings.append(Finding(
                    display, "future-date", "warning",
                    "upload date %s is in the future"
                    % uploaded))
            if used_entries is not None:
                if not is_used(file, url, used_entries):
                    findings.append(Finding(
                        display, "unused-image", "warning",
                        "image appears in no supplied usage list "
                        "entry, so nothing on the site links to it"))
            files.append(MediaFile(file, url, alt_text, width,
                                   height, size, mime, file_hash,
                                   uploaded))
    return files, findings, used_entries is not None


def deletable_files(files, findings):
    """Return the files the audit considers safe to delete.

    This is a report only: nothing is deleted. A file is
    listed when it is a duplicate beyond the first upload of
    its content hash, or when it is an unused image that is
    also oversized or in an unsupported format. An unused
    image that is otherwise clean is not listed, because an
    unused image may still be wanted. Each entry names the
    reason the file is on the list.
    """
    duplicate = set()
    unused = set()
    oversized = set()
    unsupported = set()
    for finding in findings:
        if finding.rule == "duplicate-file":
            duplicate.add(finding.name)
        elif finding.rule == "unused-image":
            unused.add(finding.name)
        elif finding.rule == "oversized":
            oversized.add(finding.name)
        elif finding.rule == "unsupported-format":
            unsupported.add(finding.name)
    listed = []
    for item in files:
        name = item.file or item.url
        reasons = []
        if name in duplicate:
            reasons.append(
                "duplicate of an earlier upload of the same "
                "content hash")
        if name in unused and is_image_mime(item.mime or ""):
            parts = []
            if name in oversized:
                parts.append("oversized")
            if name in unsupported:
                parts.append("unsupported format")
            if parts:
                reasons.append(
                    "unused and " + " and ".join(parts))
        if reasons:
            listed.append({"file": name,
                           "reason": "; ".join(reasons)})
    return listed


def analyze_file(path, as_of=None, max_size=DEFAULT_MAX_SIZE,
                 max_width=DEFAULT_MAX_WIDTH,
                 max_alt=DEFAULT_MAX_ALT, used_file=None,
                 deletable=False):
    """Audit one media file and return the report dict.

    With deletable=True the report also carries the
    deletable list: the files safe to delete, each with the
    reason it is on the list.
    """
    if as_of is None:
        as_of = datetime.date.today()
    used_entries = None
    if used_file is not None:
        used_entries = load_used_file(used_file)
    files, findings, used = load_media(
        path, as_of, max_size, max_width, max_alt, used_entries)
    mime_counts = {}
    mime_sizes = {}
    total_size = 0
    for item in files:
        mime = item.mime or "(unknown)"
        mime_counts[mime] = mime_counts.get(mime, 0) + 1
        if item.size_bytes:
            mime_sizes[mime] = mime_sizes.get(mime, 0) \
                + item.size_bytes
            total_size += item.size_bytes
    format_rows = [{"mime": mime, "images": mime_counts[mime],
                    "size_bytes": mime_sizes.get(mime, 0)}
                   for mime in sorted(mime_counts)]
    unused = sum(1 for f in findings if f.rule == "unused-image")
    summary = {
        "images": len(files),
        "total_size_bytes": total_size,
        "formats": len(mime_counts),
        "findings": len(findings),
        "errors": sum(1 for f in findings if f.severity == "error"),
        "warnings": sum(1 for f in findings
                        if f.severity == "warning"),
        "unused": unused,
        "used_file": used,
    }
    report = {"summary": summary, "formats": format_rows,
              "findings": [f.as_dict() for f in findings]}
    if deletable:
        report["deletable"] = deletable_files(files, findings)
    return report


def format_text(report):
    """Render the audit as plain text."""
    summary = report["summary"]
    lines = []
    for finding in report["findings"]:
        lines.append("%s [%s] %s: %s"
                     % (finding["severity"].upper(),
                        finding["rule"], finding["file"],
                        finding["message"]))
    if report["formats"]:
        lines.append("")
        lines.append("Per format:")
        for row in report["formats"]:
            noun = "image" if row["images"] == 1 else "images"
            lines.append("%s: %d %s, %d bytes"
                         % (row["mime"], row["images"], noun,
                            row["size_bytes"]))
    lines.append("")
    lines.append("Images: %d, total size: %d bytes, findings: %d, "
                 "errors: %d, warnings: %d"
                 % (summary["images"], summary["total_size_bytes"],
                    summary["findings"], summary["errors"],
                    summary["warnings"]))
    if not summary["used_file"]:
        lines.append("Note: no --used-file supplied, so "
                     "unused-image checks were skipped.")
    if not report["findings"]:
        lines.append("All media clean.")
    if "deletable" in report:
        lines.append("")
        lines.append("Safe to delete (report only, nothing is "
                     "deleted):")
        if report["deletable"]:
            for entry in report["deletable"]:
                lines.append("- %s: %s"
                             % (entry["file"], entry["reason"]))
        else:
            lines.append("- none.")
    return "\n".join(lines) + "\n"


def format_json(report):
    """Render the audit as JSON."""
    return json.dumps(report, indent=2) + "\n"


def parse_as_of(value):
    """Parse a YYYY-MM-DD reference date, or raise ValueError."""
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            "--as-of must be a YYYY-MM-DD date, got %r" % value)


def main(argv=None):
    """Entry point for the wp-media-doctor CLI."""
    parser = argparse.ArgumentParser(
        description="Audit a WordPress media library CSV export "
                    "for missing or weak alt text, oversized "
                    "originals, duplicate files, unused images, "
                    "and unsupported formats.")
    parser.add_argument("path", help="CSV file of media library")
    parser.add_argument("--used-file",
                        help="file listing image URLs or file names "
                             "found in site content, one per line")
    parser.add_argument("--max-size", type=int,
                        default=DEFAULT_MAX_SIZE,
                        help="maximum file size in bytes before an "
                             "image counts as oversized "
                             "(default: 1000000)")
    parser.add_argument("--max-width", type=int,
                        default=DEFAULT_MAX_WIDTH,
                        help="maximum image width in pixels before "
                             "an image counts as large "
                             "(default: 2560)")
    parser.add_argument("--max-alt", type=int,
                        default=DEFAULT_MAX_ALT,
                        help="maximum alt text length in characters "
                             "(default: 125)")
    parser.add_argument("--as-of", default=None,
                        help="reference date as YYYY-MM-DD "
                             "(default: today)")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of text")
    parser.add_argument("--deletable", action="store_true",
                        help="after the summary, list the files "
                             "the audit considers safe to delete "
                             "(report only)")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any error is found")
    parser.add_argument("--strict", action="store_true",
                        help="with --check, also exit 1 on warnings")
    parser.add_argument("--out", help="write the report to a file")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    try:
        as_of = parse_as_of(args.as_of) if args.as_of else None
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if args.max_size <= 0:
        print("error: --max-size must be above 0", file=sys.stderr)
        return 2
    if args.max_width <= 0:
        print("error: --max-width must be above 0", file=sys.stderr)
        return 2
    if args.max_alt <= 0:
        print("error: --max-alt must be above 0", file=sys.stderr)
        return 2
    try:
        report = analyze_file(args.path, as_of=as_of,
                              max_size=args.max_size,
                              max_width=args.max_width,
                              max_alt=args.max_alt,
                              used_file=args.used_file,
                              deletable=args.deletable)
    except FileNotFoundError:
        print("error: file not found: %s" % args.path, file=sys.stderr)
        return 2
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.path, exc),
              file=sys.stderr)
        return 2
    if args.json:
        output = format_json(report)
    else:
        output = format_text(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output)
    else:
        print(output, end="")
    summary = report["summary"]
    if args.check:
        if summary["errors"]:
            return 1
        if args.strict and summary["warnings"]:
            return 1
    return 0


def main_entry():
    """Console script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    main_entry()
