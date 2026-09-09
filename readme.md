# Markdown Nav

Navigate a long markdown document by its **headers** and its **tags**, from the Command Palette.

Built for big notes files — the kind that accumulate for years and get too long to scroll. Two
commands:

| Command Palette | What it does |
|---|---|
| `Markdown Nav: Jump to Header` | Walk the header tree one level at a time to the section you want |
| `Markdown Nav: Find Tag` | Pick a tag, then pick one of its matches, then jump there |

No key bindings are set by default. Copy what you want out of `Example.sublime-keymap`, via
**Preferences → Package Settings → Markdown Nav → Key Bindings**.

## Jump to Header

Rather than one flat list of every header in the file, this descends the outline a level at a time:

- **The first panel** shows the top level of the document. If the file has more than one `# H1`,
  that's the H1s. If it has a single `# H1` (the usual document title), it starts a level in, at
  that H1's own sub-headers — so you don't click through a list of one.
- **Picking a header that has sub-headers** opens the next level down, with `(jump here)` as the
  first entry (which jumps to the header you just picked), followed by its children.
- **Picking a leaf header** — one with nothing nested under it — jumps immediately, no extra panel.

Each row shows the header's depth (`##`), its text, its line number, and how many sub-headers it
has. Levels may be skipped: an `## H2` whose children are `#### H4`s works fine — each panel shows
the shallowest level actually present in that section. Headers inside fenced code blocks are
ignored. `esc` at any level cancels without moving the caret.

