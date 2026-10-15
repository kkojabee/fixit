import functools
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .schema import TextRegion, LineStyle

class TextRenderer:
    """Exact typography imitation engine using NanumSquare:
    Matches font family, weight (ExtraBold/Bold), tracking (자간), aspect ratio (장평),
    and 0.45px Gaussian edge blending to be indistinguishable from original graphics."""
    
    FONT_MAP = {
        "NanumSquareEB": "fonts/NanumSquareEB.ttf",
        "NanumSquare-ExtraBold": "fonts/NanumSquareEB.ttf",
        "NanumSquareB": "fonts/NanumSquareB.ttf",
        "NanumSquare-Bold": "fonts/NanumSquareB.ttf",
        "NanumSquareR": "fonts/NanumSquareR.ttf",
        "NanumSquare-Regular": "fonts/NanumSquareR.ttf",
        "NotoSansKR-Bold": "fonts/NotoSansKR-Bold.ttf",
        "NotoSansKR-Regular": "fonts/NotoSansKR-Regular.ttf",
        "Paperlogy-7Bold": "fonts/Paperlogy-7Bold.ttf",
        "Paperlogy-4Regular": "fonts/Paperlogy-4Regular.ttf",
    }
    
    def __init__(self, font_dir: str = "fonts", scale_factor: int = 3):
        self.font_dir = Path(font_dir)
        self.scale = scale_factor
        self.font_eb_path = str(self.font_dir / "NanumSquareEB.ttf")
        self.font_b_path = str(self.font_dir / "NanumSquareB.ttf")
        self.font_r_path = str(self.font_dir / "NanumSquareR.ttf")
        self.fallback_font_path = str(self.font_dir / "NotoSansKR-Bold.ttf")

    def resolve_font_path(self, font_family: str, font_weight: str = "Bold") -> str:
        """Resolve font path based on 3 supported font families and 7 weights."""
        fam = str(font_family or "").lower()
        wt = str(font_weight or "").lower()

        if "noto" in fam:
            if "reg" in wt or "reg" in fam:
                p = self.font_dir / "NotoSansKR-Regular.ttf"
            else:
                p = self.font_dir / "NotoSansKR-Bold.ttf"
        elif "paper" in fam:
            if "reg" in wt or "reg" in fam:
                p = self.font_dir / "Paperlogy-4Regular.ttf"
            else:
                p = self.font_dir / "Paperlogy-7Bold.ttf"
        else:
            # NanumSquare default
            if "extra" in wt or "eb" in wt or "extra" in fam or "eb" in fam:
                p = self.font_dir / "NanumSquareEB.ttf"
            elif "reg" in wt or "reg" in fam:
                p = self.font_dir / "NanumSquareR.ttf"
            else:
                p = self.font_dir / "NanumSquareB.ttf"

        if p.exists():
            return str(p)
        if Path(self.fallback_font_path).exists():
            return self.fallback_font_path
        if Path(self.font_b_path).exists():
            return self.font_b_path
        return str(p)

    @staticmethod
    @functools.lru_cache(maxsize=256)
    def _cached_truetype(font_path: str, size: int):
        try:
            if font_path and Path(font_path).exists():
                return ImageFont.truetype(font_path, size)
        except Exception:
            pass
        return None

    def _load_font(self, font_path: str, size: int):
        f = self._cached_truetype(font_path, size)
        if f is not None:
            return f
        if self.fallback_font_path:
            f_fb = self._cached_truetype(self.fallback_font_path, size)
            if f_fb is not None:
                return f_fb
        f_bold = self._cached_truetype(self.font_b_path, size)
        if f_bold is not None:
            return f_bold
        return ImageFont.load_default()

    def render_line_exact(
        self,
        text: str,
        font_path: str,
        font_size_pt: int,
        scale_x: float = 0.92,
        letter_spacing: float = -0.5,
        text_color: Tuple[int, int, int] = (0, 0, 0),
        blur_radius: float = 0.0,
        max_width: Optional[int] = None
    ) -> Image.Image:
        """Render a single line with exact glyph size, adaptive letter spacing/aspect ratio fit, and crisp subpixel anti-aliasing."""
        s = self.scale
        s_size = int(round(font_size_pt * s))
        
        font = self._load_font(font_path, s_size)
        fallback_font = self._load_font(self.fallback_font_path, s_size)
        
        chars = list(text)
        char_widths = []
        for c in chars:
            f = font if font.getmask(c).getbbox() else fallback_font
            bb = f.getbbox(c)
            cw = bb[2] - bb[0] if bb[2] > bb[0] else f.getbbox("o")[2]
            char_widths.append(cw)

        # Keep font_size and scale_x strictly uniform across the block
        # Only compress letter_spacing per line when exceeding max_width (never increase letter_spacing)
        actual_letter_spacing = letter_spacing
        actual_scale_x = scale_x

        if max_width and max_width > 0 and len(chars) > 1:
            sum_cw = sum(char_widths)
            num_gaps = len(chars) - 1
            est_w = (sum_cw + num_gaps * int(actual_letter_spacing * s)) * actual_scale_x / s
            if est_w > max_width:
                # Calculate required tracking to fit strictly within max_width
                max_canvas_w = (max_width * s) / actual_scale_x
                req_spacing_px = (max_canvas_w - sum_cw) / num_gaps
                req_spacing = req_spacing_px / s
                # Only reduce letter_spacing, never increase
                if req_spacing < actual_letter_spacing:
                    actual_letter_spacing = req_spacing

        spacing_px = int(actual_letter_spacing * s)
        total_w = sum(char_widths) + max(0, len(chars) - 1) * spacing_px
        total_h = int(s_size * 1.5) + 10 * s
        
        canvas = Image.new("RGBA", (max(10, total_w + 30 * s), total_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        
        cx = 0
        base_y = int(s_size * 0.2)
        for c in chars:
            f = font if font.getmask(c).getbbox() else fallback_font
            y_pos = base_y
            if c == "•":
                # Bullet vertical optical centering with Korean glyphs
                b_bb = f.getbbox("•")
                ref_bb = f.getbbox("가")
                if b_bb and ref_bb:
                    ref_mid = (ref_bb[1] + ref_bb[3]) / 2.0
                    b_mid = (b_bb[1] + b_bb[3]) / 2.0
                    y_pos += int(ref_mid - b_mid)
            draw.text((cx, y_pos), c, font=f, fill=(*text_color, 255))
            bb = f.getbbox(c)
            cw = bb[2] - bb[0] if bb[2] > bb[0] else f.getbbox("o")[2]
            cx += cw + spacing_px
            
        alpha_bb = canvas.getbbox()
        if not alpha_bb:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
            
        cropped = canvas.crop((0, alpha_bb[1], max(1, cx), alpha_bb[3]))
        target_w = max(1, round(cx * actual_scale_x / s))
        if max_width and target_w > max_width:
            target_w = max_width  # Strictly contain within masking area!
        target_h = max(1, round((alpha_bb[3] - alpha_bb[1]) / s))
        
        # High quality LANCZOS downsampling produces sharp, pristine Korean text
        resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # Subpixel alpha enhancement: preserves anti-aliased geometry while restoring deep, punchy stroke density
        r, g, b, a = resized.split()
        a_np = np.array(a, dtype=np.float32) / 255.0
        a_np = np.clip(np.power(a_np, 0.85) * 1.12, 0.0, 1.0)
        a_boosted = Image.fromarray((a_np * 255).astype(np.uint8))
        resized = Image.merge("RGBA", (r, g, b, a_boosted))

        if blur_radius > 0.05:
            resized = resized.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        return resized

    @staticmethod
    def parse_color(color_val: str) -> Tuple[int, int, int]:
        """Parse hex or name color to RGB tuple."""
        if not color_val or not isinstance(color_val, str):
            return (0, 0, 0)
        c = color_val.strip()
        if c.startswith("#") and len(c) == 7:
            try:
                return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
            except Exception:
                return (0, 0, 0)
        if c.lower() == "white" or c == "#ffffff":
            return (255, 255, 255)
        return (0, 0, 0)

    def composite_onto(self, base_image: Image.Image, original_bgr: Optional[np.ndarray] = None, regions: Optional[List[TextRegion]] = None) -> Image.Image:
        """Render all regions with exact typography styles and precision line spacing (줄간) onto cleaned base image."""
        if regions is None and isinstance(original_bgr, list):
            regions = original_bgr
            original_bgr = None
        regions = regions or []
        base_rgba = base_image.convert("RGBA")
        overlay = Image.new("RGBA", base_rgba.size, (0, 0, 0, 0))

        for reg in regions:
            rx, ry, bw, bh = reg.bbox
            
            # Extract line specifications for this block
            line_items = []
            if reg.lines:
                for lspec in reg.lines:
                    l_weight = getattr(lspec, "font_weight", None) or getattr(reg, "font_weight", "Bold")
                    font_file = self.resolve_font_path(lspec.font_family, l_weight)
                    col = self.parse_color(lspec.color)
                    gap = getattr(lspec, "gap_after", 6)
                    line_items.append({"text": lspec.text, "font_file": font_file, "color": col, "gap_after": gap, "orig_fsize": lspec.font_size, "orig_scale_x": lspec.scale_x, "orig_spacing": lspec.letter_spacing})
            else:
                raw_lines = [l for l in reg.corrected.split("\n") if l.strip()]
                font_file = self.resolve_font_path(reg.font_family, getattr(reg, "font_weight", "Bold"))
                col = self.parse_color(reg.text_color)
                for line in raw_lines:
                    line_items.append({"text": line, "font_file": font_file, "color": col, "gap_after": reg.line_gap, "orig_fsize": reg.font_size, "orig_scale_x": reg.scale_x, "orig_spacing": reg.letter_spacing})

            if not line_items:
                continue

            # Block-Level Uniform Styling:
            # 1. Base scale_x is 0.95 (95% 장평) for all text by default.
            # 2. Block shares uniform font_size and scale_x across all lines.
            # 3. If any line has extreme tight tracking (< -1.8), first reduce block scale_x (down to 0.78).
            # 4. If still unresolved, reduce block font_size by 0.5pt increments.
            # 5. Never increase letter_spacing beyond default.
            s = self.scale
            block_fsize = float(line_items[0]["orig_fsize"] or reg.font_size or 24)
            raw_scale = float(line_items[0]["orig_scale_x"] or reg.scale_x or 0.95)
            block_scale_x = min(0.95, raw_scale)
            base_spacing = float(line_items[0]["orig_spacing"] or reg.letter_spacing or -0.5)
            MIN_TRACKING = -1.8

            # LLM 기준 폰트크기, 줄바꿈 100% 보존 (임의 줄바꿈 및 폰트 축소 제거)
            block_fsize = float(line_items[0]["orig_fsize"] or reg.font_size or 24)

            def evaluate_min_tracking(test_fsize: float, test_scale: float) -> float:
                min_tr = 999.0
                for item in line_items:
                    chars = list(item["text"])
                    if len(chars) <= 1:
                        continue
                    font = self._load_font(item["font_file"], int(round(test_fsize * s)))
                    fallback_font = self._load_font(self.fallback_font_path, int(round(test_fsize * s)))
                    sum_cw = sum(font.getbbox(c)[2] - font.getbbox(c)[0] if font.getmask(c).getbbox() else fallback_font.getbbox(c)[2] - fallback_font.getbbox(c)[0] for c in chars)
                    num_gaps = len(chars) - 1
                    max_canvas_w = (bw * s) / test_scale
                    req_tr = (max_canvas_w - sum_cw) / (num_gaps * s)
                    if req_tr < min_tr:
                        min_tr = req_tr
                return min_tr

            # Step 1: If extreme negative tracking is detected, reduce scale_x down to 0.78
            if bw > 0:
                while block_scale_x > 0.80:
                    worst_tr = evaluate_min_tracking(block_fsize, block_scale_x)
                    if worst_tr >= MIN_TRACKING:
                        break
                    block_scale_x = max(0.78, round(block_scale_x - 0.03, 3))

                # Step 2: If still unresolved past scale_x 0.80, lower font_size in 0.5pt increments
                while block_fsize > 13.0:
                    worst_tr = evaluate_min_tracking(block_fsize, block_scale_x)
                    if worst_tr >= MIN_TRACKING:
                        break
                    block_fsize = round(block_fsize - 0.5, 1)

            # Render all lines with identical block_fsize and block_scale_x
            line_patches = []
            for item in line_items:
                patch = self.render_line_exact(
                    text=item["text"],
                    font_path=item["font_file"],
                    font_size_pt=block_fsize,
                    scale_x=block_scale_x,
                    letter_spacing=base_spacing,
                    text_color=item["color"],
                    max_width=bw
                )
                line_patches.append(patch)

            if not line_patches:
                continue

            # Calculate total vertical height with explicit line spacing (줄간격)
            num_patches = len(line_patches)
            tot_patch_h = sum(p.height for p in line_patches)
            if num_patches > 1 and bh > tot_patch_h:
                computed_gap = max(2, int((bh - tot_patch_h) / (num_patches - 1)))
                gaps = [computed_gap] * (num_patches - 1)
                total_text_h = tot_patch_h + sum(gaps)
            elif reg.lines:
                gaps = [ls.gap_after for ls in reg.lines[:-1]]
                total_text_h = tot_patch_h + sum(gaps)
            else:
                gaps = [reg.line_gap] * max(0, num_patches - 1)
                total_text_h = tot_patch_h + sum(gaps)

            # Vertical positioning
            if reg.valign == "top":
                curr_y = ry + reg.padding_top
            elif reg.valign == "bottom":
                curr_y = ry + max(0, bh - total_text_h)
            else:  # "center"
                curr_y = ry + max(0, (bh - total_text_h) // 2)

            # Paste each line sequentially with constant, controlled line spacing
            for idx, patch in enumerate(line_patches):
                if reg.align == "center":
                    pos_x = rx + max(0, (bw - patch.width) // 2)
                elif reg.align == "right":
                    pos_x = rx + max(0, bw - patch.width)
                else:  # "left"
                    pos_x = rx

                overlay.paste(patch, (pos_x, curr_y), patch)
                gap = gaps[idx] if idx < len(gaps) else 0
                curr_y += patch.height + gap

        result = Image.alpha_composite(base_rgba, overlay)
        if base_image.mode == "RGB":
            return result.convert("RGB")
        return result
