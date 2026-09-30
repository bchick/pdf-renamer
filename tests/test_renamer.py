"""Offline tests for pdf_renamer. Network calls are stubbed out."""

import json

import pymupdf
import pytest

from pdf_renamer import renamer


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Keep settings and history out of the user's real data dir."""
    data = tmp_path / "data"
    monkeypatch.setattr(renamer, "DATA_DIR", data)
    monkeypatch.setattr(renamer, "LOG_FILE", data / "rename_log.json")
    monkeypatch.setattr(renamer, "SETTINGS_FILE", data / "settings.json")
    return data


@pytest.fixture
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("unexpected network call")
    monkeypatch.setattr(renamer.SESSION, "get", fail)


def make_pdf(path, lines):
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((50, 80 + 30 * i), line)
    doc.save(path)
    return path


METADATA = {
    "title": "Attention Is All You Need",
    "authors": ["Vaswani, Ashish", "Shazeer, Noam", "Parmar, Niki"],
    "year": "2017",
    "journal": "NeurIPS",
    "publisher": "Curran",
}


# ---------------------------------------------------------------------------
# Filename generation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("authors, expected", [
    ([], "Unknown"),
    (["Kornberg, Roger"], "Kornberg"),
    (["Allis, C. David", "Jenuwein, Thomas"], "Allis & Jenuwein"),
    (["Vaswani, Ashish", "Shazeer, Noam", "Parmar, Niki"], "Vaswani et al."),
    (["Ashish Vaswani"], "Vaswani"),
    (["Edward J. Hu", "Yelong Shen"], "Hu & Shen"),
])
def test_format_author(authors, expected):
    assert renamer._format_author(authors) == expected


@pytest.mark.parametrize("preset, expected", [
    ("standard", "Vaswani et al. - Attention Is All You Need (2017).pdf"),
    ("journal", "Vaswani et al. - Attention Is All You Need - NeurIPS (2017).pdf"),
    ("year_first", "2017 - Vaswani et al. - Attention Is All You Need.pdf"),
    ("compact", "Vaswani et al._2017_Attention Is All You Need.pdf"),
])
def test_generate_filename_presets(preset, expected):
    tpl = renamer.resolve_template(preset)
    assert renamer.generate_filename(METADATA, template=tpl) == expected


def test_generate_filename_custom_template():
    tpl = renamer.resolve_template("{year}_{author}_{publisher}")
    assert renamer.generate_filename(METADATA, template=tpl) == "2017_Vaswani et al._Curran.pdf"


def test_generate_filename_uses_settings_default():
    renamer.save_settings({"template": "custom", "custom_template": "{year} {title}"})
    assert renamer.generate_filename(METADATA) == "2017 Attention Is All You Need.pdf"


def test_sanitize_filename_strips_invalid_chars_and_truncates():
    assert renamer._sanitize_filename('a/b:c*d?  "e"') == "abcd e"
    long = renamer._sanitize_filename("word " * 100)
    assert len(long) <= 200 and not long.endswith(" ")


@pytest.mark.parametrize("bad, message", [
    ("{author} {bogus}", "Unknown template field"),
    ("{author", "Invalid template"),
    ("nonexistent_preset", "not a preset"),
])
def test_resolve_template_rejects_bad_templates(bad, message):
    with pytest.raises(ValueError, match=message):
        renamer.resolve_template(bad)


# ---------------------------------------------------------------------------
# PDF identifier extraction
# ---------------------------------------------------------------------------

