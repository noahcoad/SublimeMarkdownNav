# Markdown Nav — navigate a markdown document by its headers and its tags.
#
# Commands:
#   mdnav_jump_to_header — drill down the header tree one level at a time, then jump
#   mdnav_find_tag       — two-step picker: tag -> match, then jump
#
# Command names keep the historical `mdnav_` prefix so existing key bindings survive the
# package's rename from "mdnav" to "Markdown Nav" (2026-09-09).
#
# How a tag is recognized is specified in full in readme.md ("How tags are defined").
# Two settings tune it; everything else about tag handling is structural and lives in code:
#   tag_name_pattern — the character pattern for a tag NAME, spliced into both forms
#   skip_frontmatter — ignore a leading YAML `---` block, so its `tags:` key isn't a tag

import re

import sublime
import sublime_plugin

SETTINGS = "Markdown Nav.sublime-settings"

# Lowercase-only by default: `Heather:`/`M:`/`#Heather` are NOT tags; `heather:`/`#heather` are.
# Keeps tag identity unambiguous and avoids false positives on capitalized prose words.
DEFAULT_TAG_NAME = r"[a-z][a-z0-9_-]*"


# ---------- shared parsing helpers ----------

_FENCE_RE = re.compile(r"^\s*```")
_HEADER_RE = re.compile(r"^(#{1,6})\s+\S")
_HEADER_TEXT_RE = re.compile(r"^#{1,6} +(.+?)\s*#*\s*$")
_LEAD_RE = re.compile(r"^(\s*(?:[*+\-]\s+|\d+[.)]\s+)?)(#{1,6}\s+)?")

_res_cache = {}


def _tag_res(name_pat):
	"""Compile the three structural tag patterns around `name_pat`. Cached per pattern.

	Falls back to DEFAULT_TAG_NAME on a pattern that won't compile, or one that adds a capture
	group — group(1) has to be the tag name, so a user group would silently shift it and break
	scope and label extraction rather than raising anywhere visible.
	"""
	hit = _res_cache.get(name_pat)
	if hit: return hit
	problem = None
	try:
		if re.compile(name_pat).groups:
			problem = "it adds a capture group — use (?:...) instead"
	except re.error as e:
		problem = str(e)
	if problem:
		sublime.status_message("Markdown Nav: ignoring tag_name_pattern (%s)" % problem)
		return _tag_res(DEFAULT_TAG_NAME)
	hit = (
		re.compile(r"^(?:#{1,6}\s+)?(" + name_pat + r"): +\S"),		# keyword form
		re.compile(r"(?:^|[^\w&])#(" + name_pat + r")"),				# hashtag form
		re.compile(r"^(?:#" + name_pat + r"\s*)+$"),					# tags-only line
	)
	_res_cache[name_pat] = hit
	return hit


def _config():
	"""(keyword_re, hashtag_re, tags_only_re, skip_frontmatter) from the settings file."""
	s = sublime.load_settings(SETTINGS)
	pat = s.get("tag_name_pattern") or DEFAULT_TAG_NAME
	skip = s.get("skip_frontmatter")
	return _tag_res(pat) + (True if skip is None else bool(skip),)


def _scan_lines(text):
	"""Return (lines, line_start, header_level, in_code_fence) — single fence-aware pass."""
	lines = text.split("\n")
	n = len(lines)
	line_start = [0] * (n + 1)
	header_level = [0] * n
	in_fence = [False] * n
	pos = 0
	fence = False
	for i, line in enumerate(lines):
		line_start[i] = pos
		pos += len(line) + 1
		if _FENCE_RE.match(line):
			in_fence[i] = fence  # fence marker line itself counts as outside
			fence = not fence
			continue
		in_fence[i] = fence
		if not fence:
			m = _HEADER_RE.match(line)
			if m: header_level[i] = len(m.group(1))
	line_start[n] = pos
	return lines, line_start, header_level, in_fence


def _frontmatter_end(lines):
	"""Index one past a leading YAML `---` block, else 0.

	A file-level `tags:` key in frontmatter is metadata about the whole file, not an in-document
	tag, so those lines are skipped. An unterminated `---` returns 0 rather than swallowing the
	rest of the file — a lone `---` at the top is a horizontal rule, not frontmatter.
	"""
	if not lines or lines[0].strip() != "---": return 0
	for i in range(1, len(lines)):
		if lines[i].strip() in ("---", "..."): return i + 1
	return 0


