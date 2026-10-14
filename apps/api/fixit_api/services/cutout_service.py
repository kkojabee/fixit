import io
import cv2
import numpy as np
from PIL import Image

class CutoutService:
    @staticmethod
    def extract_foreground_by_bbox(img_np: np.ndarray, bbox: list) -> np.ndarray:
        """
        GrabCut based fast foreground segmentation for given bbox [ymin, xmin, ymax, xmax].
        Returns RGBA image (H, W, 4) with transparent background.
        """
        h, w = img_np.shape[:2]
        ymin, xmin, ymax, xmax = bbox
        
        # Ensure coordinates are bounded
        xmin, ymin = max(0, int(xmin)), max(0, int(ymin))
        xmax, ymax = min(w, int(xmax)), min(h, int(ymax))
        
        rect = (xmin, ymin, max(1, xmax - xmin), max(1, ymax - ymin))
        
        mask = np.zeros((h, w), np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        
        try:
            cv2.grabCut(img_np, mask, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
            alpha = np.where((mask == 2) | (mask == 0), 0, 255).astype(np.uint8)
        except Exception:
            # Fallback simple rectangle alpha
            alpha = np.zeros((h, w), dtype=np.uint8)
            alpha[ymin:ymax, xmin:xmax] = 255
            
        rgba = cv2.cvtColor(img_np, cv2.COLOR_RGB2RGBA)
        rgba[:, :, 3] = alpha
        return rgba

    @staticmethod
    def extract_foreground_by_point(img_np: np.ndarray, click_x: int, click_y: int, radius: int = 150) -> np.ndarray:
        """Segment foreground around clicked point (click_x, click_y)."""
        h, w = img_np.shape[:2]
        ymin = max(0, click_y - radius)
        ymax = min(h, click_y + radius)
        xmin = max(0, click_x - radius)
        xmax = min(w, click_x + radius)
        return CutoutService.extract_foreground_by_bbox(img_np, [ymin, xmin, ymax, xmax])
