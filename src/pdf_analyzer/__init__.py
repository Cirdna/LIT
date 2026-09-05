"""pdf_analyzer: standardized PDF contract analyzer engine.

Stages:
  1. stage1_ingest   - conversion router + DPI-standardized rendering
  2. stage2_vlm      - VLM semantic extraction (Qwen2.5-VL / InternVL)
     stage2_ocr      - OCR verbatim word-level extraction (Tesseract)
  3. stage3_reconcile - fuzzy spatial reconciliation + bounding box envelope
  4. schema          - enriched 41-CUAD JSON schema
  5. (frontend/)     - PDF viewer click-to-jump integration
"""

__version__ = "0.1.0"