**The panel reopens on your last pick.** The top panel highlights the section containing it, and
each level down highlights the next step along that path, so re-running the command puts you right
back where you were. Sublime's quick panel can't be pre-filled with filter text, so this is done
with a pre-highlighted row — type to filter as usual, or press `enter` immediately to re-jump. The
memory is per view and keyed on header *text* (so edits above a header don't lose it), and lasts
only for the session.

### The major header level

The first panel keys off the **major** level: the shallowest header level that appears **more than
once**. A file with several `# H1`s has H1 as its major level; a file with a single `# H1` document
title falls through to its `## H2`s, since a lone title isn't a section divider.

## Find Tag

Two panels: **pick a tag** (listed most-recently-used first, with a match count), then **pick a
match** (with its line number), then jump. Both are fuzzy-filterable like any Sublime quick panel.

Match labels are the *tagged text* — what the line says with the tag itself stripped out — so the
list reads as content rather than as a column of repeated tag names.

## How tags are defined

A tag has two orthogonal aspects: the **form** it's written in, and the **scope** it refers to. A
tag's identity is its lowercased name.

### Forms

**Keyword-prefix form — `heather: …`**

A line whose first text content (optionally after a markdown header prefix `#{1,6} `) is
`<name>:` followed by **at least one space** and then non-whitespace. The keyword is the tag.

The required space after the colon is what disqualifies URLs and similar:

| Matches | Does not match | Why not |
|---|---|---|
| `heather: lunch on Saturday` | `mobilenotes://abc123` | no space after `:` |
| `**heather:** lunch` | `http://example.com` | no space after `:` |
| `**heather**: lunch` | `mailto:foo@bar.com` | no space after `:` |
| `  issue: bad bearings` | `key:value` | no space after `:` |
| `## person: Heather` | `Heather: lunch` | uppercase — see below |

**Hashtag form — `#heather`**

A `#name` token anywhere on the line. It must be at the start of the line or preceded by a
non-word, non-`&` character, so `word#tag` and the HTML entity `&#8212;` don't match.

| Matches | Does not match | Why not |
|---|---|---|
| `#heather` | `#Heather` | uppercase — see below |
| `**#heather**` | `#123` | numeric |
| `## topic #heather` | `&#8212;` | HTML entity |
| `we met #heather today` | `word#tag` | no boundary before `#` |

**Case.** Tags are lowercase by default, in both forms. This is deliberate: it keeps tag identity
unambiguous and stops every capitalized word before a colon (`Note: …`, `TODO: …`) and every
sentence starting with a capital from becoming a tag. Change it with `tag_name_pattern` below if
you'd rather have uppercase count.

**Bold.** Tags in either form may be wrapped in `**…**`; the markers are stripped before the tag is
identified, and they don't affect scope.

### Scopes

A tag's scope is **section** if either the line is a markdown header, or the line consists only of
hashtag tokens. Otherwise it's **single-line**.

- **Single-line scope** — the match is that one line. Jumps to the start of the line.
- **Section scope** — the match is the enclosing section, anchored at the tag's own line if it's a
  header, otherwise at the nearest preceding header at any level, otherwise the top of the
  document. Jumps to the start of the anchor line.

| Example line | Form | Header? | Tags-only? | Scope |
|---|---|---|---|---|
| `heather: lunch on Saturday` | keyword | no | no | single-line |
| `## heather: lunch` | keyword | yes | — | section |
| `do #heather today` | hashtag | no | no | single-line |
| `#heather` | hashtag | no | yes | section |
| `#heather #family` | hashtag ×2 | no | yes | section |
| `## title #heather` | hashtag | yes | — | section |

### Ignored

- Anything inside a fenced code block (` ``` `).
- Numeric-only `#1`, `#123`, and HTML entities `&#nnn;`.
- Mid-token `word#tag`.
- A leading YAML `---` frontmatter block. Its `tags:` key is metadata about the whole file, not an
  in-document tag, so it isn't reported as a tag named `tags`. Turn this off with
  `skip_frontmatter`. An unterminated `---` is treated as a horizontal rule, not frontmatter.

### Match text

The label shown for a match is the line with the tag stripped out:

| Raw line | Tag | Label |
|---|---|---|
| `heather: lunch on Saturday` | heather | `lunch on Saturday` |
| `**heather:** lunch on Saturday` | heather | `lunch on Saturday` |
| `  * heather: lunch` | heather | `lunch` |
| `  5. heather: lunch` | heather | `lunch` |
| `## person: Heather` | person | `Heather` |
| `we met #heather today` | heather | `we met today` |
| `* #heather alone item` | heather | `alone item` |
| `* item with #heather inline` | heather | `* item with inline` |
| `## title #heather` | heather | `title` |

The rules: strip the tag and its bold markers; if the tag was at the start of the line, strip the
leading whitespace, bullet marker (`*`, `-`, `+`, `N.`, `N)`) and header marker too; if the line is
a header, strip the header marker regardless of where the tag was; if the tag was mid-line, remove
only the tag and keep the surrounding text as context; then collapse and trim whitespace.

When stripping leaves nothing, the line was tag-only — which means section scope — so the label
comes from the section anchor instead, or `(top of doc)` if there's no preceding header.

## Settings

**Preferences → Package Settings → Markdown Nav → Settings**, or
`Preferences: Markdown Nav Settings` in the Command Palette.

```json
{
	"tag_name_pattern": "[a-z][a-z0-9_-]*",
	"skip_frontmatter": true
}
```

**`tag_name_pattern`** — the character pattern for a tag *name*, spliced into both forms. To also
accept uppercase, use `"[A-Za-z][A-Za-z0-9_-]*"`. To allow dots, `"[a-z][a-z0-9._-]*"`. It must not
contain a capture group — use `(?:…)` if you need grouping — because the tag name has to stay as
group 1 for scope and label extraction to work. A pattern that won't compile, or that adds a group,
is ignored with a note in the status bar and the default is used instead.

**`skip_frontmatter`** — whether to skip a leading YAML `---` block when scanning for tags.

Everything else about tag handling is structural rather than a preference, and lives in code: which
of the two forms a line uses, whether the scope is a line or a section, where a section's anchor is,
and how a label is stripped. Those are interdependent — the patterns carry a contract that group 1
is the tag name — so exposing them as raw regex settings would let a bad override break scope and
labels silently instead of failing loudly. `tag_name_pattern` is the one part that varies
independently of the rest.

## Requirements

Sublime Text 4, build 4107 or newer (it runs in the Python 3.8 plugin host).

## Layout

```
mdnav.py                       # both commands and the parsing helpers
Markdown Nav.sublime-settings  # tag_name_pattern, skip_frontmatter
Default.sublime-commands       # Command Palette entries
Main.sublime-menu              # Preferences -> Package Settings -> Markdown Nav
Example.sublime-keymap         # suggested bindings; Sublime never loads this file
tests/test_tags.py             # standalone, stubs `sublime`, no ST needed
```

Command names are `mdnav_jump_to_header` and `mdnav_find_tag` — the `mdnav_` prefix predates the
rename from "mdnav" to "Markdown Nav" and is kept so existing key bindings keep working.

## Tests

```bash
py tests/test_tags.py
```

## License

MIT — see `LICENSE`.
