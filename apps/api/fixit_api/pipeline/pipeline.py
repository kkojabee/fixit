import json
import time
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from fixit_api.config import settings
from .schema import TextRegion
from .strata_ocr import StrataOCR
from .lama_inpaint import LamaInpainter
from .text_renderer import TextRenderer

class ImageRestorationPipeline:
    """End-to-End Image Restoration Pipeline: Dual VLM OCR + Smart Inpaint + Multi-Font Typography Transfer."""
    
    def __init__(
        self,
        strata_url: Optional[str] = None,
        lama_device: str = "cpu",
        font_dir: Optional[str] = None,
        supersample_scale: int = 3
    ):
        fdir = font_dir or getattr(settings, "FONTS_DIR", "fonts")
        self.font_dir = fdir
        self.ocr_engine = StrataOCR(api_url=strata_url or getattr(settings, "STRATA_VLM_URL", None))
        self.inpaint_engine = LamaInpainter(device=lama_device)
        self.text_renderer = TextRenderer(font_dir=fdir, scale_factor=supersample_scale)
        header_font_path = Path(fdir) / "NotoSansKR-Regular.ttf"
        if header_font_path.exists():
            self.header_font = ImageFont.truetype(str(header_font_path), 14)
        else:
            self.header_font = ImageFont.load_default()

    def analyze(self, image_path: Path, model_type: str = "strata_non_thinking") -> Tuple[List[TextRegion], Dict[str, Any]]:
        """Step 1: Extract & calibrate regions with Dual VLM (Strata ⇄ Azure GPT-6.1-sol)."""
        return self.ocr_engine.extract_regions(image_path, model_type=model_type)

    def inpaint(self, original_img: Image.Image, regions: List[TextRegion]) -> Image.Image:
        """Step 2: Smart inpainting (Solid Card Fill + CPU LaMa)."""
        return self.inpaint_engine.inpaint(original_img, regions)

    def render(self, bg_img: Image.Image, regions: List[TextRegion], orig_bgr: Optional[np.ndarray] = None) -> Image.Image:
        """Step 3: High-resolution typography compositing using 3 supported font families."""
        return self.text_renderer.composite_onto(bg_img, orig_bgr, regions)

    def run(
        self,
        image_path: str,
        output_dir: str = "outputs",
        generate_comparisons: bool = True,
        model_type: str = "strata_non_thinking"
    ) -> dict:
        """Runs complete 4-step automated pipeline with chosen AI model."""
        start_time = time.time()
        in_path = Path(image_path)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        original_img = Image.open(in_path)
        orig_bgr = cv2.imread(str(in_path))
        
        # Step 1: Dual OCR & Correction
        t0 = time.time()
        regions, ocr_meta = self.analyze(in_path, model_type=model_type)
        ocr_time = time.time() - t0
        
        # Step 2: Hybrid Inpainting
        t0 = time.time()
        inpainted_img = self.inpaint(original_img, regions)
        inpaint_time = time.time() - t0
        bg_save_path = out_path / "background_inpainted.png"
        inpainted_img.save(bg_save_path)
        
        # Step 3: Typography Style Transfer
        t0 = time.time()
        restored_img = self.render(inpainted_img, regions, orig_bgr)
        render_time = time.time() - t0
        
        restored_filename = f"{in_path.stem}_restored.png"
        final_save_path = out_path / restored_filename
        restored_img.save(final_save_path)
        
        # Step 4: Comparison Generation
        comparisons = []
        if generate_comparisons:
            for reg in regions:
                x, y, w, h = reg.bbox
                pad = 14
                crop_box = (
                    max(0, x - pad),
                    max(0, y - pad),
                    min(original_img.width, x + w + pad),
                    min(original_img.height, y + h + pad)
                )
                
                crop_orig = original_img.crop(crop_box)
                crop_rest = restored_img.crop(crop_box)
                
                cw, ch = crop_orig.size
                header_h = 28
                comp = Image.new("RGBA", (cw * 2 + 10, ch + header_h), (245, 245, 248, 255))
                draw = ImageDraw.Draw(comp)
                
                obs_line = reg.observed.splitlines()[0] if reg.observed else ""
                corr_line = reg.corrected.splitlines()[0] if reg.corrected else ""
                draw.text((10, 6), f"Before (Corrupted): {obs_line}", font=self.header_font, fill=(180, 20, 20, 255))
                draw.text((cw + 20, 6), f"After (Restored): {corr_line}", font=self.header_font, fill=(10, 130, 40, 255))
                
                comp.paste(crop_orig, (0, header_h))
                comp.paste(crop_rest, (cw + 10, header_h))
                
                comp_file = out_path / f"comparison_{reg.id}.png"
                comp.save(comp_file)
                comparisons.append({
                    "id": reg.id,
                    "observed": reg.observed,
                    "corrected": reg.corrected,
                    "bbox": list(reg.bbox),
                    "clean_bbox": list(reg.clean_bbox) if reg.clean_bbox else list(reg.bbox),
                    "comparison_path": str(comp_file)
                })
                
        total_time = time.time() - start_time
        summary = {
            "source": str(in_path),
            "output": str(final_save_path),
            "background_inpainted": str(bg_save_path),
            "regions_count": len(regions),
            "elapsed_seconds": {
                "ocr": round(ocr_time, 2),
                "inpaint": round(inpaint_time, 2),
                "typography_render": round(render_time, 2),
                "total": round(total_time, 2)
            },
            "regions": [r.to_dict() for r in regions],
            "comparisons": comparisons,
            "metadata": ocr_meta
        }
        
        report_path = out_path / "restoration_report.json"
        report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary
