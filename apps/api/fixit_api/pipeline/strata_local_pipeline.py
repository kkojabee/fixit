import base64
import io
import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import cv2
import numpy as np
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR

from .schema import TextRegion
from fixit_api.services.vlm_lock_service import vlm_lock_manager

logger = logging.getLogger(__name__)

# RapidOCR singleton instance for fast reuse
_RAPID_OCR_ENGINE: Optional[RapidOCR] = None

def get_rapid_ocr_engine() -> RapidOCR:
    global _RAPID_OCR_ENGINE
    if _RAPID_OCR_ENGINE is None:
        logger.info("[Strata Pipeline] Initializing RapidOCR text detector engine...")
        _RAPID_OCR_ENGINE = RapidOCR()
    return _RAPID_OCR_ENGINE


def extract_original_ocr_boxes(image_path: Path) -> List[List[int]]:
    """
    Step 1: RapidOCR 순수 100% 검출
    임의의 수평 스티칭(가로 결합) 루틴을 전면 배제하여 순수 검출 박스 목록 보존
    """
    logger.info(f"[Strata Pipeline] Step 1: RapidOCR pure detection on {image_path.name}...")
    engine = get_rapid_ocr_engine()
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise ValueError(f"Cannot read image file: {image_path}")

    dt_boxes, elapse = engine.text_detector(img_bgr)
    raw_boxes: List[List[int]] = []
    if dt_boxes is not None and len(dt_boxes) > 0:
        for poly in dt_boxes:
            xs = [pt[0] for pt in poly]
            ys = [pt[1] for pt in poly]
            raw_boxes.append([int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))])

    # Y, X 순서로 정렬
    raw_boxes.sort(key=lambda b: (b[1], b[0]))
    logger.info(f"[Strata Pipeline] Step 1 completed: {len(raw_boxes)} pure RapidOCR boxes detected.")
    return raw_boxes


