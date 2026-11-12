# Good first issues

Seeded issues for new contributors. File each one on GitHub with
the `good first issue` and `help wanted` labels.

## 1. Add a per-image savings estimate

Title: Show how many bytes each oversized image could save

Description: Add a --savings flag that, after the per-format
table, prints one line per oversized image with its current
size and an estimated size after resizing to --max-width and
recompressing to 80 percent of its current bytes, so a site
owner can see the total saving at a glance. The summary
gains a "potential_savings_bytes" field in JSON output.

Difficulty: Easy

Acceptance criteria: the sample file shows IMG_4521.jpg at
3,500,000 bytes with an estimated saving, and the total
saving is the sum of the per-image estimates; a test checks
the estimate math; README documents the flag.

## 2. Add a suggested-action line per finding

Title: Print what to do about each flagged image

Description: Each finding already says what is wrong. Add a
short suggested action to the text output, for example
"write descriptive alt text" for a missing alt, "compress
or resize before uploading" for an oversized original, or
"delete the duplicate, keep the first upload" for a
duplicate file, so a site owner who is not a WordPress
expert knows the next step. The JSON output gains an
"action" field per finding.

Difficulty: Easy

Acceptance criteria: the sample file shows an action for
every finding; the JSON findings carry the action field; a
test covers the mapping; README documents the actions.

## 3. Support the WordPress REST API media export

Title: Accept wp-json media JSON input

Description: Add a --format json option so the tool can read
the JSON output of the WordPress REST API media endpoint
(`/wp-json/wp/v2/media`) directly, mapping its fields
(source_url, alt_text, media_details.width,
media_details.height, media_details.filesize, mime_type,
date) onto the same checks and the same output. The usage
list check still works from the media URLs.

Difficulty: Medium

Acceptance criteria: the sample media as JSON produces the
same 21 findings as the CSV; a test round-trips both
formats; README documents the option.

## 4. Add a --fix-dry-run that lists the safe deletions

Title: List the files that are safe to delete

Description: Add a --deletable flag that prints, after the
summary, the list of files the audit considers safe to
delete: duplicate files beyond the first upload of each
hash, and unused images that are also oversized or in an
unsupported format. The list is a report only, nothing is
deleted, and each line names the reason. Files that are
unused but otherwise clean are not listed, because an
unused image may still be wanted.

Difficulty: Medium

Acceptance criteria: the sample file lists product-a.jpg as
a duplicate and old-scan.tiff as unused and oversized, and
does not list team-photo.jpg; a test checks the list;
README documents the flag.
