# PDF Renamer

**Stop wasting time renaming papers by hand.** Point this tool at a folder of PDFs and it automatically identifies each paper's title, authors, year, and journal — then renames everything in seconds with clean, consistent filenames.

Built for researchers who accumulate hundreds of `10.1016_j.cell.2024.01.pdf` files and just want them to say `Smith - Cortical Dynamics in Mice (2024).pdf`.

## Why use this?

- **It just works** — drop in a directory path, click Scan, done.
- **Smart metadata lookup** — pulls from CrossRef, Semantic Scholar, Open Library, and Google Books. DOI and ISBN are extracted straight from the PDF text.
- **You stay in control** — review every proposed name before committing. Edit any you want to tweak.
- **Undo anything** — made a mistake? Revert individual files or entire sessions.
- **Zotero integration** — optionally sync renamed filenames back to your Zotero library.
- **Confidence scores** — see at a glance how reliable each metadata match is.
- **Flexible naming** — four built-in templates or define your own with `{author}`, `{title}`, `{year}`, `{journal}`, `{publisher}`.

## Quick Start

```bash
git clone <repo-url> && cd pdf-renamer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 and start renaming.

## How it works

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

Settings are stored locally in `data/settings.json` (auto-created on first save, git-ignored). See `data/settings.example.json` for the format.

You can also configure the Flask server via environment variables:

| Variable | Default | Description |
|---|---|---|
| `FLASK_DEBUG` | `0` | Set to `1` to enable debug mode |
| `FLASK_HOST` | `127.0.0.1` | Bind address |
| `FLASK_PORT` | `5000` | Port number |

## Project Structure

```
pdf-renamer/
  app.py              Flask web server and API routes
  renamer.py          Core logic: PDF extraction, API lookups, renaming
  requirements.txt    Python dependencies
  templates/
    index.html        Single-page web UI
  static/
    style.css         Styles
    app.js            Frontend logic
  data/
    settings.example.json   Settings template
    settings.json           Your settings (auto-created, git-ignored)
    rename_log.json         Rename history (auto-created, git-ignored)
```

## Requirements

- Python 3.10+
- No API keys needed for basic use (CrossRef, Semantic Scholar, Open Library, and Google Books are free)
- Zotero API key only required if you want Zotero sync

## License

MIT