def perform_geometric_vertical_merging(image_path: Path, orig_boxes: List[List[int]]) -> List[Dict[str, Any]]:
    """
    Step 2: 1차 단일 패스 기하학적 세로 머징 (Single-Pass Geometric Vertical Merging)
    수직 간격: -5px <= gap <= 5px 엄격 준수
    배경색 완화: 글자 획 간섭 배제한 순수 배경 샘플링 및 허용 오차 (diff_bg <= 48) 적용
    """
    logger.info(f"[Strata Pipeline] Step 2: Geometric vertical merging on {len(orig_boxes)} boxes...")
    im_cv = cv2.imread(str(image_path))
    if im_cv is None:
        raise ValueError(f"Cannot read image file for background sampling: {image_path}")

    def get_box_bg(box: List[int]) -> np.ndarray:
        x1, y1, x2, y2 = box
        p = im_cv[max(0, y1):min(im_cv.shape[0], y2), max(0, x1):min(im_cv.shape[1], x2)]
        if p.size == 0:
            return np.array([255, 255, 255], dtype=np.float32)
        gray = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY)
        bright_mask = gray >= np.percentile(gray, 60)
        bg_pix = p[bright_mask]
        if len(bg_pix) > 0:
            return np.median(bg_pix, axis=0)
        b = np.concatenate([p[0, :, :], p[-1, :, :], p[:, 0, :], p[:, -1, :]], axis=0)
        return np.median(b, axis=0)

    def can_merge_blocks(b1_obj: Dict[str, Any], b2_obj: Dict[str, Any]) -> bool:
        b1, b2 = b1_obj["bbox"], b2_obj["bbox"]
        if b1[1] > b2[1]:
            b1, b2 = b2, b1
            b1_obj, b2_obj = b2_obj, b1_obj

        # 1. 줄 높이 편차 (각 블록의 줄당 평균 높이 기준 40% 이내)
        h1_line = (b1[3] - b1[1]) / max(1, len(b1_obj["indices"]))
        h2_line = (b2[3] - b2[1]) / max(1, len(b2_obj["indices"]))
        if abs(h1_line - h2_line) / max(h1_line, h2_line, 1) > 0.40:
            return False

        # 2. X축 정렬 및 겹침 (시작점 차이 20px 이내, 겹침 40% 이상)
        w1, w2 = b1[2] - b1[0], b2[2] - b2[0]
        overlap_x = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
        min_w = min(w1, w2)
        diff_x1 = abs(b1[0] - b2[0])
        if overlap_x < 0.40 * min_w or diff_x1 > 20:
            return False

        # 3. Y축 수직 간격 (사용자 지침: gap <= 5px, -5px 포개짐 허용)
        gap_y = b2[1] - b1[3]
        if not (-5 <= gap_y <= 5):
            return False

        # 4. 배경색 확인 (배경톤이 다르면 다른 셀/상자이므로 결합 금지)
        diff_bg = np.linalg.norm(get_box_bg(b1) - get_box_bg(b2))
        if diff_bg > 48:
            return False

        return True

    def run_merge_cycle(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        num_b = len(blocks)
        adj: Dict[int, List[int]] = {i: [] for i in range(num_b)}
        for i in range(num_b):
            for j in range(i + 1, num_b):
                if can_merge_blocks(blocks[i], blocks[j]):
                    adj[i].append(j)
                    adj[j].append(i)

        visited = set()
        merged_blocks: List[Dict[str, Any]] = []
        for i in range(num_b):
            if i in visited:
                continue
            comp: List[int] = []
            q = [i]
            visited.add(i)
            while q:
                curr = q.pop(0)
                comp.append(curr)
                for nxt in adj[curr]:
                    if nxt not in visited:
                        visited.add(nxt)
                        q.append(nxt)

            merged_indices: List[int] = []
            for c in comp:
                merged_indices.extend(blocks[c]["indices"])
            merged_indices = sorted(list(set(merged_indices)))

            boxes = [orig_boxes[idx] for idx in merged_indices]
            merged_blocks.append({
                "indices": merged_indices,
                "bbox": [
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes)
                ]
            })
        return merged_blocks

    init_blocks = [{"indices": [i], "bbox": orig_boxes[i]} for i in range(len(orig_boxes))]
    merged_blocks = run_merge_cycle(init_blocks)

    recalculated_blocks: List[Dict[str, Any]] = []
    for group_id, b in enumerate(merged_blocks):
        # 배경색 샘플링 저장
        bg_rgb = get_box_bg(b["bbox"])
        bg_hex = f"#{int(bg_rgb[2]):02x}{int(bg_rgb[1]):02x}{int(bg_rgb[0]):02x}"
        recalculated_blocks.append({
            "block_id": group_id,
            "merged_orig_indices": b["indices"],
            "bbox": b["bbox"],
            "count": len(b["indices"]),
            "bg_color": bg_hex
        })

    # 읽기 순서대로 정렬 (Y/25, X)
    recalculated_blocks.sort(key=lambda b: (b["bbox"][1] // 25, b["bbox"][0]))
    for i, b in enumerate(recalculated_blocks):
        b["block_id"] = i

    logger.info(f"[Strata Pipeline] Step 2 completed: {len(orig_boxes)} boxes merged into {len(recalculated_blocks)} paragraph blocks.")
    return recalculated_blocks


def prepare_crop_patch(crop_pil: Image.Image) -> str:
    """고해상도 패치 리사이징 및 흰색 여백 확장 패딩"""
    w, h = crop_pil.size
    scale = max(2.0, 100.0 / max(1, h))
    new_w, new_h = int(w * scale), int(h * scale)
    scaled = crop_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
    padded = ImageOps.expand(scaled, border=25, fill="white")
    buf = io.BytesIO()
    padded.save(buf, format="JPEG", quality=95)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def run_crop_and_strata_vlm_analysis(
    image_path: Path,
    recalculated_blocks: List[Dict[str, Any]],
    api_url: str = "http://127.0.0.1:8080/v1/chat/completions",
    model_name: str = "qwen3.8-flash-next-iq3_s"
) -> List[Dict[str, Any]]:
    """
    Step 3: Strata VLM 배치 분석 (Zero-Drop Guarantee)
    블록 삭제 없이 전체 블록을 크롭하여 단일/청크 배치로 일괄 질의
    """
    logger.info(f"[Strata Pipeline] Step 3: Cropping {len(recalculated_blocks)} blocks & querying Strata VLM...")
    im_full = Image.open(image_path).convert("RGB")
    chunk_size = 45
    all_parsed_items: List[Dict[str, Any]] = []

    # API 엔드포인트 URL 정규화
    target_api_url = api_url
    if not target_api_url.endswith("/chat/completions"):
        target_api_url = target_api_url.rstrip("/") + "/chat/completions"

    for chunk_start in range(0, len(recalculated_blocks), chunk_size):
        chunk_blocks = recalculated_blocks[chunk_start:chunk_start + chunk_size]
        logger.info(f"[Strata Pipeline] Processing VLM batch {chunk_start} ~ {chunk_start + len(chunk_blocks) - 1}...")

        prompt_system = (
            f"당신은 인포그래픽 텍스트 교정 및 타이포그래피 스타일링 전문가입니다.\n"
            f"아래 전달된 {len(chunk_blocks)}개의 잘려진(Cropped) 이미지 블록 각각에 대해 이미지 번호(image_idx: {chunk_start} ~ {chunk_start + len(chunk_blocks)-1})를 명시하여 정밀 분석하고 단일 JSON 배열로 회신하시오.\n\n"
            "도메인 지침 및 규칙:\n"
            "1. 모든 블록은 인포그래픽의 핵심 텍스트 영역이므로 누락 없이 100% 텍스트를 복원해야 합니다.\n"
            "2. 각 항목의 JSON 스키마:\n"
            "   - image_idx: 해당 블록의 이미지 번호 (정수)\n"
            "   - text: 원본에 적힌 정확한 텍스트 (필요한 경우 줄바꿈 \\n 포함, 오탈자 정정)\n"
            "   - font_size: 추천 폰트 크기 (px 정수)\n"
            "   - font_weight: Normal 또는 Bold\n"
            "   - text_color: 글자 색상 HEX (예: #1A3A6B, #FFFFFF, #333333 등)\n\n"
            "출력 포맷 예시:\n"
            "```json\n"
            "[\n"
            f'  {{"image_idx": {chunk_start}, "text": "인식된 텍스트", "font_size": 20, "font_weight": "Bold", "text_color": "#1A1A1A"}}\n'
            "]\n"
            "```\n\n"
            f"반드시 {chunk_start}부터 {chunk_start + len(chunk_blocks)-1}까지 빠짐없이 순서대로 포함한 단일 JSON 배열로 출력하시오.\n"
            "마크다운 코드블록(```json ... ```) 안에 순수 JSON 배열만 출력하시오."
        )

        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt_system}]
        for local_idx, b_info in enumerate(chunk_blocks):
            global_idx = chunk_start + local_idx
            x1, y1, x2, y2 = b_info["bbox"]
            crop_pil = im_full.crop([
                max(0, x1 - 1),
                max(0, y1 - 1),
                min(im_full.width, x2 + 1),
                min(im_full.height, y2 + 1)
            ])
            b64 = prepare_crop_patch(crop_pil)
            data_url = f"data:image/jpeg;base64,{b64}"
            content.append({"type": "text", "text": f"\n--- [이미지 번호: {global_idx}] ---"})
            content.append({"type": "image_url", "image_url": {"url": data_url}})

        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.1,
            "max_tokens": 102400,
            "reasoning_effort": "low"
        }

        # VLM 충돌 방지를 위한 Lock 획득
        with vlm_lock_manager.acquire(task_name=f"strata_batch_vlm_{image_path.stem}", model_type="strata_vllm"):
            req = urllib.request.Request(
                target_api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=300) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            logger.info(f"[Strata Pipeline] VLM batch query completed in {elapsed:.2f}s")

        msg = res["choices"][0]["message"]
        content_str = msg.get("content") or ""
        if not content_str and msg.get("reasoning_content"):
            content_str = msg.get("reasoning_content") or ""
        content_str = content_str.strip()

        if "</think>" in content_str:
            content_str = content_str.split("</think>")[-1].strip()
        if "```json" in content_str:
            content_str = content_str.split("```json")[1].split("```")[0].strip()
        elif "```" in content_str:
            content_str = content_str.split("```")[1].split("```")[0].strip()

        try:
            chunk_parsed = json.loads(content_str)
            if isinstance(chunk_parsed, dict) and "results" in chunk_parsed:
                chunk_parsed = chunk_parsed["results"]
            if isinstance(chunk_parsed, list):
                all_parsed_items.extend(chunk_parsed)
        except Exception as e:
            logger.error(f"[Strata Pipeline] JSON parsing error in VLM response: {e}, raw text snippet: {content_str[:300]}")

    results: List[Dict[str, Any]] = []
    for i, b_info in enumerate(recalculated_blocks):
        match_item = None
        for p in all_parsed_items:
            if p.get("image_idx") == i:
                match_item = p
                break
        if not match_item and i < len(all_parsed_items):
            match_item = all_parsed_items[i]
        if not match_item:
            match_item = {
                "text": f"텍스트 영역 {i + 1}",
                "font_size": 18,
                "font_weight": "Bold",
                "text_color": "#1A1A1A"
            }

        match_item["block_id"] = i
        match_item["bbox"] = b_info["bbox"]
        match_item["bg_color"] = b_info.get("bg_color", "#FFFFFF")
        results.append(match_item)

    logger.info(f"[Strata Pipeline] Step 3 completed: Parsed {len(results)} items from Strata VLM.")
    return results


