"""Compatibility shim: `python app.py` starts the web UI."""

from pdf_renamer.app import serve

if __name__ == "__main__":
    serve()
