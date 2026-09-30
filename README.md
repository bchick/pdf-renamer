# PDF Renamer

**Stop wasting time renaming papers by hand.** Point this tool at a folder of PDFs and it automatically identifies each paper's title, authors, year, and journal — then renames everything in seconds with clean, consistent filenames.

## Why use this?

- **It just works** — drop in a directory path, click Scan, done.
- **Smart metadata lookup** — pulls from CrossRef, Semantic Scholar, Open Library, and Google Books. DOI and ISBN are extracted straight from the PDF text.
- **You stay in control** — review every proposed name before committing. Edit any you want to tweak.
- **Undo anything** — made a mistake? Revert individual files or entire sessions.
- **Zotero integration** — optionally sync renamed filenames back to your Zotero library.
- **Confidence scores** — see at a glance how reliable each metadata match is.
- **Flexible naming** — four built-in templates or define your own with `{author}`, `{title}`, `{year}`, `{journal}`, `{publisher}`.

## Install

The easiest way is with [pipx](https://pipx.pypa.io/), which installs the `pdf-renamer` command in its own isolated environment:

```bash
pipx install git+https://github.com/bchick/pdf-renamer.git
```

(Plain `pip install git+https://github.com/bchick/pdf-renamer.git` works too.)

## Quick Start

```bash
# Preview proposed names without changing anything
pdf-renamer ~/Papers --dry-run

# Review the proposals and confirm
pdf-renamer ~/Papers
```

Prefer a point-and-click interface? Run `pdf-renamer --web` and your browser opens the web UI.

## CLI Usage

```bash
# Scan a directory and interactively approve renames
pdf-renamer /path/to/pdfs

# Auto-approve all renames without prompting
pdf-renamer /path/to/pdfs --yes

# Preview proposed renames without changing anything
pdf-renamer /path/to/pdfs --dry-run

# Use a specific naming template
pdf-renamer /path/to/pdfs --template journal

# View rename history
pdf-renamer --history

# Undo all renames from a session
pdf-renamer --undo 20250301_143022

# Launch the web UI (opens your browser)
pdf-renamer --web
pdf-renamer --web --port 8080 --no-browser
```

Run `pdf-renamer --help` for all options.

## How it works (Web UI)

1. Enter a directory path and click **Scan**.
2. The tool extracts DOIs/ISBNs from each PDF, queries academic APIs, and proposes clean filenames.
3. Review the table — edit any names you'd like to adjust.
4. Check the files you want and click **Rename Selected**.
5. Use the **History** tab to view past renames or undo them.

## Naming Templates

| Preset | Example Output |
|---|---|
| Standard | `Author - Title (Year).pdf` |
| Journal | `Author - Title - Nature (Year).pdf` |
| Year First | `Year - Author - Title.pdf` |
| Compact | `Author_Year_Title.pdf` |

Or define a custom template using any combination of `{author}`, `{title}`, `{year}`, `{journal}`, `{publisher}`.

## Zotero Integration (optional)

1. Open **Settings** in the web UI.
2. Enter your [Zotero API key](https://www.zotero.org/settings/keys) and library ID.
3. When a PDF matches a Zotero entry, the attachment filename is updated automatically after renaming.

## Configuration

Settings (`settings.json`) and rename history (`rename_log.json`) are stored in a per-user data directory:

| OS | Location |
|---|---|
| Linux | `~/.local/share/pdf-renamer/` (or `$XDG_DATA_HOME/pdf-renamer/`) |
| macOS | `~/Library/Application Support/pdf-renamer/` |
| Windows | `%APPDATA%\pdf-renamer\` |

`pdf-renamer --help` prints the exact path. Set `PDF_RENAMER_DATA_DIR` to use a different location. If you run from a git checkout that already has a `data/` folder from an older version, that folder keeps being used so your history is preserved. See `data/settings.example.json` for the settings format.

You can also configure the web server via environment variables:

| Variable | Default | Description |
|---|---|---|
| `FLASK_DEBUG` | `0` | Set to `1` to enable debug mode |
| `FLASK_HOST` | `127.0.0.1` | Bind address |
| `FLASK_PORT` | `5000` | Port number |

## Development

```bash
git clone https://github.com/bchick/pdf-renamer.git && cd pdf-renamer
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pdf-renamer --help
```

`python renamer.py ...` and `python app.py` still work from a checkout.

## Project Structure

```
pdf-renamer/
  pyproject.toml        Packaging and the `pdf-renamer` command
  pdf_renamer/
    renamer.py          Core logic (PDF extraction, API lookups, renaming) and CLI
    app.py              Flask web server and API routes
    templates/index.html  Single-page web UI
    static/             Styles and frontend logic
  renamer.py, app.py    Shims for running from a checkout
  data/settings.example.json   Settings template
```

## Requirements

- Python 3.10+
- No API keys needed for basic use (CrossRef, Semantic Scholar, Open Library, and Google Books are free)
- Zotero API key only required if you want Zotero sync

## License

MIT