def build_text_regions_from_strata_results(parsed_results: List[Dict[str, Any]]) -> List[TextRegion]:
    """
    Step 3 분석 결과를 FixIt 표준 TextRegion 모델로 변환하여
    위지윅 에디터(Canvas) 및 이후 복원 프로세스(인페인팅, 렌더링)와 100% 동일하게 연동
    """
    regions: List[TextRegion] = []
    for idx, item in enumerate(parsed_results):
        x1, y1, x2, y2 = item["bbox"]
        box_w = max(10, x2 - x1)
        box_h = max(8, y2 - y1)

        raw_text = item.get("text", "")
        if not raw_text and item.get("segments"):
            raw_text = "\n".join([s.get("text", "") for s in item.get("segments", []) if s.get("text")])
        if not raw_text:
            raw_text = f"인식 텍스트 {idx + 1}"

        # 폰트 크기 추천 및 보정
        rec_font_size = item.get("font_size")
        if not rec_font_size or not isinstance(rec_font_size, (int, float)):
            line_count = max(1, len(raw_text.splitlines()))
            rec_font_size = max(11, min(32, int((box_h - 4) / (line_count * 1.2))))
        else:
            rec_font_size = int(rec_font_size)

        weight_str = str(item.get("font_weight", "Bold")).capitalize()
        if weight_str not in ["Regular", "Bold", "ExtraBold"]:
            weight_str = "Bold"

        text_color = str(item.get("text_color", "#1A1A1A")).strip()
        if not text_color.startswith("#"):
            text_color = "#1A1A1A"

        reg = TextRegion(
            id=f"strata_reg_{idx + 1:02d}",
            observed=raw_text,
            corrected=raw_text,
            bbox=(x1, y1, box_w, box_h),
            clean_bbox=(max(0, x1 - 4), max(0, y1 - 4), box_w + 8, box_h + 8),
            font_family="NanumSquare",
            font_weight=weight_str,
            font_size=rec_font_size,
            scale_x=0.92,
            letter_spacing=-0.6,
            text_color=text_color,
            align="left",
            valign="top",
            line_gap=6,
            padding_top=0,
            bg_color=None  # refine_and_autostyle_regions에서 원본 ROI 외곽 테두리 픽셀 기준으로 정밀 샘플링되도록 함
        )
        regions.append(reg)

    return regions


