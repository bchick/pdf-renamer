"""Core logic for PDF metadata extraction, API lookups, and renaming."""

import json
import os
import re
import shutil
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import fitz  # pymupdf
import requests

DATA_DIR = Path(__file__).parent / "data"
LOG_FILE = DATA_DIR / "rename_log.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

CROSSREF_API = "https://api.crossref.org"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
OPEN_LIBRARY_API = "https://openlibrary.org"
GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1"
ZOTERO_API = "https://api.zotero.org"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "pdf-renamer/1.0 (https://github.com/pdf-renamer; mailto:pdf-renamer@example.com)"
})

TEMPLATE_PRESETS = {
    "standard": "{author} - {title} ({year})",
    "journal": "{author} - {title} - {journal} ({year})",
    "year_first": "{year} - {author} - {title}",
    "compact": "{author}_{year}_{title}",
}

DOI_PATTERN = re.compile(
    r'(10\.\d{4,9}/[^\s,;"\'\]}>]+)', re.IGNORECASE
)
ISBN_PATTERN = re.compile(
    r'(?:ISBN[-:]?\s*)((?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx])', re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def load_settings():
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {
        "zotero_api_key": "",
        "zotero_library_id": "",
        "zotero_library_type": "user",
        "template": "standard",
        "custom_template": "",
    }


def save_settings(settings):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = load_settings()
    current.update(settings)
    SETTINGS_FILE.write_text(json.dumps(current, indent=2))
    return current


# ---------------------------------------------------------------------------
# Rename log
# ---------------------------------------------------------------------------

def _load_log():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []


def _save_log(entries):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(entries, indent=2))


