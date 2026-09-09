"""
Created: 2026-09-09
Purpose: Tests for Markdown Nav's tag recognition, scope resolution, and label extraction —
	the rules documented in readme.md ("How tags are defined"). Also covers the outline's
	major-level rule that Jump to Header's first panel depends on.
Usage: py tests/test_tags.py     (from the MarkdownNav folder)
	Exits non-zero and prints each failing case.
Notes: mdnav.py imports `sublime` and `sublime_plugin`, which only exist inside Sublime, so
	this stubs both into sys.modules before importing it. Only enough surface is stubbed for
	the module to import and for _config() to read settings — the TextCommands aren't
	exercised here, just the pure helpers underneath them.
	Excluded from the installed package via .gitattributes export-ignore.
"""

import os, sys, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_settings = {}


class _FakeSettings:
	def get(self, key, default=None): return _settings.get(key, default)


_sublime = types.ModuleType("sublime")
_sublime.status_message = lambda *a, **k: None
_sublime.load_settings = lambda name: _FakeSettings()
_sublime.set_timeout = lambda fn, ms: None
_sublime.Region = lambda a, b=None: (a, b)
_sublime_plugin = types.ModuleType("sublime_plugin")
_sublime_plugin.TextCommand = type("TextCommand", (object,), {})
sys.modules["sublime"] = _sublime
sys.modules["sublime_plugin"] = _sublime_plugin

import mdnav

FAILS = []


def check(name, got, want):
	if got != want: FAILS.append("%s\n  expected: %r\n  got:      %r" % (name, want, got))


def tags_of(line, pattern=mdnav.DEFAULT_TAG_NAME):
	kw, hs, only = mdnav._tag_res(pattern)
	return mdnav._extract_tags(line, kw, hs, only)


# ---------- recognition: keyword form ----------

for line, want in [
	("heather: lunch on Saturday", ["heather"]),
	("**heather:** lunch on Saturday", ["heather"]),
	("**heather**: lunch on Saturday", ["heather"]),
	("  issue: bad bearings", ["issue"]),
	("## person: Heather", ["person"]),
	# not tags
	("mobilenotes://abc123", []),
	("http://example.com", []),
	("mailto:foo@bar.com", []),
	("key:value", []),				# no space after the colon
	("M: some text", []),			# uppercase
	("Heather: lunch", []),			# uppercase
]:
	check("keyword form %r" % line, tags_of(line)[0], want)

# ---------- recognition: hashtag form ----------

for line, want in [
	("#heather", ["heather"]),
	("**#heather**", ["heather"]),
	("## topic #heather", ["heather"]),
	("we met #heather today", ["heather"]),
	("#heather #family", ["heather", "family"]),
	# not tags
	("#Heather", []),				# uppercase
	("#123", []),					# numeric
	("&#8212;", []),				# HTML entity
	("word#tag", []),				# no boundary before #
]:
	check("hashtag form %r" % line, tags_of(line)[0], want)

# ---------- tags-only lines carry section scope ----------

for line, want in [
	("#heather", True),
	("#heather #family", True),
	("**#heather**", True),
	("do #heather today", False),
	("heather: lunch", False),
]:
	check("tags-only %r" % line, tags_of(line)[1], want)

# ---------- configurable tag_name_pattern ----------

check("uppercase allowed by pattern", tags_of("#Heather", "[A-Za-z][A-Za-z0-9_-]*")[0], ["heather"])
check("uppercase keyword by pattern", tags_of("Heather: lunch", "[A-Za-z][A-Za-z0-9_-]*")[0], ["heather"])
check("dots allowed by pattern", tags_of("#a.b", "[a-z][a-z0-9._-]*")[0], ["a.b"])
# a pattern with a capture group would shift group(1); it must be rejected, not silently wrong
check("capture group rejected -> default", tags_of("#heather", "([a-z]+)")[0], ["heather"])
check("capture group rejected, uppercase still not a tag", tags_of("#Heather", "([a-z]+)")[0], [])
check("uncompilable pattern -> default", tags_of("#heather", "[a-z")[0], ["heather"])

# ---------- YAML frontmatter ----------

