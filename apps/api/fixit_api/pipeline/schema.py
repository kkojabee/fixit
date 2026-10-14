from dataclasses import dataclass, field
from typing import List, Optional, Tuple

@dataclass
class LineStyle:
    text: str
    font_size: int = 26
    font_family: str = "NanumSquareEB"
    font_weight: str = "ExtraBold"
    scale_x: float = 0.95  # Horizontal scale (기본 장평 95%)
    letter_spacing: float = -0.5  # Tracking (자간)
    color: str = "#000000"
    gap_after: int = 6  # Spacing in pixels to next line

@dataclass
class TextRegion:
    id: str
    observed: str
    corrected: str
    bbox: Tuple[int, int, int, int]  # (x, y, width, height) in original pixels
    font_family: str = "NanumSquare"
    font_weight: str = "ExtraBold"  # Regular, Bold, ExtraBold
    font_size: int = 26
    scale_x: float = 0.95  # Default 장평 95%
    letter_spacing: float = -0.8  # Default 자간
    text_color: str = "#000000"
    align: str = "left"  # left, center, right
    valign: str = "center"  # center, top, bottom
    line_gap: int = 6  # Explicit line spacing (줄간격) in pixels
    padding_top: int = 0
    add_shadow: bool = False
    shadow_offset: Tuple[int, int] = (1, 1)
    shadow_color: str = "rgba(0,0,0,45)"
    blur_radius: float = 0.35  # Subtle Gaussian blur for natural raster look
    mask_padding: int = 6  # Padding for background clearing
    bg_color: Optional[str] = None  # Explicit background color override (e.g. hex #356ba6)
    clean_bbox: Optional[Tuple[int, int, int, int]] = None  # Explicit bounding box for inpainting
    lines: Optional[List[LineStyle]] = None  # Per-line specific typography tuning

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "observed": self.observed,
            "corrected": self.corrected,
            "bbox": list(self.bbox),
            "clean_bbox": list(self.clean_bbox) if self.clean_bbox else list(self.bbox),
            "font_family": self.font_family,
            "font_weight": self.font_weight,
            "font_size": self.font_size,
            "scale_x": self.scale_x,
            "letter_spacing": self.letter_spacing,
            "text_color": self.text_color,
            "align": self.align,
            "valign": self.valign,
            "line_gap": self.line_gap,
            "padding_top": self.padding_top,
            "blur_radius": self.blur_radius,
            "bg_color": self.bg_color
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TextRegion":
        return cls(
            id=str(data.get("id", "region")),
            observed=str(data.get("observed", "")),
            corrected=str(data.get("corrected", data.get("observed", ""))),
            bbox=tuple(data.get("bbox", [0, 0, 100, 30])),
            clean_bbox=tuple(data["clean_bbox"]) if data.get("clean_bbox") else None,
            font_family=str(data.get("font_family", "NanumSquare")),
            font_weight=str(data.get("font_weight", "Bold")),
            font_size=int(data.get("font_size", 26)),
            scale_x=float(data.get("scale_x", 0.90)),
            letter_spacing=float(data.get("letter_spacing", -0.6)),
            text_color=str(data.get("text_color", "#000000")),
            align=str(data.get("align", "left")),
            valign=str(data.get("valign", "top")),
            line_gap=int(data.get("line_gap", 6)),
            padding_top=int(data.get("padding_top", 0)),
            blur_radius=float(data.get("blur_radius", 0.35)),
            bg_color=data.get("bg_color")
        )