def _extract_tags(line, keyword_re, hashtag_re, tags_only_re):
	"""Return (tags_lc, is_tags_only_line)."""
	out = []
	seen = set()
	def add(t):
		lc = t.lower()
		if lc not in seen:
			seen.add(lc)
			out.append(lc)
	unbold = line.replace("**", "")
	trimmed = unbold.strip()
	kw = keyword_re.match(trimmed)
	if kw: add(kw.group(1))
	for m in hashtag_re.finditer(unbold): add(m.group(1))
	is_tags_only = bool(tags_only_re.match(trimmed))
	return out, is_tags_only


def _tagged_text(line, tag):
	"""Strip the tag and any leading marker, so the label reads as what the line says."""
	s = line.replace("**", "")
	lead = _LEAD_RE.match(s)
	after = s[lead.end():]
	header_prefix = lead.group(2) or ""

	# Match the tag literally, so a case-variant lookalike (not a tag) survives untouched.
	kw = re.match(r"^" + re.escape(tag) + r":\s+(\S.*)$", after)
	if kw: return kw.group(1).strip()

	hs = re.match(r"^#" + re.escape(tag) + r"(?:\s+(.*))?$", after)
	if hs: return (hs.group(1) or "").strip()

	if header_prefix:
		stripped = re.sub(r"(?:^|[^\w&])#" + re.escape(tag) + r"\b", " ", after)
		return re.sub(r"\s+", " ", stripped).strip()

	stripped = re.sub(r"(^|[^\w&])#" + re.escape(tag) + r"\b", r"\1", s)
	return re.sub(r"\s+", " ", stripped).strip()


def _resolve_scope(i, is_tags_only, header_level, line_start):
	"""Return ('section'|'line', anchor_line, jump_pos)."""
	is_header = header_level[i] > 0
	sectional = is_header or is_tags_only
	if not sectional:
		return "line", i, line_start[i]
	anchor = i if is_header else -1
	if anchor == -1:
		for k in range(i - 1, -1, -1):
			if header_level[k] > 0:
				anchor = k
				break
	jump_pos = 0 if anchor == -1 else line_start[anchor]
	return "section", anchor, jump_pos


def _major_level(header_level):
	"""The outline's 'major' header level: the shallowest one that repeats.

	A lone `# H1` is a document title, not a divider — in that case the level below it
	(usually H2) is major, so Jump to Header's first panel isn't a list of one.
	"""
	levels = sorted(set(l for l in header_level if l))
	if not levels: return 0
	if sum(1 for l in header_level if l == levels[0]) > 1: return levels[0]
	return levels[1] if len(levels) > 1 else levels[0]


# view id -> (level, caption) of the header last jumped to, so reopening the panel
# lands on it. Keyed on text, not position, so edits above it don't break the match.
_last_header = {}


def _jump(view, point):
	"""Move caret to `point` and scroll so it lands near the top of the viewport."""
	view.sel().clear()
	view.sel().add(sublime.Region(point))
	view.show_at_center(point)


# ---------- commands ----------

