"""Tests for wp-media-doctor."""

import datetime
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import wp_media_doctor

AS_OF = datetime.date(2026, 11, 12)

HEADER = ("id,file,url,alt_text,width,height,size_bytes,mime,"
          "hash,uploaded\n")


def row(file="a.jpg", url="https://example.com/a.jpg",
        alt="A red bicycle", width="800", height="600",
        size="100000", mime="image/jpeg", file_hash="abc123",
        uploaded="2026-01-01", row_id="1"):
    """Build one CSV row with sensible defaults."""
    return ",".join((row_id, file, url, alt, width, height, size,
                     mime, file_hash, uploaded)) + "\n"


def run_csv(text, as_of=AS_OF, **kwargs):
    """Write text to a temp CSV and analyze it."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8")
    handle.write(text)
    handle.close()
    try:
        return wp_media_doctor.analyze_file(
            handle.name, as_of=as_of, **kwargs)
    finally:
        os.unlink(handle.name)


def rules(report):
    """Return the list of (rule, severity) pairs in a report."""
    return [(f["rule"], f["severity"])
            for f in report["findings"]]


def has_rule(report, rule, severity=None):
    """Return True when the report has a finding for the rule."""
    for finding in report["findings"]:
        if finding["rule"] == rule:
            if severity is None or finding["severity"] == severity:
                return True
    return False


class TestAltText(unittest.TestCase):
    """Missing, weak, and long alt text."""

    def test_missing_alt_is_error(self):
        report = run_csv(HEADER + row(alt=""))
        self.assertTrue(has_rule(report, "missing-alt", "error"))

    def test_good_alt_is_clean(self):
        report = run_csv(HEADER + row())
        self.assertEqual(report["findings"], [])

    def test_alt_equal_to_filename_is_weak(self):
        report = run_csv(HEADER + row(file="IMG_4521.jpg",
                                      alt="IMG_4521.jpg"))
        self.assertTrue(has_rule(report, "weak-alt", "warning"))

    def test_alt_equal_to_basename_is_weak(self):
        report = run_csv(HEADER + row(file="team-photo.jpg",
                                      alt="team-photo"))
        self.assertTrue(has_rule(report, "weak-alt", "warning"))

    def test_camera_filename_alt_is_weak(self):
        report = run_csv(HEADER + row(file="dsc_0042.jpg",
                                      alt="DSC_0042"))
        self.assertTrue(has_rule(report, "weak-alt", "warning"))

    def test_screenshot_filename_alt_is_weak(self):
        report = run_csv(HEADER + row(
            file="screenshot-2024-05-01.png",
            alt="screenshot-2024-05-01"))
        self.assertTrue(has_rule(report, "weak-alt", "warning"))

    def test_generic_word_alt_is_weak(self):
        for alt in ("image", "photo", "picture", "img", "logo",
                    "image 1", "Photo 2"):
            with self.subTest(alt=alt):
                report = run_csv(HEADER + row(alt=alt))
                self.assertTrue(has_rule(report, "weak-alt",
                                         "warning"))

    def test_one_character_alt_is_weak(self):
        report = run_csv(HEADER + row(alt="x"))
        self.assertTrue(has_rule(report, "weak-alt", "warning"))

    def test_two_character_alt_is_weak(self):
        report = run_csv(HEADER + row(alt="ab"))
        self.assertTrue(has_rule(report, "weak-alt", "warning"))

    def test_descriptive_alt_is_not_weak(self):
        report = run_csv(HEADER + row(
            alt="Group photo of the support team"))
        self.assertFalse(has_rule(report, "weak-alt"))

    def test_alt_with_photo_inside_is_not_weak(self):
        report = run_csv(HEADER + row(
            alt="Team photo at the office"))
        self.assertFalse(has_rule(report, "weak-alt"))

    def test_long_alt_is_warning(self):
        report = run_csv(HEADER + row(alt="a" * 126))
        self.assertTrue(has_rule(report, "long-alt", "warning"))

    def test_alt_at_limit_is_clean(self):
        report = run_csv(HEADER + row(alt="a" * 125))
        self.assertFalse(has_rule(report, "long-alt"))

    def test_long_alt_limit_is_tunable(self):
        report = run_csv(HEADER + row(alt="a" * 60), max_alt=50)
        self.assertTrue(has_rule(report, "long-alt", "warning"))

    def test_non_image_skips_alt_check(self):
        report = run_csv(HEADER + row(
            file="brochure.pdf", mime="application/pdf", alt="",
            width="", height=""))
        self.assertFalse(has_rule(report, "missing-alt"))
        self.assertFalse(has_rule(report, "weak-alt"))

    def test_is_weak_alt_unit(self):
        self.assertTrue(wp_media_doctor.is_weak_alt(
            "IMG_1234.jpg", "IMG_1234.jpg"))
        self.assertTrue(wp_media_doctor.is_weak_alt(
            "photo", "photo.jpg"))
        self.assertTrue(wp_media_doctor.is_weak_alt(
            "ab", "photo.jpg"))
        self.assertFalse(wp_media_doctor.is_weak_alt(
            "A red bicycle leaning on a fence", "bike.jpg"))


class TestSizeAndDimensions(unittest.TestCase):
    """Oversized, empty, invalid size, and dimension rules."""

    def test_oversized_is_error(self):
        report = run_csv(HEADER + row(size="1200000"))
        self.assertTrue(has_rule(report, "oversized", "error"))

    def test_size_at_limit_is_clean(self):
        report = run_csv(HEADER + row(size="1000000"))
        self.assertFalse(has_rule(report, "oversized"))

    def test_max_size_is_tunable(self):
        report = run_csv(HEADER + row(size="600000"),
                         max_size=500000)
        self.assertTrue(has_rule(report, "oversized", "error"))

    def test_empty_file_is_error(self):
        report = run_csv(HEADER + row(size="0"))
        self.assertTrue(has_rule(report, "empty-file", "error"))

    def test_invalid_size_is_error(self):
        report = run_csv(HEADER + row(size="not-a-number"))
        self.assertTrue(has_rule(report, "invalid-size", "error"))

    def test_negative_size_is_error(self):
        report = run_csv(HEADER + row(size="-5"))
        self.assertTrue(has_rule(report, "invalid-size", "error"))

    def test_missing_size_is_error(self):
        report = run_csv(HEADER + row(size=""))
        self.assertTrue(has_rule(report, "missing-size", "error"))

    def test_size_with_commas_parses(self):
        text = HEADER + '1,a.jpg,https://example.com/a.jpg,' \
            'A red bicycle,800,600,"1,200,000",image/jpeg,' \
            'abc123,2026-01-01\n'
        report = run_csv(text)
        self.assertTrue(has_rule(report, "oversized", "error"))

    def test_large_width_is_warning(self):
        report = run_csv(HEADER + row(width="4000"))
        self.assertTrue(has_rule(report, "large-dimensions",
                                 "warning"))

    def test_width_at_limit_is_clean(self):
        report = run_csv(HEADER + row(width="2560"))
        self.assertFalse(has_rule(report, "large-dimensions"))

    def test_max_width_is_tunable(self):
        report = run_csv(HEADER + row(width="2000"),
                         max_width=1920)
        self.assertTrue(has_rule(report, "large-dimensions",
                                 "warning"))

    def test_missing_dimensions_is_warning(self):
        report = run_csv(HEADER + row(width="", height=""))
        self.assertTrue(has_rule(report, "missing-dimensions",
                                 "warning"))

    def test_invalid_dimensions_is_warning(self):
        report = run_csv(HEADER + row(width="wide"))
        self.assertTrue(has_rule(report, "invalid-dimensions",
                                 "warning"))

    def test_zero_dimensions_is_warning(self):
        report = run_csv(HEADER + row(width="0"))
        self.assertTrue(has_rule(report, "invalid-dimensions",
                                 "warning"))

    def test_non_image_skips_dimension_checks(self):
        report = run_csv(HEADER + row(
            file="brochure.pdf", mime="application/pdf", alt="",
            width="", height=""))
        self.assertFalse(has_rule(report, "missing-dimensions"))
        self.assertFalse(has_rule(report, "invalid-dimensions"))


class TestDuplicatesAndFormats(unittest.TestCase):
    """Duplicate hashes and URLs, and unsupported formats."""

    def test_duplicate_hash_is_error(self):
        text = HEADER + row(row_id="1") + row(
            file="b.jpg", url="https://example.com/b.jpg",
            row_id="2")
        report = run_csv(text)
        self.assertTrue(has_rule(report, "duplicate-file", "error"))
        self.assertEqual(report["summary"]["images"], 2)

    def test_same_hash_different_case_is_duplicate(self):
        text = HEADER + row(file_hash="ABC123") + row(
            file="b.jpg", url="https://example.com/b.jpg",
            file_hash="abc123", row_id="2")
        report = run_csv(text)
        self.assertTrue(has_rule(report, "duplicate-file", "error"))

    def test_empty_hash_is_not_a_duplicate(self):
        text = HEADER + row(file_hash="") + row(
            file="b.jpg", url="https://example.com/b.jpg",
            file_hash="", row_id="2")
        report = run_csv(text)
        self.assertFalse(has_rule(report, "duplicate-file"))

    def test_duplicate_url_is_warning(self):
        text = HEADER + row(row_id="1") + row(
            file="b.jpg", file_hash="zzz999", row_id="2")
        report = run_csv(text)
        self.assertTrue(has_rule(report, "duplicate-url", "warning"))

    def test_unsupported_tiff_is_error(self):
        report = run_csv(HEADER + row(mime="image/tiff"))
        self.assertTrue(has_rule(report, "unsupported-format",
                                 "error"))

    def test_unsupported_heic_is_error(self):
        report = run_csv(HEADER + row(mime="image/heic"))
        self.assertTrue(has_rule(report, "unsupported-format",
                                 "error"))

    def test_unsupported_pdf_is_error(self):
        report = run_csv(HEADER + row(
            file="brochure.pdf", mime="application/pdf", alt="",
            width="", height=""))
        self.assertTrue(has_rule(report, "unsupported-format",
                                 "error"))

    def test_supported_formats_are_clean(self):
        for mime in ("image/jpeg", "image/png", "image/webp",
                     "image/gif", "image/avif", "image/svg+xml"):
            with self.subTest(mime=mime):
                report = run_csv(HEADER + row(mime=mime))
                self.assertFalse(
                    has_rule(report, "unsupported-format"))

    def test_mime_inferred_from_extension(self):
        report = run_csv(HEADER + row(mime="", file="scan.tiff"))
        self.assertTrue(has_rule(report, "unsupported-format",
                                 "error"))

    def test_jpg_extension_infers_supported_mime(self):
        report = run_csv(HEADER + row(mime=""))
        self.assertFalse(has_rule(report, "unsupported-format"))
        self.assertFalse(has_rule(report, "unknown-format"))

    def test_unknown_extension_is_warning(self):
        report = run_csv(HEADER + row(mime="", file="odd.xyz"))
        self.assertTrue(has_rule(report, "unknown-format",
                                 "warning"))

    def test_mime_case_is_normalised(self):
        report = run_csv(HEADER + row(mime="IMAGE/JPEG"))
        self.assertFalse(has_rule(report, "unsupported-format"))


class TestUnusedImages(unittest.TestCase):
    """The --used-file unused-image check."""

    def _used_file(self, lines):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8")
        handle.write("\n".join(lines) + "\n")
        handle.close()
        return handle.name

    def test_no_used_file_skips_check(self):
        report = run_csv(HEADER + row())
        self.assertFalse(has_rule(report, "unused-image"))
        self.assertFalse(report["summary"]["used_file"])

    def test_used_by_url_is_clean(self):
        path = self._used_file(["https://example.com/a.jpg"])
        try:
            report = run_csv(HEADER + row(), used_file=path)
        finally:
            os.unlink(path)
        self.assertFalse(has_rule(report, "unused-image"))
        self.assertTrue(report["summary"]["used_file"])

    def test_used_by_basename_is_clean(self):
        path = self._used_file(["a.jpg"])
        try:
            report = run_csv(HEADER + row(), used_file=path)
        finally:
            os.unlink(path)
        self.assertFalse(has_rule(report, "unused-image"))

    def test_unused_is_warning(self):
        path = self._used_file(["https://example.com/other.jpg"])
        try:
            report = run_csv(HEADER + row(), used_file=path)
        finally:
            os.unlink(path)
        self.assertTrue(has_rule(report, "unused-image", "warning"))
        self.assertEqual(report["summary"]["unused"], 1)

    def test_used_file_comments_and_blanks_ignored(self):
        path = self._used_file(["# a comment", "",
                                "https://example.com/a.jpg"])
        try:
            report = run_csv(HEADER + row(), used_file=path)
        finally:
            os.unlink(path)
        self.assertFalse(has_rule(report, "unused-image"))

    def test_missing_used_file_is_error(self):
        with self.assertRaises(FileNotFoundError):
            run_csv(HEADER + row(), used_file="/nonexistent.txt")

    def test_is_used_unit(self):
        entries = {"https://example.com/a.jpg", "b.jpg"}
        self.assertTrue(wp_media_doctor.is_used(
            "a.jpg", "https://example.com/a.jpg", entries))
        self.assertTrue(wp_media_doctor.is_used(
            "b.jpg", "https://example.com/b.jpg", entries))
        self.assertFalse(wp_media_doctor.is_used(
            "c.jpg", "https://example.com/c.jpg", entries))


class TestRowsAndHeaders(unittest.TestCase):
    """Malformed rows, missing columns, aliases, dates."""

    def test_malformed_row_is_error_and_skipped(self):
        text = HEADER + row() + "13,short,short\n"
        report = run_csv(text)
        self.assertTrue(has_rule(report, "malformed-row", "error"))
        self.assertEqual(report["summary"]["images"], 1)

    def test_row_with_too_many_fields_is_malformed(self):
        text = HEADER + row() + "2,b.jpg,https://example.com/b.jpg," \
            "Alt,800,600,1000,image/jpeg,hash,2026-01-01,extra\n"
        report = run_csv(text)
        self.assertTrue(has_rule(report, "malformed-row", "error"))
        self.assertEqual(report["summary"]["images"], 1)

    def test_blank_lines_are_skipped(self):
        report = run_csv(HEADER + "\n" + row() + "\n")
        self.assertEqual(report["summary"]["images"], 1)
        self.assertEqual(report["findings"], [])

    def test_missing_file_is_error(self):
        report = run_csv(HEADER + row(file=""))
        self.assertTrue(has_rule(report, "missing-file", "error"))

    def test_missing_url_is_error(self):
        report = run_csv(HEADER + row(url=""))
        self.assertTrue(has_rule(report, "missing-url", "error"))

    def test_missing_required_column_raises(self):
        text = "id,alt_text,width,height\n1,Alt,800,600\n"
        with self.assertRaises(ValueError):
            run_csv(text)

    def test_empty_file_raises(self):
        with self.assertRaises(ValueError):
            run_csv("")

    def test_header_aliases_are_accepted(self):
        text = ("filename,file_url,alt,width,height,size,"
                "mime_type,md5,upload_date\n"
                "a.jpg,https://example.com/a.jpg,A red bicycle,"
                "800,600,100000,image/jpeg,abc123,2026-01-01\n")
        report = run_csv(text)
        self.assertEqual(report["findings"], [])

    def test_bom_header_is_accepted(self):
        report = run_csv("\ufeff" + HEADER + row())
        self.assertEqual(report["findings"], [])

    def test_invalid_upload_date_is_warning(self):
        report = run_csv(HEADER + row(uploaded="not-a-date"))
        self.assertTrue(has_rule(report, "invalid-date", "warning"))

    def test_future_upload_date_is_warning(self):
        report = run_csv(HEADER + row(uploaded="2027-01-01"))
        self.assertTrue(has_rule(report, "future-date", "warning"))

    def test_upload_date_on_as_of_is_clean(self):
        report = run_csv(HEADER + row(uploaded="2026-11-12"))
        self.assertFalse(has_rule(report, "future-date"))

    def test_parse_date_formats(self):
        parse = wp_media_doctor.parse_date
        self.assertEqual(parse("2026-01-02"),
                         datetime.date(2026, 1, 2))
        self.assertEqual(parse("2026-01-02 09:00:00"),
                         datetime.date(2026, 1, 2))
        self.assertEqual(parse("2026/01/02"),
                         datetime.date(2026, 1, 2))
        self.assertEqual(parse("02/01/2026"),
                         datetime.date(2026, 1, 2))
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("not-a-date"))


class TestOutputAndCli(unittest.TestCase):
    """Summary counts, JSON, text, --check, --strict, --out."""

    def _sample_path(self):
        base = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        return os.path.join(base, "examples", "media.csv")

    def _used_path(self):
        base = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        return os.path.join(base, "examples", "used.txt")

    def test_sample_counts(self):
        report = wp_media_doctor.analyze_file(
            self._sample_path(), as_of=AS_OF,
            used_file=self._used_path())
        summary = report["summary"]
        self.assertEqual(summary["images"], 16)
        self.assertEqual(summary["total_size_bytes"], 11745000)
        self.assertEqual(summary["findings"], 21)
        self.assertEqual(summary["errors"], 10)
        self.assertEqual(summary["warnings"], 11)
        self.assertEqual(summary["unused"], 3)

    def test_sample_format_table(self):
        report = wp_media_doctor.analyze_file(
            self._sample_path(), as_of=AS_OF,
            used_file=self._used_path())
        by_mime = {row["mime"]: row["images"]
                   for row in report["formats"]}
        self.assertEqual(by_mime["image/jpeg"], 10)
        self.assertEqual(by_mime["image/png"], 3)
        self.assertEqual(by_mime["image/svg+xml"], 1)
        self.assertEqual(by_mime["image/tiff"], 1)
        self.assertEqual(by_mime["application/pdf"], 1)

    def test_clean_sample_is_clean(self):
        base = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        report = wp_media_doctor.analyze_file(
            os.path.join(base, "examples", "clean.csv"),
            as_of=AS_OF)
        self.assertEqual(report["summary"]["findings"], 0)
        self.assertEqual(report["summary"]["images"], 3)

    def test_warnings_only_sample(self):
        base = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        report = wp_media_doctor.analyze_file(
            os.path.join(base, "examples", "warnings-only.csv"),
            as_of=AS_OF)
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(report["summary"]["warnings"], 3)

    def test_text_output_mentions_no_used_file(self):
        report = run_csv(HEADER + row())
        text = wp_media_doctor.format_text(report)
        self.assertIn("no --used-file supplied", text)
        self.assertIn("All media clean.", text)

    def test_text_output_summary_line(self):
        report = run_csv(HEADER + row())
        text = wp_media_doctor.format_text(report)
        self.assertIn("Images: 1, total size: 100000 bytes", text)

    def test_json_output_shape(self):
        report = run_csv(HEADER + row(alt=""))
        parsed = json.loads(wp_media_doctor.format_json(report))
        self.assertEqual(parsed["summary"]["images"], 1)
        self.assertEqual(parsed["findings"][0]["rule"],
                         "missing-alt")
        self.assertEqual(parsed["findings"][0]["severity"], "error")

    def test_check_exits_1_on_error(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(HEADER + row(alt=""))
        handle.close()
        try:
            self.assertEqual(
                wp_media_doctor.main([handle.name, "--check"]), 1)
        finally:
            os.unlink(handle.name)

    def test_check_exits_0_on_warnings_only(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(HEADER + row(alt="photo"))
        handle.close()
        try:
            self.assertEqual(
                wp_media_doctor.main([handle.name, "--check"]), 0)
            self.assertEqual(
                wp_media_doctor.main(
                    [handle.name, "--check", "--strict"]), 1)
        finally:
            os.unlink(handle.name)

    def test_check_exits_0_on_clean(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(HEADER + row())
        handle.close()
        try:
            self.assertEqual(
                wp_media_doctor.main(
                    [handle.name, "--check", "--strict"]), 0)
        finally:
            os.unlink(handle.name)

    def test_missing_file_exits_2(self):
        saved = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self.assertEqual(
                wp_media_doctor.main(["/nonexistent.csv"]), 2)
        finally:
            sys.stderr = saved

    def test_bad_as_of_exits_2(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(HEADER + row())
        handle.close()
        saved = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self.assertEqual(
                wp_media_doctor.main(
                    [handle.name, "--as-of", "not-a-date"]), 2)
        finally:
            sys.stderr = saved
            os.unlink(handle.name)

    def test_out_writes_file(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(HEADER + row())
        handle.close()
        out = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False)
        out.close()
        try:
            self.assertEqual(
                wp_media_doctor.main(
                    [handle.name, "--out", out.name]), 0)
            with open(out.name, encoding="utf-8") as read:
                self.assertIn("All media clean.", read.read())
        finally:
            os.unlink(handle.name)
            os.unlink(out.name)

    def test_version_flag(self):
        with self.assertRaises(SystemExit) as caught:
            wp_media_doctor.main(["--version"])
        self.assertEqual(caught.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