def test_extract_doi_from_text(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", ["Some Title Here", "https://doi.org/10.1016/j.molcel.2013.07.020."])
    info = renamer.extract_pdf_info(str(pdf))
    assert info["doi"] == "10.1016/j.molcel.2013.07.020"
    assert info["arxiv_id"] is None


def test_extract_isbn_from_text(tmp_path):
    pdf = make_pdf(tmp_path / "book.pdf", ["A Long Book Title", "ISBN 978-0-262-03384-8"])
    assert renamer.extract_pdf_info(str(pdf))["isbn"] == "9780262033848"


def test_extract_arxiv_id_from_filename(tmp_path):
    pdf = make_pdf(tmp_path / "1706.03762v5.pdf", ["Attention Is All You Need"])
    info = renamer.extract_pdf_info(str(pdf))
    assert info["arxiv_id"] == "1706.03762"
    assert info["arxiv_id_from_text"] is False


def test_extract_arxiv_id_from_first_page(tmp_path):
    pdf = make_pdf(tmp_path / "paper.pdf", ["arXiv:1706.03762v7 [cs.CL] 2 Aug 2023", "Attention Is All You Need"])
    info = renamer.extract_pdf_info(str(pdf))
    assert info["arxiv_id"] == "1706.03762"
    assert info["arxiv_id_from_text"] is True


def test_arxiv_doi_is_routed_to_arxiv(tmp_path):
    pdf = make_pdf(tmp_path / "paper.pdf", ["Some Preprint Title", "doi: 10.48550/arXiv.2106.09685"])
    info = renamer.extract_pdf_info(str(pdf))
    assert info["arxiv_id"] == "2106.09685"
    assert info["doi"] is None


def test_extract_from_unreadable_file(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_text("not a pdf")
    info = renamer.extract_pdf_info(str(bad))
    assert info["doi"] is None and info["arxiv_id"] is None


# ---------------------------------------------------------------------------
# API response parsing
# ---------------------------------------------------------------------------

ARXIV_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <updated>2023-08-02T00:41:18Z</updated>
    <title>Attention Is All
      You Need</title>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <author><name>Niki Parmar</name></author>
    {doi}
  </entry>
</feed>"""


def test_parse_arxiv_uses_first_version_year(no_network):
    m = renamer._parse_arxiv_response(ARXIV_RESPONSE.format(doi="").encode())
    assert m["title"] == "Attention Is All You Need"
    assert m["year"] == "2017"
    assert m["source"] == "arxiv"
    assert renamer.generate_filename(m, renamer.resolve_template("standard")) == \
        "Vaswani et al. - Attention Is All You Need (2017).pdf"


def test_parse_arxiv_prefers_published_doi(monkeypatch):
    published = dict(METADATA, source="crossref", confidence=1.0)
    monkeypatch.setattr(renamer, "crossref_lookup_doi", lambda doi: published if doi == "10.1/x" else None)
    xml = ARXIV_RESPONSE.format(doi="<arxiv:doi>10.1/x</arxiv:doi>").encode()
    assert renamer._parse_arxiv_response(xml) is published


def test_parse_arxiv_unknown_id(no_network):
    xml = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>x</id><title>Error</title></entry></feed>"""
    assert renamer._parse_arxiv_response(xml) is None


def test_parse_crossref_item():
    item = {
        "author": [{"family": "Albeck", "given": "John"}, {"family": "Mills", "given": "Gordon"}],
        "title": ["Frequency-Modulated Pulses of ERK Activity"],
        "published-print": {"date-parts": [[2013, 1]]},
        "published-online": {"date-parts": [[2012, 12]]},
        "short-container-title": ["Mol Cell"],
        "publisher": "Elsevier",
        "DOI": "10.1016/j.molcel.2012.11.002",
    }
    m = renamer._parse_crossref_item(item)
    assert m["authors"] == ["Albeck, John", "Mills, Gordon"]
    assert m["year"] == "2013"
    assert m["journal"] == "Mol Cell"


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_title_search_prefers_article_over_repost(monkeypatch):
    items = [
        {"title": ["Attention Is All You Need"], "type": "posted-content",
         "author": [{"family": "Vaswani"}], "created": {"date-parts": [[2025]]}},
        {"title": ["Attention Is All You Need"], "type": "proceedings-article",
         "author": [{"family": "Vaswani"}], "published-print": {"date-parts": [[2017]]}},
    ]
    monkeypatch.setattr(renamer.SESSION, "get", lambda *a, **k: FakeResponse({"message": {"items": items}}))
    m = renamer.crossref_search_title("Attention Is All You Need")
    assert m["year"] == "2017"
    # Title matches are never reported as certain as a DOI match
    assert m["confidence"] == renamer.TITLE_MATCH_MAX_CONFIDENCE


def test_arxiv_id_cited_in_text_is_ignored_if_title_differs(tmp_path, monkeypatch):
    pdf = make_pdf(tmp_path / "paper.pdf", ["A Different Paper Entirely", "see arXiv:1706.03762"])
    monkeypatch.setattr(renamer, "arxiv_lookup", lambda _id: dict(METADATA, source="arxiv"))
    monkeypatch.setattr(renamer, "crossref_search_title", lambda t: None)
    monkeypatch.setattr(renamer, "semantic_scholar_search", lambda t: None)
    assert renamer.resolve_metadata(str(pdf))["source"] == "manual_review"


# ---------------------------------------------------------------------------
# Scanning, renaming, undo
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_metadata(monkeypatch):
    monkeypatch.setattr(renamer, "resolve_metadata", lambda path: dict(METADATA, source="crossref", confidence=1.0))


def test_find_pdfs_is_case_insensitive_and_optionally_recursive(tmp_path):
    for rel in ["a.pdf", "b.PDF", "notes.txt", "sub/c.Pdf", ".hidden/d.pdf"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
    names = lambda ps: sorted(str(p.relative_to(tmp_path)) for p in ps)
    assert names(renamer.find_pdfs(tmp_path)) == ["a.pdf", "b.PDF"]
    assert names(renamer.find_pdfs(tmp_path, recursive=True)) == ["a.pdf", "b.PDF", "sub/c.Pdf"]


def test_scan_directory_reports_bad_template(tmp_path):
    assert "error" in renamer.scan_directory(tmp_path, template="{nope}")


def test_scan_rename_and_undo_roundtrip(tmp_path, stub_metadata):
    (tmp_path / "sub").mkdir()
    orig = tmp_path / "sub" / "1706.03762v5.PDF"
    orig.write_bytes(b"%PDF")

    scan = renamer.scan_directory(tmp_path, template="standard", recursive=True)
    [f] = scan["files"]
    assert f["relative_path"] == "sub/1706.03762v5.PDF"

    result = renamer.execute_renames([{**f, "new_name": f["proposed_name"]}], session_id="s1")
    [r] = result["results"]
    renamed = tmp_path / "sub" / "Vaswani et al. - Attention Is All You Need (2017).pdf"
    assert r["success"] and renamed.exists() and not orig.exists()

    history = renamer.get_history()
    assert json.loads(renamer.LOG_FILE.read_text()) == history
    assert history[0]["session_id"] == "s1"

    [u] = renamer.undo_session("s1")
    assert u["success"] and orig.exists() and not renamed.exists()
    assert renamer.undo_session("s1") == []


def test_rename_collision_gets_numeric_suffix(tmp_path):
    (tmp_path / "Taken.pdf").write_bytes(b"existing")
    src = tmp_path / "x.pdf"
    src.write_bytes(b"new")
    [r] = renamer.execute_renames([{"original_path": str(src), "new_name": "Taken.pdf"}])["results"]
    assert r["new_path"] == str(tmp_path / "Taken (1).pdf")
    assert (tmp_path / "Taken.pdf").read_bytes() == b"existing"


# ---------------------------------------------------------------------------
# Settings and data dir
# ---------------------------------------------------------------------------

def test_contact_email_goes_in_user_agent(monkeypatch):
    monkeypatch.delenv("PDF_RENAMER_EMAIL", raising=False)
    renamer.save_settings({"contact_email": "someone@example.org"})
    assert "mailto:someone@example.org" in renamer.SESSION.headers["User-Agent"]
    renamer.save_settings({"contact_email": ""})
    assert "mailto" not in renamer.SESSION.headers["User-Agent"]


def test_data_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_RENAMER_DATA_DIR", str(tmp_path / "custom"))
    assert renamer._default_data_dir() == tmp_path / "custom"
