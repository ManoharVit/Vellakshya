"""
Coordinate transform utilities for PDF page space and viewport registration.
Handles unrotated page coordinates, page rotation matrices, CropBox offsets,
and canvas pixel scaling.
"""

from __future__ import annotations

import fitz


def get_visible_page_rect(page: fitz.Page) -> fitz.Rect:
    """Returns the visible bounding box of the page respecting its rotation and CropBox."""
    return page.rect


def unrotated_to_visible_rect(
    rect: list[float] | tuple[float, float, float, float] | fitz.Rect,
    page: fitz.Page,
) -> list[float]:
    """
    Transforms raw unrotated PDF coordinates (from get_text or annotations)
    into visible page coordinates using page.rotation_matrix and CropBox offsets.
    """
    r = fitz.Rect(rect)
    rot_matrix = page.rotation_matrix
    transformed_rect = r * rot_matrix

    # Adjust for CropBox displacement if CropBox origin is non-zero
    crop = page.cropbox
    if crop.x0 != 0 or crop.y0 != 0:
        transformed_rect = fitz.Rect(
            transformed_rect.x0 - crop.x0,
            transformed_rect.y0 - crop.y0,
            transformed_rect.x1 - crop.x0,
            transformed_rect.y1 - crop.y0,
        )

    return [
        round(transformed_rect.x0, 2),
        round(transformed_rect.y0, 2),
        round(transformed_rect.x1, 2),
        round(transformed_rect.y1, 2),
    ]


def visible_to_unrotated_rect(
    rect: list[float] | tuple[float, float, float, float] | fitz.Rect,
    page: fitz.Page,
) -> list[float]:
    """
    Transforms visible page coordinates back to unrotated raw PDF coordinate space
    using page.derotation_matrix and CropBox adjustments.
    """
    r = fitz.Rect(rect)
    crop = page.cropbox
    if crop.x0 != 0 or crop.y0 != 0:
        r = fitz.Rect(
            r.x0 + crop.x0,
            r.y0 + crop.y0,
            r.x1 + crop.x0,
            r.y1 + crop.y0,
        )

    derot_matrix = page.derotation_matrix
    unrotated_rect = r * derot_matrix
    return [
        round(unrotated_rect.x0, 2),
        round(unrotated_rect.y0, 2),
        round(unrotated_rect.x1, 2),
        round(unrotated_rect.y1, 2),
    ]


def to_canvas_pixels(
    visible_rect: list[float],
    zoom: float = 1.0,
    dpr: float = 1.0,
) -> dict[str, float]:
    """Maps visible page space coordinates [x0, y0, x1, y1] to screen canvas pixel values."""
    scale = zoom * dpr
    x0, y0, x1, y1 = visible_rect
    return {
        "left": round(x0 * scale, 2),
        "top": round(y0 * scale, 2),
        "width": round((x1 - x0) * scale, 2),
        "height": round((y1 - y0) * scale, 2),
    }
