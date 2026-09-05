"""AITHENA real worker.

Runs the pdf_analyzer pipeline against uploaded contracts and writes the results
into the webapp's PostgreSQL schema — a drop-in replacement for the Node stub
worker (scripts/stub-worker.ts). See webapp/worker/README.md.
"""