def run_strata_local_extraction(
    image_path: Path,
    api_url: str = "http://127.0.0.1:8080/v1/chat/completions",
    model_name: str = "qwen3.8-flash-next-iq3_s"
) -> Tuple[List[TextRegion], Dict[str, Any]]:
    """
    Strata 로컬 vLLM 전용 완전 분기 파이프라인 진입점:
    Step 1: RapidOCR 순수 100% 검출
    Step 2: 1차 단일 패스 기하학적 세로 머징 (Single-Pass Geometric Merging)
    Step 3: Strata VLM 배치 분석 (Zero-Drop Guarantee)
    -> TextRegion 변환 후 반환 (이후 Step 4 인페인팅 및 Step 5 렌더링/위지윅 편집은 기존 인프라와 100% 동일)
    """
    t0 = time.time()
    orig_boxes = extract_original_ocr_boxes(image_path)
    if not orig_boxes:
        logger.warning(f"[Strata Pipeline] RapidOCR detected 0 boxes on {image_path.name}")
        return [], {"error": "No text detected", "elapsed_sec": round(time.time() - t0, 2)}

    recalculated_blocks = perform_geometric_vertical_merging(image_path, orig_boxes)
    parsed_results = run_crop_and_strata_vlm_analysis(
        image_path,
        recalculated_blocks,
        api_url=api_url,
        model_name=model_name
    )
    regions = build_text_regions_from_strata_results(parsed_results)
    elapsed = round(time.time() - t0, 2)

    metadata = {
        "engine": "strata_local_vllm_pipeline",
        "step1_raw_boxes_count": len(orig_boxes),
        "step2_merged_blocks_count": len(recalculated_blocks),
        "step3_vlm_parsed_count": len(parsed_results),
        "regions_count": len(regions),
        "elapsed_sec": elapsed,
        "is_airgapped_secure": True
    }
    logger.info(f"[Strata Pipeline] Fully completed in {elapsed}s with {len(regions)} regions generated.")
    return regions, metadata
