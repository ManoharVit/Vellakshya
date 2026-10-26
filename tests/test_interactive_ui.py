import pytest
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_static_assets_and_vendor_libraries():
    """Verify all vendor libraries and UI assets are correctly served."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "interactivePdfViewer" in res_index.text
    assert "wordFindBar" in res_index.text
    assert "wfbSearchInput" in res_index.text
    assert "wfbReplaceInput" in res_index.text
    assert "btnToggleWordFind" in res_index.text

    res_pdf_js = client.get("/vendor/pdf.min.js")
    assert res_pdf_js.status_code == 200
    assert len(res_pdf_js.content) > 100_000

    res_worker_js = client.get("/vendor/pdf.worker.min.js")
    assert res_worker_js.status_code == 200
    assert len(res_worker_js.content) > 500_000

    res_app_js = client.get("/js/app.js")
    assert res_app_js.status_code == 200
    assert "renderInteractivePdfViewer" in res_app_js.text
    assert "attachPageInteractionHandlers" in res_app_js.text
    assert "executeWordFind" in res_app_js.text
    assert "executeWordReplace" in res_app_js.text
    assert "pointerTooltip" in res_app_js.text

    res_css = client.get("/css/styles.css")
    assert res_css.status_code == 200
    assert "pdf-match-highlight" in res_css.text
    assert "pdf-match-active" in res_css.text
    assert "pointer-tooltip" in res_css.text
    assert "drag-marquee" in res_css.text


def test_undo_redo_ui_assets():
    """Verify Undo/Redo controls, history pill, toast and JS handlers are present."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "btnHeaderUndo" in res_index.text
    assert "btnHeaderRedo" in res_index.text
    assert "btnToolbarUndo" in res_index.text
    assert "btnToolbarRedo" in res_index.text
    assert "historyStepPill" in res_index.text
    assert "historyToast" in res_index.text
    assert "zoomControlsGroup" in res_index.text
    assert "btnZoomIn" in res_index.text
    assert "btnFitWidth" in res_index.text

    res_app_js = client.get("/js/app.js")
    assert res_app_js.status_code == 200
    assert "performUndo" in res_app_js.text
    assert "performRedo" in res_app_js.text
    assert "pushHistory" in res_app_js.text
    assert "updateUndoRedoUI" in res_app_js.text
    assert "showHistoryToast" in res_app_js.text
    assert "setupZoomControls" in res_app_js.text

    res_css = client.get("/css/styles.css")
    assert res_css.status_code == 200
    assert "btn-hdr-action" in res_css.text
    assert "history-step-pill" in res_css.text
    assert "history-toast" in res_css.text
    assert "zoom-controls-group" in res_css.text


def test_word_replace_ui_integration():
    """Verify Word-Style Replace and Replace All button IDs and logic in HTML & JS."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "wfbBtnReplace" in res_index.text
    assert "wfbBtnReplaceAll" in res_index.text
    assert "wfbMatchBadge" in res_index.text

    res_app_js = client.get("/js/app.js")
    assert res_app_js.status_code == 200
    assert "executeWordReplace" in res_app_js.text
    assert "executeWordReplaceAll" in res_app_js.text
    assert "occurrenceOnPage" in res_app_js.text
    assert "single: true" in res_app_js.text
    assert "single: false" in res_app_js.text
    assert "preserve_style: true" in res_app_js.text
    assert "repPreserveStyle" in res_app_js.text

    assert "wfbStylePill" in res_index.text
    res_css = client.get("/css/styles.css")
    assert res_css.status_code == 200
    assert "wfb-style-pill" in res_css.text


def test_deep_document_inspector_ui():
    """Verify Deep Document Inspector elements, quick actions, and edit drawer in HTML, CSS & JS."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "Deep Document Inspector" in res_index.text
    assert "inspectorView" in res_index.text
    assert "infoTabBtn" in res_index.text

    res_css = client.get("/css/styles.css")
    assert res_css.status_code == 200
    assert "inspect-audit-box" in res_css.text
    assert "inspect-perm-grid" in res_css.text
    assert "perm-pill-yes" in res_css.text
    assert "meta-edit-drawer" in res_css.text

    res_app_js = client.get("/js/app.js")
    assert res_app_js.status_code == 200
    assert "btnSideEditMeta" in res_app_js.text
    assert "btnSideDeleteAllMeta" in res_app_js.text
    assert "btnSideExportReport" in res_app_js.text
    assert "editMetaDrawer" in res_app_js.text
    assert "btnSaveMeta" in res_app_js.text
    assert "chkSelectAllMeta" in res_app_js.text
    assert "exportInspectionReport" in res_app_js.text
    assert "executeSaveMetadata" in res_app_js.text