FM = '---\nabout: "a spec for tagging"\ntags: [markdown, tags]\n---\n\n# Title\n\nheather: lunch\n'
lines = FM.split("\n")
check("frontmatter end index", mdnav._frontmatter_end(lines), 4)
check("no frontmatter -> 0", mdnav._frontmatter_end("# Title\nheather: lunch".split("\n")), 0)
check("unterminated --- is a rule, not frontmatter",
	mdnav._frontmatter_end("---\nsome text\nmore".split("\n")), 0)
check("--- not on line 1 -> 0", mdnav._frontmatter_end("# T\n---\nx\n---".split("\n")), 0)
check("... terminator accepted", mdnav._frontmatter_end("---\na: 1\n...\nbody".split("\n")), 3)

# the bug this fixes: `about:` and `tags:` in frontmatter were reported as tags
check("frontmatter about: is a keyword tag when scanned", tags_of('about: "a spec"')[0], ["about"])
check("frontmatter tags: is a keyword tag when scanned", tags_of("tags: [markdown, tags]")[0], ["tags"])
# ...so the body must start after the block
body = [l for i, l in enumerate(lines) if i >= mdnav._frontmatter_end(lines)]
found = sorted({t for l in body for t in tags_of(l)[0]})
check("frontmatter skipped -> only real tags remain", found, ["heather"])

# ---------- label extraction ----------

for line, tag, want in [
	("heather: lunch on Saturday", "heather", "lunch on Saturday"),
	("**heather:** lunch on Saturday", "heather", "lunch on Saturday"),
	("**heather**: lunch on Saturday", "heather", "lunch on Saturday"),
	("  * heather: lunch", "heather", "lunch"),
	("  - issue: bad bearings", "issue", "bad bearings"),
	("  5. heather: lunch", "heather", "lunch"),
	("## person: Heather", "person", "Heather"),
	("we met #heather today", "heather", "we met today"),
	("* #heather alone item", "heather", "alone item"),
	("* item with #heather inline", "heather", "* item with inline"),
	("## title #heather", "heather", "title"),
]:
	check("label %r/%s" % (line, tag), mdnav._tagged_text(line, tag), want)

# ---------- scope resolution ----------

def scope_of(text, line_idx):
	lines, line_start, header_level, _ = mdnav._scan_lines(text)
	_, only = tags_of(lines[line_idx])
	return mdnav._resolve_scope(line_idx, only, header_level, line_start)

doc = "# Title\n\n## Section A\n\nheather: lunch\n\n#family\n"
check("plain tagged line -> line scope", scope_of(doc, 4)[0], "line")
check("tags-only line -> section scope", scope_of(doc, 6)[0], "section")
check("tags-only line anchors to preceding header", scope_of(doc, 6)[1], 2)
check("header line -> section scope, anchored on itself", scope_of("## a: b\n", 0)[:2], ("section", 0))
check("tags-only with no preceding header -> top of doc", scope_of("#family\ntext\n", 0)[1:], (-1, 0))

# ---------- fenced code is ignored ----------

lines, _, _, in_fence = mdnav._scan_lines("#a\n```\n#b\n```\n#c")
# The OPENING ``` reads as outside the fence and the CLOSING one as inside — asymmetric, but
# it never matters: a fence marker line has no tags on it either way.
check("fence flags", in_fence, [False, False, True, True, False])
check("headers inside a fence are not headers", mdnav._scan_lines("# a\n```\n# b\n```")[2], [1, 0, 0, 0])

# ---------- major level (Jump to Header's first panel) ----------

for name, levels, want in [
	("several H1s -> H1", [1, 0, 1, 0], 1),
	("lone H1 title -> H2", [1, 2, 0, 2], 2),
	("lone H1 only -> H1", [1, 0], 1),
	("no headers -> 0", [0, 0], 0),
	("skipped levels: lone H2 then H4s -> H4", [2, 4, 4], 4),
]:
	check("major_level %s" % name, mdnav._major_level(levels), want)


if FAILS:
	for f in FAILS: print("FAIL: " + f)
	print("\n%d failed" % len(FAILS))
	sys.exit(1)
print("all tag checks passed")