def log_rename(original, new_path, metadata_source, session_id, metadata=None):
    entries = _load_log()
    entries.append({
        "original_path": str(original),
        "new_path": str(new_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata_source": metadata_source,
        "session_id": session_id,
        "metadata": metadata or {},
        "undone": False,
    })
    _save_log(entries)


def get_history():
    return _load_log()


def undo_single(index):
    entries = _load_log()
    if index < 0 or index >= len(entries):
        return {"error": "Invalid index"}
    entry = entries[index]
    if entry["undone"]:
        return {"error": "Already undone"}
    new_p = Path(entry["new_path"])
    orig_p = Path(entry["original_path"])
    if not new_p.exists():
        return {"error": f"File not found: {new_p}"}
    if orig_p.exists():
        return {"error": f"Original path already occupied: {orig_p}"}
    shutil.move(str(new_p), str(orig_p))
    entries[index]["undone"] = True
    _save_log(entries)
    return {"success": True, "restored": str(orig_p)}


def undo_session(session_id):
    entries = _load_log()
    results = []
    for i, entry in enumerate(entries):
        if entry["session_id"] == session_id and not entry["undone"]:
            r = undo_single(i)
            results.append(r)
            # Reload entries since undo_single modifies the file
            entries = _load_log()
    return results


# ---------------------------------------------------------------------------
# PDF metadata extraction
# ---------------------------------------------------------------------------

def extract_pdf_info(pdf_path):
    """Extract DOI, ISBN, title guess, and raw text from a PDF."""
    result = {
        "doi": None,
        "isbn": None,
        "title_guess": None,
        "text_snippet": "",
        "pdf_metadata": {},
    }

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return result

    # Grab PDF metadata fields
    meta = doc.metadata or {}
    result["pdf_metadata"] = {k: v for k, v in meta.items() if v}

    # Extract text from first 2 pages
    text_parts = []
    for page_num in range(min(2, len(doc))):
        page = doc[page_num]
        text_parts.append(page.get_text())
    full_text = "\n".join(text_parts)
    result["text_snippet"] = full_text[:3000]

    doc.close()

    # --- DOI extraction ---
    # 1. Check metadata fields (subject, keywords, etc.)
    for field in ("subject", "keywords", "doi"):
        val = meta.get(field, "")
        if val:
            m = DOI_PATTERN.search(val)
            if m:
                result["doi"] = _clean_doi(m.group(1))
                break

    # 2. Check embedded text
    if not result["doi"]:
        m = DOI_PATTERN.search(full_text)
        if m:
            result["doi"] = _clean_doi(m.group(1))

    # 3. Check filename
    if not result["doi"]:
        m = DOI_PATTERN.search(os.path.basename(pdf_path))
        if m:
            result["doi"] = _clean_doi(m.group(1))

    # --- ISBN extraction ---
    m = ISBN_PATTERN.search(full_text)
    if m:
        result["isbn"] = re.sub(r'[-\s]', '', m.group(1))

    # --- Title guess from first page ---
    if full_text.strip():
        lines = [l.strip() for l in full_text.split('\n') if l.strip()]
        if lines:
            # Heuristic: title is often the first long-ish line
            for line in lines[:10]:
                if len(line) > 10 and not DOI_PATTERN.search(line) and not line.startswith("http"):
                    result["title_guess"] = line[:200]
                    break

    return result


def _clean_doi(doi):
    """Strip trailing punctuation from a DOI."""
    return doi.rstrip('.,;:"\'>)}]')


# ---------------------------------------------------------------------------
# CrossRef API
# ---------------------------------------------------------------------------

def crossref_lookup_doi(doi):
    """Look up metadata by DOI via CrossRef."""
    try:
        r = SESSION.get(f"{CROSSREF_API}/works/{doi}", timeout=10)
        if r.status_code != 200:
            return None
        data = r.json().get("message", {})
        return _parse_crossref_item(data)
    except Exception:
        return None


def crossref_search_title(title):
    """Free-text search CrossRef for a title."""
    try:
        r = SESSION.get(
            f"{CROSSREF_API}/works",
            params={"query.title": title, "rows": 3},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        items = r.json().get("message", {}).get("items", [])
        if not items:
            return None
        # Return best match
        best = items[0]
        result = _parse_crossref_item(best)
        # Compute a basic confidence score
        result_title = result.get("title", "").lower()
        query_title = title.lower()
        if result_title and query_title:
            # Simple overlap ratio
            words_q = set(query_title.split())
            words_r = set(result_title.split())
            if words_q:
                overlap = len(words_q & words_r) / len(words_q)
                result["confidence"] = round(overlap, 2)
        return result
    except Exception:
        return None


def _parse_crossref_item(item):
    """Parse a CrossRef work item into our metadata format."""
    authors = []
    for a in item.get("author", []):
        family = a.get("family", "")
        given = a.get("given", "")
        if family:
            authors.append(f"{family}, {given}".strip(", "))

    title_list = item.get("title", [])
    title = title_list[0] if title_list else ""

    # Year
    date_parts = item.get("published-print", {}).get("date-parts", [[]])
    if not date_parts or not date_parts[0]:
        date_parts = item.get("published-online", {}).get("date-parts", [[]])
    if not date_parts or not date_parts[0]:
        date_parts = item.get("created", {}).get("date-parts", [[]])
    year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""

    # Journal
    journal_list = item.get("short-container-title", [])
    if not journal_list:
        journal_list = item.get("container-title", [])
    journal = journal_list[0] if journal_list else ""

    publisher = item.get("publisher", "")

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "publisher": publisher,
        "doi": item.get("DOI", ""),
        "source": "crossref",
        "confidence": 1.0,
    }


# ---------------------------------------------------------------------------
# Semantic Scholar API
# ---------------------------------------------------------------------------

def semantic_scholar_search(title):
    """Search Semantic Scholar as a fallback."""
    try:
        r = SESSION.get(
            f"{SEMANTIC_SCHOLAR_API}/paper/search",
            params={"query": title, "limit": 3, "fields": "title,authors,year,venue,externalIds"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        papers = r.json().get("data", [])
        if not papers:
            return None
        paper = papers[0]
        authors = [a.get("name", "") for a in paper.get("authors", [])]

        return {
            "title": paper.get("title", ""),
            "authors": authors,
            "year": str(paper.get("year", "")),
            "journal": paper.get("venue", ""),
            "publisher": "",
            "doi": (paper.get("externalIds") or {}).get("DOI", ""),
            "source": "semantic_scholar",
            "confidence": 0.7,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ISBN lookups (Open Library + Google Books)
# ---------------------------------------------------------------------------

def isbn_lookup(isbn):
    """Look up book metadata by ISBN."""
    result = _open_library_isbn(isbn)
    if result:
        return result
    return _google_books_isbn(isbn)


def _open_library_isbn(isbn):
    try:
        r = SESSION.get(
            f"{OPEN_LIBRARY_API}/api/books",
            params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        key = f"ISBN:{isbn}"
        if key not in data:
            return None
        book = data[key]
        authors = [a.get("name", "") for a in book.get("authors", [])]
        publishers = book.get("publishers", [])
        publisher = publishers[0].get("name", "") if publishers else ""
        return {
            "title": book.get("title", ""),
            "authors": authors,
            "year": book.get("publish_date", "")[-4:] if book.get("publish_date") else "",
            "journal": "",
            "publisher": publisher,
            "doi": "",
            "isbn": isbn,
            "source": "open_library",
            "confidence": 0.9,
        }
    except Exception:
        return None


def _google_books_isbn(isbn):
    try:
        r = SESSION.get(
            f"{GOOGLE_BOOKS_API}/volumes",
            params={"q": f"isbn:{isbn}"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        items = r.json().get("items", [])
        if not items:
            return None
        info = items[0].get("volumeInfo", {})
        return {
            "title": info.get("title", ""),
            "authors": info.get("authors", []),
            "year": info.get("publishedDate", "")[:4],
            "journal": "",
            "publisher": info.get("publisher", ""),
            "doi": "",
            "isbn": isbn,
            "source": "google_books",
            "confidence": 0.85,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Zotero integration
# ---------------------------------------------------------------------------

def zotero_search(title, settings=None):
    """Search Zotero library for a title match."""
    s = settings or load_settings()
    api_key = s.get("zotero_api_key", "")
    lib_id = s.get("zotero_library_id", "")
    lib_type = s.get("zotero_library_type", "user")
    if not api_key or not lib_id:
        return None

    try:
        r = SESSION.get(
            f"{ZOTERO_API}/{lib_type}s/{lib_id}/items",
            params={"q": title, "limit": 3, "format": "json"},
            headers={"Zotero-API-Key": api_key},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        items = r.json()
        if not items:
            return None
        data = items[0].get("data", {})
        creators = data.get("creators", [])
        authors = []
        for c in creators:
            name = c.get("lastName", "")
            if c.get("firstName"):
                name = f"{name}, {c['firstName']}"
            if name:
                authors.append(name)
        return {
            "title": data.get("title", ""),
            "authors": authors,
            "year": data.get("date", "")[:4],
            "journal": data.get("publicationTitle", "") or data.get("journalAbbreviation", ""),
            "publisher": data.get("publisher", ""),
            "doi": data.get("DOI", ""),
            "source": "zotero",
            "confidence": 0.95,
            "zotero_key": items[0].get("key", ""),
        }
    except Exception:
        return None


def zotero_update_attachment(item_key, new_filename, settings=None):
    """Update the linked file path for a Zotero item's attachment."""
    s = settings or load_settings()
    api_key = s.get("zotero_api_key", "")
    lib_id = s.get("zotero_library_id", "")
    lib_type = s.get("zotero_library_type", "user")
    if not api_key or not lib_id:
        return False

    try:
        # Get children (attachments) of the item
        r = SESSION.get(
            f"{ZOTERO_API}/{lib_type}s/{lib_id}/items/{item_key}/children",
            headers={"Zotero-API-Key": api_key},
            timeout=10,
        )
        if r.status_code != 200:
            return False
        children = r.json()
        for child in children:
            data = child.get("data", {})
            if data.get("itemType") == "attachment" and data.get("contentType") == "application/pdf":
                version = child.get("version", 0)
                patch = {"title": new_filename, "filename": new_filename}
                rp = SESSION.patch(
                    f"{ZOTERO_API}/{lib_type}s/{lib_id}/items/{child['key']}",
                    json=patch,
                    headers={
                        "Zotero-API-Key": api_key,
                        "If-Unmodified-Since-Version": str(version),
                    },
                    timeout=10,
                )
                return rp.status_code in (200, 204)
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Metadata resolution pipeline
# ---------------------------------------------------------------------------

def resolve_metadata(pdf_path):
    """Full pipeline: extract info from PDF, then resolve via APIs."""
    info = extract_pdf_info(pdf_path)
    metadata = None

    # 1. DOI lookup via CrossRef
    if info["doi"]:
        metadata = crossref_lookup_doi(info["doi"])
        if metadata:
            metadata["confidence"] = 1.0
            return metadata

    # 2. ISBN lookup for books
    if info["isbn"]:
        metadata = isbn_lookup(info["isbn"])
        if metadata:
            return metadata

    title = info.get("title_guess", "")

    # 3. CrossRef free-text search
    if title:
        metadata = crossref_search_title(title)
        if metadata and metadata.get("confidence", 0) >= 0.5:
            return metadata

    # 4. Semantic Scholar search
    if title:
        metadata = semantic_scholar_search(title)
        if metadata:
            return metadata

    # 5. Zotero fallback
    if title:
        metadata = zotero_search(title)
        if metadata:
            return metadata

    # 6. Manual review needed
    return {
        "title": title or os.path.splitext(os.path.basename(pdf_path))[0],
        "authors": [],
        "year": "",
        "journal": "",
        "publisher": "",
        "doi": info.get("doi", ""),
        "source": "manual_review",
        "confidence": 0.0,
    }


# ---------------------------------------------------------------------------
# Filename generation
# ---------------------------------------------------------------------------

def _sanitize_filename(name):
    """Remove or replace characters that are invalid in filenames."""
    # Normalize unicode
    name = unicodedata.normalize("NFKD", name)
    # Replace path separators and other problematic chars
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    # Truncate to reasonable length
    if len(name) > 200:
        name = name[:200].rsplit(' ', 1)[0]
    return name


def _format_author(authors):
    """Format author list for filename: 'LastName' or 'Last1, Last2' or 'Last1 et al.'"""
    if not authors:
        return "Unknown"
    # Extract last names
    last_names = []
    for a in authors:
        parts = a.split(",")
        last_names.append(parts[0].strip())
    if len(last_names) == 1:
        return last_names[0]
    if len(last_names) == 2:
        return f"{last_names[0]} & {last_names[1]}"
    return f"{last_names[0]} et al."


def generate_filename(metadata, template=None):
    """Generate a filename from metadata using a template."""
    settings = load_settings()
    if template is None:
        tpl_key = settings.get("template", "standard")
        if tpl_key == "custom":
            template = settings.get("custom_template", TEMPLATE_PRESETS["standard"])
        else:
            template = TEMPLATE_PRESETS.get(tpl_key, TEMPLATE_PRESETS["standard"])

    author_str = _format_author(metadata.get("authors", []))
    title = metadata.get("title", "Untitled")
    year = metadata.get("year", "")
    journal = metadata.get("journal", "")
    publisher = metadata.get("publisher", "")

    name = template.format(
        author=author_str,
        title=title,
        year=year,
        journal=journal,
        publisher=publisher,
    )
    name = _sanitize_filename(name)
    return name + ".pdf"


# ---------------------------------------------------------------------------
# Scan & Execute
# ---------------------------------------------------------------------------

def scan_directory(directory, template=None):
    """Scan a directory for PDFs and propose new names."""
    directory = Path(directory)
    if not directory.is_dir():
        return {"error": f"Not a directory: {directory}"}

    # Resolve template: preset key or custom string
    tpl = None
    if template:
        tpl = TEMPLATE_PRESETS.get(template, template)

    results = []
    pdf_files = sorted(directory.glob("*.pdf"))

    for pdf_path in pdf_files:
        metadata = resolve_metadata(str(pdf_path))
        proposed = generate_filename(metadata, template=tpl)

        results.append({
            "original_path": str(pdf_path),
            "original_name": pdf_path.name,
            "proposed_name": proposed,
            "metadata": metadata,
            "source": metadata.get("source", "unknown"),
            "confidence": metadata.get("confidence", 0),
        })

    return {"files": results, "count": len(results), "directory": str(directory)}


def execute_renames(files, session_id=None):
    """Execute rename operations for a list of files.

    Args:
        files: list of dicts with 'original_path' and 'new_name' keys.
        session_id: optional session identifier for undo grouping.
    """
    if session_id is None:
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    results = []
    settings = load_settings()

    for f in files:
        original = Path(f["original_path"])
        new_name = f.get("new_name", f.get("proposed_name", original.name))
        new_path = original.parent / new_name

        if not original.exists():
            results.append({"original": str(original), "error": "File not found"})
            continue

        if new_path.exists() and new_path != original:
            # Add a numeric suffix to avoid collisions
            stem = new_path.stem
            suffix = new_path.suffix
            counter = 1
            while new_path.exists():
                new_path = original.parent / f"{stem} ({counter}){suffix}"
                counter += 1

        try:
            shutil.move(str(original), str(new_path))
            metadata_source = f.get("source", "unknown")
            log_rename(original, new_path, metadata_source, session_id, f.get("metadata"))
            result = {"original": str(original), "new_path": str(new_path), "success": True}

            # Zotero update if configured
            zotero_key = (f.get("metadata") or {}).get("zotero_key")
            if zotero_key and settings.get("zotero_api_key"):
                zotero_ok = zotero_update_attachment(zotero_key, new_name, settings)
                result["zotero_updated"] = zotero_ok

            results.append(result)
        except Exception as e:
            results.append({"original": str(original), "error": str(e)})

    return {"results": results, "session_id": session_id}
