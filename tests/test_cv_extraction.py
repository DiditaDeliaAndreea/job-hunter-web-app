import io

import pytest
from docx import Document
from fastapi import HTTPException
from pypdf import PdfWriter

import api.index as api


@pytest.mark.asyncio
async def test_scanned_or_empty_pdf_is_rejected():
    pdf_bytes = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(pdf_bytes)

    with pytest.raises(HTTPException, match="scanned or image-only"):
        await api.extract_cv_text_from_bytes("resume.pdf", pdf_bytes.getvalue())


@pytest.mark.asyncio
async def test_empty_docx_is_rejected():
    docx_bytes = io.BytesIO()
    Document().save(docx_bytes)

    with pytest.raises(HTTPException, match="selectable text"):
        await api.extract_cv_text_from_bytes("resume.docx", docx_bytes.getvalue())


@pytest.mark.asyncio
async def test_text_based_pdf_is_accepted():
    pdf_bytes = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(pdf_bytes)

    assert not api.has_extractable_cv_text(" ")
    assert api.has_extractable_cv_text("Product Operations Manager with 8 years experience")