class MdnavJumpToHeaderCommand(sublime_plugin.TextCommand):
	"""Drill down the header tree one level at a time, then jump to a section.

	The first panel lists the top level of the outline: H1s when the file has more
	than one, otherwise the level below the lone H1 (usually its H2s). Picking a
	header that has sub-headers opens the next level with a "jump here" option on
	top; picking a leaf header jumps straight to it.
	"""

	def run(self, edit):
		view = self.view
		text = view.substr(sublime.Region(0, view.size()))
		lines, line_start, header_level, in_fence = _scan_lines(text)

		# Flat outline in document order: (level, caption, line_num_1based, jump_pos).
		self.headers = []
		for i, line in enumerate(lines):
			if not header_level[i]: continue  # _scan_lines already ignores fenced lines
			m = _HEADER_TEXT_RE.match(line)
			if m: self.headers.append((header_level[i], m.group(1), i + 1, line_start[i]))

		if not self.headers:
			sublime.status_message("Markdown Nav: no headers found")
			return

		# Top panel = the major level: H1s when the file has several, else a level in.
		major = _major_level(header_level)
		roots = [k for k, h in enumerate(self.headers) if h[0] == major]
		self._show(roots, len(self.headers), None)

	# ---------- tree helpers (indexes into self.headers) ----------

	def _children(self, lo, hi):
		"""Indexes in [lo, hi) at the shallowest level present — one outline level."""
		if lo >= hi: return []
		top = min(self.headers[k][0] for k in range(lo, hi))
		return [k for k in range(lo, hi) if self.headers[k][0] == top]

	def _span(self, k, hi):
		"""Body range of header k: everything after it until a header at its level or above."""
		lvl = self.headers[k][0]
		for j in range(k + 1, hi):
			if self.headers[j][0] <= lvl: return k + 1, j
		return k + 1, hi

	# ---------- panels ----------

	def _show(self, idxs, hi, parent):
		"""Panel of `idxs`; `hi` bounds their subtrees, `parent` is the header index above (or None)."""
		items = []
		if parent is not None:
			_, caption, ln, _pos = self.headers[parent]
			# Parens + no `#` marker so it reads as an action, not one of the headers.
			items.append(["(jump here)", "{} — line {}".format(caption, ln)])
		for k in idxs:
			lvl, caption, ln, _pos = self.headers[k]
			lo, sub_hi = self._span(k, hi)
			kids = len(self._children(lo, sub_hi))
			detail = "line {}".format(ln)
			if kids: detail += " — {} sub-header{}".format(kids, "" if kids == 1 else "s")
			items.append(["{} {}".format("#" * lvl, caption), detail])

		def on_select(sel):
			if sel < 0: return
			if parent is not None:
				if sel == 0:
					self._go(parent)
					return
				sel -= 1
			k = idxs[sel]
			lo, sub_hi = self._span(k, hi)
			kids = self._children(lo, sub_hi)
			if not kids:
				self._go(k)
				return
			# Re-entrant show_quick_panel needs a tick to let the current panel close.
			sublime.set_timeout(lambda: self._show(kids, sub_hi, k), 10)

		self.view.window().show_quick_panel(items, on_select,
			selected_index=self._preselect(idxs, hi, parent))

	def _go(self, k):
		"""Jump to header k and remember it as this view's last pick."""
		lvl, caption, _ln, pos = self.headers[k]
		_last_header[self.view.id()] = (lvl, caption)
		_jump(self.view, pos)

	def _preselect(self, idxs, hi, parent):
		"""Row to highlight: the one on the path to this view's last pick, else the first."""
		last = _last_header.get(self.view.id())
		if last is None: return -1
		key = lambda k: (self.headers[k][0], self.headers[k][1])
		if parent is not None and key(parent) == last: return 0
		base = 1 if parent is not None else 0
		for n, k in enumerate(idxs):
			lo, sub_hi = self._span(k, hi)
			if key(k) == last or any(key(j) == last for j in range(lo, sub_hi)):
				return base + n
		return -1


class MdnavFindTagCommand(sublime_plugin.TextCommand):
	"""Two-step picker: pick a tag, then pick a match. Jump to the match.

	Tag recognition is specified in readme.md ("How tags are defined").
	"""

	def run(self, edit):
		view = self.view
		keyword_re, hashtag_re, tags_only_re, skip_fm = _config()
		text = view.substr(sublime.Region(0, view.size()))
		lines, line_start, header_level, in_fence = _scan_lines(text)
		body_starts = _frontmatter_end(lines) if skip_fm else 0

		matches = []  # {tag, jump_pos, label, line_num}
		tag_to_idxs = {}

		for i, line in enumerate(lines):
			if i < body_starts: continue
			if in_fence[i]: continue
			tags, is_tags_only = _extract_tags(line, keyword_re, hashtag_re, tags_only_re)
			if not tags: continue
			scope, anchor, jump_pos = _resolve_scope(i, is_tags_only, header_level, line_start)
			for tag in tags:
				if scope == "section":
					if anchor == -1:
						label = "(top of doc)"
					else:
						label = (_tagged_text(lines[anchor], tag)
							or _tagged_text(line, tag)
							or "(top of doc)")
				else:
					label = _tagged_text(line, tag) or "(empty line)"
				idx = len(matches)
				matches.append({"tag": tag, "jump_pos": jump_pos, "label": label, "line_num": i + 1})
				tag_to_idxs.setdefault(tag, []).append(idx)

		if not matches:
			sublime.status_message("Markdown Nav: no tags found")
			return

		# Tag picker — sort by most-recent match position, latest first.
		tags = sorted(tag_to_idxs.keys(),
			key=lambda t: matches[tag_to_idxs[t][-1]]["jump_pos"], reverse=True)

		tag_items = []
		for t in tags:
			n = len(tag_to_idxs[t])
			tag_items.append(["#" + t, "{} match{}".format(n, "" if n == 1 else "es")])

		def on_tag(tidx):
			if tidx < 0: return
			tag = tags[tidx]
			idxs = sorted(tag_to_idxs[tag], key=lambda i: matches[i]["jump_pos"], reverse=True)
			hit_items = [[matches[i]["label"], "line {}".format(matches[i]["line_num"])] for i in idxs]

			def on_hit(hidx):
				if hidx < 0: return
				_jump(view, matches[idxs[hidx]]["jump_pos"])

			view.window().show_quick_panel(hit_items, on_hit)

		view.window().show_quick_panel(tag_items, on_tag)
