"""Compatibility shim: `python renamer.py ...` runs the pdf-renamer CLI."""

from pdf_renamer.renamer import main

if __name__ == "__main__":
    main()
