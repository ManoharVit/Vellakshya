"""
API integration tests for PDF Workbench Pro endpoints.
"""
from fastapi.testclient import TestClient
import fitz
from app.main import app

client = TestClient(app)


def get_sample_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((50, 100), "Hello API Acrobat Pro!", fontsize=18)
    data = doc.tobytes()
    doc.close()
    return data


def test_root_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "Vellakshya" in response.text or "PDF Workbench" in response.text


def test_api_convert_html_fixed():
    pdf_bytes = get_sample_pdf_bytes()
    response = client.post(
        "/api/convert/html",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"mode": "fixed"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Hello API Acrobat Pro!" in response.text


def test_api_convert_html_semantic():
    pdf_bytes = get_sample_pdf_bytes()
    response = client.post(
        "/api/convert/html",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"mode": "semantic"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Hello API Acrobat Pro!" in response.text


def test_api_inspect():
    pdf_bytes = get_sample_pdf_bytes()
    response = client.post(
        "/api/inspect",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page_count"] == 1
    assert data["is_encrypted"] is False


def test_api_delete_metadata():
    pdf_bytes = get_sample_pdf_bytes()
    # 1. Update metadata first
    up_res = client.post(
        "/api/inspect/update-metadata",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"title": "Test Title", "author": "Test Author"},
    )
    assert up_res.status_code == 200

    # 2. Delete specific metadata field (title)
    del_res1 = client.post(
        "/api/inspect/delete-metadata",
        files={"file": ("test.pdf", up_res.content, "application/pdf")},
        data={"fields": "title"},
    )
    assert del_res1.status_code == 200
    doc1 = fitz.open(stream=del_res1.content, filetype="pdf")
    assert doc1.metadata["title"] == ""
    assert doc1.metadata["author"] == "Test Author"
    doc1.close()

    # 3. Delete all metadata
    del_res2 = client.post(
        "/api/inspect/delete-metadata",
        files={"file": ("test.pdf", del_res1.content, "application/pdf")},
    )
    assert del_res2.status_code == 200
    doc2 = fitz.open(stream=del_res2.content, filetype="pdf")
    assert doc2.metadata["title"] == ""
    assert doc2.metadata["author"] == ""
    doc2.close()


def test_api_watermark():
    pdf_bytes = get_sample_pdf_bytes()
    response = client.post(
        "/api/edit/watermark",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"text": "TOP SECRET", "opacity": 0.3, "font_size": 40, "angle": 45},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


def test_api_replace_text():
    pdf_bytes = get_sample_pdf_bytes()
    response = client.post(
        "/api/edit/replace-text",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={
            "search_text": "Hello API Acrobat Pro!",
            "replacement_text": "Modified Text 2026",
            "color": "#000000",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-replacement-count"] == "1"
    doc = fitz.open(stream=response.content, filetype="pdf")
    assert "Modified Text 2026" in doc[0].get_text()
    doc.close()


def test_api_insert_text():
    pdf_bytes = get_sample_pdf_bytes()
    response = client.post(
        "/api/edit/insert-text",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={
            "page": 1,
            "text": "Inserted Text Content",
            "x": 60.0,
            "y": 180.0,
            "font_size": 12,
            "color": "#ff0000",
            "bg_fill": True,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    doc = fitz.open(stream=response.content, filetype="pdf")
    assert "Inserted Text Content" in doc[0].get_text()
    doc.close()


def test_api_whiteout():
    pdf_bytes = get_sample_pdf_bytes()
    response = client.post(
        "/api/edit/whiteout",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"page": 1, "x0": 40.0, "y0": 90.0, "x1": 250.0, "y1": 115.0},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    doc = fitz.open(stream=response.content, filetype="pdf")
    assert "Hello API Acrobat Pro!" not in doc[0].get_text()
    doc.close()


def test_api_replace_text_batch_and_sequential():
    import json
    pdf_bytes = get_sample_pdf_bytes()
    # Step 1: Replace via batch JSON on non-overlapping boundaries
    rules = json.dumps([
        {"search": "Hello", "replace": "Hi"},
        {"search": "Pro", "replace": "Max"},
    ])
    res1 = client.post(
        "/api/edit/replace-text",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"rules": rules},
    )
    assert res1.status_code == 200
    doc1 = fitz.open(stream=res1.content, filetype="pdf")
    t1 = doc1[0].get_text()
    assert "Hi" in t1
    assert "Max" in t1
    assert "Hello" not in t1
    assert "Pro" not in t1
    doc1.close()

    # Step 2: Sequential chaining - feed the result of Step 1 into another replace call
    res2 = client.post(
        "/api/edit/replace-text",
        files={"file": ("test.pdf", res1.content, "application/pdf")},
        data={"search_text": "Acrobat", "replacement_text": "Suite"},
    )
    assert res2.status_code == 200
    doc2 = fitz.open(stream=res2.content, filetype="pdf")
    t2 = doc2[0].get_text()
    assert "Hi" in t2
    assert "Max" in t2
    assert "Suite" in t2
    assert "Acrobat" not in t2
    doc2.close()


def test_api_crop_pages():
    pdf = get_sample_pdf_bytes()
    res = client.post(
        "/api/organize/crop",
        files={"file": ("test.pdf", pdf, "application/pdf")},
        data={"x0": "40", "y0": "40", "x1": "440", "y1": "640"},
    )
    assert res.status_code == 200
    doc = fitz.open(stream=res.content, filetype="pdf")
    assert doc[0].rect.width == 400
    assert doc[0].rect.height == 600
    doc.close()


def test_api_single_replace_vs_replace_all():
    import json
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(fitz.Point(72, 100), "DRAFT proposal DRAFT section DRAFT final", fontsize=14)
    multi_pdf = doc.tobytes()
    doc.close()

    # 1. Test single replace: single=true, occurrence=1
    res_single = client.post(
        "/api/edit/replace-text",
        files={"file": ("draft.pdf", multi_pdf, "application/pdf")},
        data={
            "rules": json.dumps([
                {
                    "search_text": "DRAFT",
                    "replacement_text": "REVIEW",
                    "single": True,
                    "occurrence": 1,
                }
            ]),
            "single": "true",
        },
    )
    assert res_single.status_code == 200
    assert res_single.headers["x-replacement-count"] == "1"
    doc_single = fitz.open(stream=res_single.content, filetype="pdf")
    t_single = doc_single[0].get_text()
    assert "REVIEW" in t_single
    assert "DRAFT" in t_single
    assert len(doc_single[0].search_for("DRAFT")) == 2
    doc_single.close()

    # 2. Test replace all: single=false
    res_all = client.post(
        "/api/edit/replace-text",
        files={"file": ("draft.pdf", multi_pdf, "application/pdf")},
        data={
            "rules": json.dumps([
                {
                    "search_text": "DRAFT",
                    "replacement_text": "APPROVED",
                    "single": False,
                }
            ]),
            "single": "false",
        },
    )
    assert res_all.status_code == 200
    assert res_all.headers["x-replacement-count"] == "3"
    doc_all = fitz.open(stream=res_all.content, filetype="pdf")
    t_all = doc_all[0].get_text()
    assert "APPROVED" in t_all
    assert "DRAFT" not in t_all
    assert len(doc_all[0].search_for("DRAFT")) == 0
    doc_all.close()


def test_api_replace_text_preserves_same_color_and_font():
    import json
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Magenta bold Times
    page.insert_text(fitz.Point(72, 120), "Company: OLD_CORP headquarters", fontname="times-bold", fontsize=16, color=(0.75, 0.1, 0.6))
    sample_pdf = doc.tobytes()
    doc.close()

    res = client.post(
        "/api/edit/replace-text",
        files={"file": ("corp.pdf", sample_pdf, "application/pdf")},
        data={
            "rules": json.dumps([
                {
                    "search_text": "OLD_CORP",
                    "replacement_text": "NEW_VENTURES_INC",
                    "preserve_style": True,
                }
            ]),
            "preserve_style": "true",
        },
    )
    assert res.status_code == 200
    assert res.headers["x-replacement-count"] == "1"

    out_doc = fitz.open(stream=res.content, filetype="pdf")
    out_page = out_doc[0]
    blocks = out_page.get_text("dict")["blocks"]
    spans = [s for b in blocks if b.get("type") == 0 for l in b.get("lines", []) for s in l.get("spans", [])]
    target_span = next(s for s in spans if "NEW_VENTURES_INC" in s["text"])

    assert target_span["font"] == "Times-Bold"
    assert abs(target_span["size"] - 16.0) < 0.2
    c = target_span["color"]
    rgb = (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)
    assert abs(rgb[0] - 0.75) < 0.05
    assert abs(rgb[1] - 0.1) < 0.05
    assert abs(rgb[2] - 0.6) < 0.05
    out_doc.close()


def test_api_update_metadata_and_deep_inspection():
    pdf = get_sample_pdf_bytes()

    # Update metadata with all fields
    update_res = client.post(
        "/api/inspect/update-metadata",
        files={"file": ("test.pdf", pdf, "application/pdf")},
        data={
            "title": "Comprehensive Legal Dossier",
            "author": "Chief Legal Officer",
            "subject": "Corporate Governance",
            "keywords": "Legal, Compliance, 2026",
            "creator": "Legal Workstation",
            "producer": "PyMuPDF Workbench Engine",
        },
    )
    assert update_res.status_code == 200

    # Run Deep Inspection on the updated document
    insp_res = client.post(
        "/api/inspect",
        files={"file": ("updated.pdf", update_res.content, "application/pdf")},
    )
    assert insp_res.status_code == 200
    data = insp_res.json()

    # Verify deep inspection payload
    assert data["metadata"]["title"] == "Comprehensive Legal Dossier"
    assert data["metadata"]["author"] == "Chief Legal Officer"
    assert data["metadata"]["subject"] == "Corporate Governance"
    assert data["metadata"]["keywords"] == "Legal, Compliance, 2026"
    assert data["metadata"]["creator"] == "Legal Workstation"
    assert data["metadata"]["producer"] == "PyMuPDF Workbench Engine"
    assert "permissions" in data
    assert "stats" in data
    assert data["stats"]["total_words"] >= 1
    assert data["file_size_bytes"] > 0
    assert len(data["pages"]) >= 1
    assert data["pages"][0]["format"] in ("Letter", "A4", "Custom", "612 × 792 pt")




