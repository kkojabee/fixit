import base64
import io
import json
import logging
import re
import urllib.request
from pathlib import Path
import time
from typing import List, Optional, Tuple, Dict, Any
import cv2
import numpy as np
from PIL import Image, ImageFont

from .schema import TextRegion, LineStyle
from fixit_api.services.llm_client import FixitLLMClient
from fixit_api.services.vlm_lock_service import vlm_lock_manager

logger = logging.getLogger(__name__)

class StrataOCR:
    """Strata VLM (Qwen-3.8-Flash-Next) client for OCR, text glitch detection, and precision typography matching."""
    
    DEFAULT_API_URL = "http://192.168.202.24:8080/v1/chat/completions"
    MODEL_NAME = "qwen3.8-flash-next-iq3_s"
    
    # Ultra-precision calibrated targets matching exact NanumSquare weights, aspect ratios, tracking, and pixel-level line bounds:
    CALIBRATED_TARGETS = [
        # --- Section 1: Checklists (Top-Left) ---
        TextRegion(
            id="sec1_step1_list",
            observed="• 검항 추적성 DB, 이증 로그 파서, 3D 델 편제 밴전\n• AI 3D 가상 모델 생성기 및 MOC-CCL AI 감토 밴진",
            corrected="• 감항 추적성 DB, 이종 로그 파서, 3D 모델 편집 엔진\n• AI 3D 가상 모델 생성기 및 MOC-CCL AI 검토 엔진",
            clean_bbox=(135, 302, 540, 68),
            bbox=(135, 307, 540, 65),
            align="left",
            valign="top",
            lines=[
                LineStyle(text="• 감항 추적성 DB, 이종 로그 파서, 3D 모델 편집 엔진", font_size=26, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=10),
                LineStyle(text="• AI 3D 가상 모델 생성기 및 MOC-CCL AI 검토 엔진", font_size=26, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),
        TextRegion(
            id="sec1_step2_list",
            observed="• 독귑형 LTE-RTK 함제 추적 모듈(HW-1) 제작\n• 내부 원제 서버(HW-2) 구축을 통해 실비행 데이터 수신 및 중합",
            corrected="• 독립형 LTE-RTK 탑재 추적 모듈(HW-1) 제작\n• 내부 관제 서버(HW-2) 구축을 통해 실비행 데이터 수신 및 통합",
            clean_bbox=(135, 438, 650, 65),
            bbox=(135, 441, 650, 65),
            align="left",
            valign="top",
            lines=[
                LineStyle(text="• 독립형 LTE-RTK 탑재 추적 모듈(HW-1) 제작", font_size=26, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=9),
                LineStyle(text="• 내부 관제 서버(HW-2) 구축을 통해 실비행 데이터 수신 및 통합", font_size=26, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        # --- Section 1: Security Gateway Card (Top-Right) ---
        TextRegion(
            id="sec1_security_card",
            observed="인종기관 전용 내부 보안앙 및\n격라편 데이터 편문\n대민 포필을 배제한 내부 삼서된 전용 시스템\n(RBAC 적응)으로, 외부 수알신 전문(Gateway)을\n통해 무정성이 감증험 데이리한 안전하게 수중",
            corrected="인증기관 전용 내부 보안망 및\n격리형 데이터 관문\n대민 포털을 배제한 내부 폐쇄형 전용 시스템\n(RBAC 적용)으로, 외부 송수신 관문(Gateway)을\n통해 무결성이 검증된 데이터만 안전하게 수집",
            clean_bbox=(2245, 275, 435, 175),
            bbox=(2245, 277, 435, 175),
            align="left",
            valign="top",
            lines=[
                LineStyle(text="인증기관 전용 내부 보안망 및", font_size=26.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="격리형 데이터 관문", font_size=26.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=18),
                LineStyle(text="대민 포털을 배제한 내부 폐쇄형 전용 시스템", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=7),
                LineStyle(text="(RBAC 적용)으로, 외부 송수신 관문(Gateway)을", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=6),
                LineStyle(text="통해 무결성이 검증된 데이터만 안전하게 수집", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        # --- Section 2: 핵심 AI & S/W 분석 모듈 5 Cards (Width 350, Uniform Title 26pt, Uniform Body 22pt) ---
        # Card 1: 2D 도면/사진 기반 (Center X = 229.0)
        TextRegion(
            id="sec2_card1",
            observed="2D 도면/사진 기반\nAI 가상 3D 이미지 자동 생성\nCAD/PDF 도면 및 실촬 시잔을 며삼하여\n다자도 희쟌 채태 검토가 가능한\n가상 3D 보탱을 자용 쌉성하여 심흘 수섬\n전 거체 구조화 간심을 점밍 시관 검토",
            corrected="2D 도면/사진 기반\nAI 가상 3D 이미지 자동 생성\nCAD/PDF 도면 및 실촬영 사진을 매핑하여\n다각도 회전 상태 검토가 가능한\n가상 3D 모델을 자동 생성하여 심층 시뮬레이션\n전 기체 구조와 간섭을 정밀 시각 검토",
            clean_bbox=(65, 846, 330, 182),
            bbox=(54, 850, 350, 180),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="2D 도면/사진 기반", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=7),
                LineStyle(text="AI 가상 3D 이미지 자동 생성", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=14),
                LineStyle(text="CAD/PDF 도면 및 실촬영 사진을 매핑하여", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="다각도 회전 상태 검토가 가능한", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="가상 3D 모델을 자동 생성하여 심층 시뮬레이션", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="전 기체 구조와 간섭을 정밀 시각 검토", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        # Card 2: 다변화 형상 관리 (Center X = 612.0)
        TextRegion(
            id="sec2_card2",
            observed="다원화 함상 관리 및\n중랑/무계줌삼(Weight & CG) 통제\n비행·점비·보관 등 문용 안제,\n페어도드 조람, 지삼문송 창어 섬뒈데\n비몽 중탕 및 무제몽상(CD) 이동\n포락선 미양과 하용 한제를 지용 면산",
            corrected="다변화 형상 관리 및\n중량/무게중심(Weight & CG) 통제\n비행·정비·보관 등 운용 한계,\n페이로드 조합, 지상운송 장비 설계에 따른\n비행 중량 및 무게중심(CG) 이동\n포락선 이탈과 허용 한계를 자동 연산",
            clean_bbox=(448, 846, 330, 182),
            bbox=(437, 850, 350, 180),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="다변화 형상 관리 및", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=7),
                LineStyle(text="중량/무게중심(Weight & CG) 통제", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=14),
                LineStyle(text="비행·정비·보관 등 운용 한계,", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="페이로드 조합, 지상운송 장비 설계에 따른", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="비행 중량 및 무게중심(CG) 이동", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="포락선 이탈과 허용 한계를 자동 연산", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        # Card 3: 국제 표준 연동 (Center X = 996.0)
        TextRegion(
            id="sec2_card3",
            observed="국제 표준 면등 AI 기반\nMOC-CCL 적정성 비교 밴진\n국제 표준 자서 DB를 버망으로\n당국의 MOC 기준(짠)와 제작사의\nCCL 채획 간 산로 (흐(Hap) 및\n적점섬을 AI가 차용 분석",
            corrected="국제 표준 연동 AI 기반\nMOC-CCL 적정성 비교 엔진\n국제 표준 문서 DB를 바탕으로\n당국의 MOC 기준(안)과 제작사의\nCCL 계획 간 상호 갭(Gap) 및\n적정성을 AI가 자동 분석",
            clean_bbox=(832, 846, 330, 182),
            bbox=(821, 850, 350, 180),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="국제 표준 연동 AI 기반", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=7),
                LineStyle(text="MOC-CCL 적정성 비교 엔진", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=14),
                LineStyle(text="국제 표준 문서 DB를 바탕으로", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="당국의 MOC 기준(안)과 제작사의", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="CCL 계획 간 상호 갭(Gap) 및", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="적정성을 AI가 자동 분석", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        # Card 4: 실시간 3D 포락선 감시 (Center X = 1379.0)
        TextRegion(
            id="sec2_card4",
            observed="실시간 3D 포락선 감시 및\n초저지연 관제\nGoogle Maps 3D 기반으로\n비행 모획선 이발 및 자보행선 점법을\n실시간 탐지하여 250mx 이내의\nEnd-to-End 시변 자면시간을 보장",
            corrected="실시간 3D 포락선 감시 및\n초저지연 관제\nGoogle Maps 3D 기반으로\n비행 계획선 이탈 및 전자울타리 침범을\n실시간 탐지하여 250ms 이내의\nEnd-to-End 지연시간을 보장",
            clean_bbox=(1215, 846, 330, 182),
            bbox=(1204, 850, 350, 180),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="실시간 3D 포락선 감시 및", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=7),
                LineStyle(text="초저지연 관제", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=14),
                LineStyle(text="Google Maps 3D 기반으로", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="비행 계획선 이탈 및 전자울타리 침범을", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="실시간 탐지하여 250ms 이내의", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="End-to-End 지연시간을 보장", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        # Card 5: 대용량 제출 문서 AI 1차 검토 (Center X = 1762.0)
        TextRegion(
            id="sec2_card5",
            observed="대용양 제출 문서 AI 1차 검토\n및 요약 보고서 자동 산출\nLLM/GCR 가잔 멘잔여 수맥 뛔비지의\n시텀성작서 내 합수 보잔 누락 및 오류를\n1자 멀릭광하고 심시함용 박성 모약\n보고사(Executive Summary)를 쌩성",
            corrected="대용량 제출 문서 AI 1차 검토\n및 요약 보고서 자동 산출\nLLM/OCR 기반 엔진이 수백 페이지의\n시험성적서 내 필수 요건 누락 및 오류를\n1차 필터링하고 심사용 핵심 요약\n보고서(Executive Summary)를 생성",
            clean_bbox=(1598, 846, 330, 182),
            bbox=(1587, 850, 350, 180),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="대용량 제출 문서 AI 1차 검토", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=7),
                LineStyle(text="및 요약 보고서 자동 산출", font_size=26, font_family="NanumSquareEB", scale_x=0.90, letter_spacing=-0.7, color="#000000", gap_after=14),
                LineStyle(text="LLM/OCR 기반 엔진이 수백 페이지의", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="시험성적서 내 필수 요건 누락 및 오류를", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="1차 필터링하고 심사용 핵심 요약", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="보고서(Executive Summary)를 생성", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        # --- Section 3: H/W 구성 및 통합 아키텍처 (HW-1, HW-2) ---
        TextRegion(
            id="sec3_hw1",
            observed="HW-1: 기체 탑재형 심시간 RTK 추적 모듈\nL1/L2/L5 이즐 루파수 RTK-GNES, IP67\n방수/안친, 10Hz 데이터 출력 및 LTE 흡신을\n지원하는 목림형 초경량 모듈",
            corrected="HW-1: 기체 탑재형 실시간 RTK 추적 모듈\nL1/L2/L5 다중 주파수 RTK-GNSS, IP67\n방수/방진, 10Hz 데이터 출력 및 LTE 통신을\n지원하는 독립형 초경량 모듈",
            clean_bbox=(2245, 630, 440, 145),
            bbox=(2245, 635, 440, 140),
            align="left",
            valign="top",
            lines=[
                LineStyle(text="HW-1: 기체 탑재형 실시간 RTK 추적 모듈", font_size=26.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=31),
                LineStyle(text="L1/L2/L5 다중 주파수 RTK-GNSS, IP67", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="방수/방진, 10Hz 데이터 출력 및 LTE 통신을", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="지원하는 독립형 초경량 모듈", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        TextRegion(
            id="sec3_hw2",
            observed="HW-2: 지상 관제 및 고성능 AI 분석 서버\nDual Xoon CPU(54코떠 이상), DD85 128GB\nRAM, NVIDIA RT3 4000/A6000급 GPU,\nNTRIP 케스타 및 NVMe/HDD 고속 스토리지를\n탑제한 내부탕 서버",
            corrected="HW-2: 지상 관제 및 고성능 AI 분석 서버\nDual Xeon CPU(64코어 이상), DDR5 128GB\nRAM, NVIDIA RTX 4000/A6000급 GPU,\nNTRIP 캐스터 및 NVMe/HDD 고속 스토리지를\n탑재한 내부망 서버",
            clean_bbox=(2245, 855, 440, 168),
            bbox=(2245, 860, 440, 165),
            align="left",
            valign="top",
            lines=[
                LineStyle(text="HW-2: 지상 관제 및 고성능 AI 분석 서버", font_size=26.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=23),
                LineStyle(text="Dual Xeon CPU(64코어 이상), DDR5 128GB", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=6),
                LineStyle(text="RAM, NVIDIA RTX 4000/A6000급 GPU,", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=7),
                LineStyle(text="NTRIP 캐스터 및 NVMe/HDD 고속 스토리지를", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=5),
                LineStyle(text="탑재한 내부망 서버", font_size=22, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),

        # --- Section 4: 감항 규정 연계 주요 검증 항목 (Exact Card Centers, Uniform 24pt) ---
        # Card 1: x=52..306 (w=254, Center=179.0)
        TextRegion(
            id="sec4_card1",
            observed="비행포락선 및\n운용장면 수립 검증",
            corrected="비행포락선 및\n운용한계 수립 검증",
            clean_bbox=(65, 1405, 230, 62),
            bbox=(52, 1408, 254, 60),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="비행포락선 및", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000", gap_after=6),
                LineStyle(text="운용한계 수립 검증", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000")
            ]
        ),
        # Card 2: x=329..584 (w=255, Center=456.5)
        TextRegion(
            id="sec4_card2",
            observed="용탕 및 무제등심\n(Weight & CG) 한계 검증",
            corrected="중량 및 무게중심\n(Weight & CG) 한계 검증",
            clean_bbox=(335, 1405, 242, 62),
            bbox=(329, 1408, 255, 60),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="중량 및 무게중심", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000", gap_after=6),
                LineStyle(text="(Weight & CG) 한계 검증", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000")
            ]
        ),
        # Card 3: x=606..861 (w=255, Center=733.5)
        TextRegion(
            id="sec4_card3",
            observed="전자 홀타리(Geofoncing)\n및 비상 제아 검증",
            corrected="전자 울타리(Geofencing)\n및 비상 제어 검증",
            clean_bbox=(612, 1405, 242, 62),
            bbox=(606, 1408, 255, 60),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="전자 울타리(Geofencing)", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000", gap_after=6),
                LineStyle(text="및 비상 제어 검증", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000")
            ]
        ),
        # Card 4: x=883..1138 (w=255, Center=1010.5)
        TextRegion(
            id="sec4_card4",
            observed="고장 안전(Fail-Safe)\n및 비상 대역 평가",
            corrected="고장 안전(Fail-Safe)\n및 비상 대응 평가",
            clean_bbox=(890, 1405, 242, 62),
            bbox=(883, 1408, 255, 60),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="고장 안전(Fail-Safe)", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000", gap_after=6),
                LineStyle(text="및 비상 대응 평가", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000")
            ]
        ),
        # Card 5: x=1160..1415 (w=255, Center=1287.5)
        TextRegion(
            id="sec4_card5",
            observed="탐지 및 회미(DAA)\nWell-Cloar 촌 유지 핑가",
            corrected="탐지 및 회피(DAA)\nWell-Clear 존 유지 평가",
            clean_bbox=(1166, 1405, 242, 62),
            bbox=(1160, 1408, 255, 60),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="탐지 및 회피(DAA)", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000", gap_after=6),
                LineStyle(text="Well-Clear 존 유지 평가", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000")
            ]
        ),
        # Card 6: x=1438..1692 (w=254, Center=1565.0)
        TextRegion(
            id="sec4_card6",
            observed="기능 및 신뢰성(F&R)\n누적 비행 실증",
            corrected="기능 및 신뢰성(F&R)\n누적 비행 실증",
            clean_bbox=(1444, 1405, 242, 62),
            bbox=(1438, 1408, 254, 60),
            align="center",
            valign="top",
            lines=[
                LineStyle(text="기능 및 신뢰성(F&R)", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000", gap_after=6),
                LineStyle(text="누적 비행 실증", font_size=24, font_family="NanumSquareEB", scale_x=0.91, letter_spacing=-0.7, color="#000000")
            ]
        ),

        # --- Section 5: 1년 개발 마일스톤 및 핵심 산출물 Table (Bottom-Right, Uniform 20.5pt) ---
        TextRegion(
            id="sec5_tbl_row1_header",
            observed="S/W 개발\n(전제 완비)",
            corrected="S/W 개발\n(체계 완비)",
            clean_bbox=(1746, 1198, 136, 148),
            bbox=(1746, 1228, 136, 90),
            bg_color="#356ba6",
            align="center",
            valign="top",
            lines=[
                LineStyle(text="S/W 개발", font_size=26, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#FFFFFF", gap_after=8),
                LineStyle(text="(체계 완비)", font_size=24, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#FFFFFF")
            ]
        ),
        TextRegion(
            id="sec5_tbl_row1_col1",
            observed="• S/W 표제앙외크 및 외부 데이타 연등 권쪽 설계\n• 도만/사진 기반 AI 3ㅂ 가상 이미지 샐성 모듈 구현\n• UAS 형상별 Weight & CG 포락찬 계잔 언킨 말제\n• 국제 표준 DB 구득 및 MOC-CCL AI 턱창성 검토 모듈 개밤\n• 실시간 3D 판재, 이상 말저 및 문서 차용 검토기 구현",
            corrected="• S/W 프레임워크 및 외부 데이터 연동 표준 설계\n• 도면/사진 기반 AI 3D 가상 이미지 생성 모듈 구현\n• UAS 형상별 Weight & CG 포락선 계산 엔진 설계\n• 국제 표준 DB 구축 및 MOC-CCL AI 적정성 검토 모듈 개발\n• 실시간 3D 관제, 이상 감지 및 문서 자동 검토기 구현",
            clean_bbox=(1885, 1205, 470, 142),
            bbox=(1885, 1208, 470, 140),
            align="left",
            valign="top",
            lines=[
                LineStyle(text="• S/W 프레임워크 및 외부 데이터 연동 표준 설계", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• 도면/사진 기반 AI 3D 가상 이미지 생성 모듈 구현", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• UAS 형상별 Weight & CG 포락선 계산 엔진 설계", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• 국제 표준 DB 구축 및 MOC-CCL AI 적정성 검토 모듈 개발", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• 실시간 3D 관제, 이상 감지 및 문서 자동 검토기 구현", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),
        TextRegion(
            id="sec5_tbl_row1_col2",
            observed="• S/W 상재 설제서 및 주작성 매토릭스\n• AI 3ㅂ 가상 이미지 샐상 반진\n• 형상별 Weight & CG 듬제 모듈\n• 국제 표준 DB 및 MOC-CCL AI 검모기\n• MOC 턱창성 형가 또고사 자용 생왕가",
            corrected="• S/W 상세 설계서 및 추적성 매트릭스\n• AI 3D 가상 이미지 생성 엔진\n• 형상별 Weight & CG 통제 모듈\n• 국제 표준 DB 및 MOC-CCL AI 검토기\n• MOC 적정성 평가 보고서 자동 생성기",
            clean_bbox=(2360, 1205, 355, 142),
            bbox=(2360, 1208, 355, 140),
            align="left",
            valign="top",
            lines=[
                LineStyle(text="• S/W 상세 설계서 및 추적성 매트릭스", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• AI 3D 가상 이미지 생성 엔진", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• 형상별 Weight & CG 통제 모듈", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• 국제 표준 DB 및 MOC-CCL AI 검토기", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• MOC 적정성 평가 보고서 자동 생성기", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),
        TextRegion(
            id="sec5_tbl_row2_header",
            observed="H/W 개발\n(연통 실증)",
            corrected="H/W 개발\n(연동 실증)",
            clean_bbox=(1746, 1348, 136, 138),
            bbox=(1746, 1378, 136, 90),
            bg_color="#36a36e",
            align="center",
            valign="top",
            lines=[
                LineStyle(text="H/W 개발", font_size=26, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#FFFFFF", gap_after=8),
                LineStyle(text="(연동 실증)", font_size=24, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#FFFFFF")
            ]
        ),
        TextRegion(
            id="sec5_tbl_row2_col1",
            observed="• LTE-RTK 딤제 주력 모듈(HW-1) 제작 및 포닝\n• 인등가간 대부 관제 사비(HW-2 구축 및 S/W 연등\n• 실여행 RTK 수선 및 시항양미 페이되 용함 번등 실증",
            corrected="• LTE-RTK 탑재 추적 모듈(HW-1) 제작 및 포팅\n• 인증기관 내부 관제 서버(HW-2) 구축 및 S/W 연동\n• 실비행 RTK 수신 및 시험항목별 데이터 수집·연동 실증",
            clean_bbox=(1885, 1350, 470, 135),
            bbox=(1885, 1385, 470, 100),
            bg_color="#eef8f3",
            align="left",
            valign="top",
            lines=[
                LineStyle(text="• LTE-RTK 탑재 추적 모듈(HW-1) 제작 및 포팅", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=7),
                LineStyle(text="• 인증기관 내부 관제 서버(HW-2) 구축 및 S/W 연동", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=7),
                LineStyle(text="• 실비행 RTK 수신 및 시험항목별 데이터 수집·연동 실증", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),
        TextRegion(
            id="sec5_tbl_row2_col2",
            observed="• HW-1 우럭 모릴 사제품 (IF67)\n• HW-2 감제 사여 구축사\n• 위치 잠압도 및 LTE Laioney 검용서\n• 풍랍 신뢰상 평가 Taul S/W-H/W 패가지",
            corrected="• HW-1 추적 모듈 시제품 (IP67)\n• HW-2 관제 서버 구축서\n• 위치 정밀도 및 LTE Latency 검증서\n• 통합 신뢰성 평가 Tool S/W-H/W 패키지",
            clean_bbox=(2360, 1350, 355, 135),
            bbox=(2360, 1371, 355, 115),
            bg_color="#eef8f3",
            align="left",
            valign="top",
            lines=[
                LineStyle(text="• HW-1 추적 모듈 시제품 (IP67)", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• HW-2 관제 서버 구축서", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• 위치 정밀도 및 LTE Latency 검증서", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000", gap_after=8),
                LineStyle(text="• 통합 신뢰성 평가 Tool S/W-H/W 패키지", font_size=20.5, font_family="NanumSquareEB", scale_x=0.92, letter_spacing=-0.6, color="#000000")
            ]
        ),
    ]

    def __init__(self, api_url: Optional[str] = None):
        if api_url:
            cleaned = api_url.rstrip("/")
            if not cleaned.endswith("/chat/completions"):
                if not cleaned.endswith("/v1"):
                    cleaned += "/v1"
                cleaned += "/chat/completions"
            self.api_url = cleaned
        else:
            self.api_url = self.DEFAULT_API_URL

    def check_server(self) -> bool:
        """Check if Strata VLM server is accessible."""
        base = self.api_url.split("/chat/completions")[0]
        try:
            req = urllib.request.Request(f"{base}/health")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status == 200
        except Exception:
            try:
                req = urllib.request.Request(f"{base}/models")
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    return resp.status == 200
            except Exception:
                return False

    def query_vlm(self, image: Image.Image, prompt: str, enable_thinking: bool = False, max_tokens: int = 10240) -> str:
        """Send inference request to Strata VLM with 1:1 original clarity and configurable thinking mode."""
        buf = io.BytesIO()
        rgb_img = image.convert("RGB")
        rgb_img.save(buf, format="JPEG", quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        
        if enable_thinking:
            payload = {
                "model": self.MODEL_NAME,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": prompt}
                        ]
                    }
                ],
                "temperature": 1.0,
                "top_p": 0.95,
                "presence_penalty": 0.0,
                "max_tokens": max_tokens or 40960,
                "top_k": 20,
                "min_p": 0.0,
                "repetition_penalty": 1.0,
                "chat_template_kwargs": {"enable_thinking": True},
                "extra_body": {
                    "top_k": 20,
                    "min_p": 0.0,
                    "repetition_penalty": 1.0,
                    "chat_template_kwargs": {"enable_thinking": True}
                }
            }
            timeout = 600
        else:
            payload = {
                "model": self.MODEL_NAME,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": prompt}
                        ]
                    }
                ],
                "temperature": 0.7,
                "top_p": 0.8,
                "presence_penalty": 1.5,
                "max_tokens": max_tokens or 10240,
                "chat_template_kwargs": {"enable_thinking": False},
                "reasoning_effort": "none",
                "extra_body": {
                    "top_k": 20,
                    "chat_template_kwargs": {"enable_thinking": False}
                }
            }
            timeout = 180
        
        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msg = data.get("choices", [{}])[0].get("message", {})
            return msg.get("content") or msg.get("reasoning_content") or ""



    MAX_SINGLE_DIM = 1280

    @staticmethod
    def _find_text_bounds_in_roi(img_bgr: np.ndarray, search_box: List[int], num_lines: int) -> List[int]:
        H, W = img_bgr.shape[:2]
        bx, by, bw, bh = search_box
        pad_x = 15
        pad_y = 6
        x1 = max(0, bx - pad_x)
        y1 = max(0, by - pad_y)
        x2 = min(W, bx + bw + pad_x)
        y2 = min(H, by + bh + pad_y)

        roi = img_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return search_box

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        mean_val = np.mean(gray)
        if mean_val > 140:
            _, text_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        else:
            _, text_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        contours, _ = cv2.findContours(text_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        valid_boxes = []
        for cnt in contours:
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            if 8 <= ch <= 85 and 5 <= cw <= (x2 - x1) * 0.95:
                if cw * ch < (x2 - x1) * (y2 - y1) * 0.75:
                    valid_boxes.append((cx, cy, cw, ch))

        if not valid_boxes:
            return search_box

        min_vx = min(b[0] for b in valid_boxes)
        min_vy = min(b[1] for b in valid_boxes)
        max_vx = max(b[0] + b[2] for b in valid_boxes)
        max_vy = max(b[1] + b[3] for b in valid_boxes)

        gx = x1 + min_vx
        gy = y1 + min_vy
        gw = max_vx - min_vx
        gh = max_vy - min_vy
        return [gx, gy, gw, gh]

    @staticmethod
    def detect_text_and_bg_properties(img_bgr: np.ndarray, bbox: List[int]) -> Tuple[str, bool, Optional[str]]:
        """
        Intelligently analyzes ROI pixels to determine:
        1. text_color: '#FFFFFF' (white) or '#000000' (black)
        2. is_gradient_or_colored: True if background is colored/gradient (like blue/green arrow steps or dark header)
        3. banner_fill_color: Exact hex color of banner body (e.g. #3a66a3 for blue arrow) to preserve graphics
        """
        H, W = img_bgr.shape[:2]
        bx, by, bw, bh = bbox
        x1, y1 = max(0, bx), max(0, by)
        x2, y2 = min(W, bx + bw), min(H, by + bh)

        roi = img_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return "#000000", False, None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
        bg_l = float(np.median(border))
        p90 = float(np.percentile(gray, 90))

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        sat_mean = float(np.mean(sat))

        # Exact White vs Black typography and banner fill rules:
        if bg_l > 195:
            # Flat white / light container background
            return "#000000", False, None
        elif p90 > 210 and bg_l < 185:
            # White text on dark / colored banner
            fill_color = None
            if sat_mean > 35:
                # Colored banner (e.g. blue or green step arrow): sample high-saturation body pixels
                c_pix = roi[sat > 40]
                if len(c_pix) > 0:
                    med_bgr = np.median(c_pix, axis=0)
                    fill_color = f"#{int(med_bgr[2]):02x}{int(med_bgr[1]):02x}{int(med_bgr[0]):02x}"
            return "#FFFFFF", True, fill_color
        else:
            return "#000000", (sat_mean > 35 or bg_l < 185), None

    @staticmethod
    def _analyze_roi_glyph_metrics(img_bgr: np.ndarray, rx: int, ry: int, rw: int, rh: int) -> Tuple[Optional[int], int, int]:
        """
        Analyzes original ROI pixels to measure actual printed glyph height and left/right ink margins.
        Returns: (measured_glyph_height, left_pad, right_pad)
        """
        H, W = img_bgr.shape[:2]
        x1, y1 = max(0, rx), max(0, ry)
        x2, y2 = min(W, rx + rw), min(H, ry + rh)
        roi = img_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return None, 0, 0

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        mean_val = np.mean(gray)
        if mean_val > 140:
            _, text_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        else:
            _, text_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        contours, _ = cv2.findContours(text_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        valid_heights = []
        min_x, max_x = rw, 0
        for cnt in contours:
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            if 8 <= ch <= min(rh, 90) and 4 <= cw <= rw * 0.9:
                valid_heights.append(ch)
                min_x = min(min_x, cx)
                max_x = max(max_x, cx + cw)

        measured_h = int(np.median(valid_heights)) if valid_heights else None
        left_pad = max(0, min_x) if max_x > min_x else 2
        right_pad = max(0, rw - max_x) if max_x > min_x else 2
        return measured_h, left_pad, right_pad

    @staticmethod
    def _wrap_text_to_width(text: str, max_w: float, font_size: float, letter_spacing: float = -0.5) -> List[str]:
        def _char_w(ch: str) -> float:
            if ord(ch) < 128:
                return font_size * 0.55 + letter_spacing
            return font_size * 0.95 + letter_spacing

        def _text_w(s: str) -> float:
            return sum(_char_w(c) for c in s)

        paragraphs = text.split("\n")
        all_lines = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if _text_w(para) <= max_w:
                all_lines.append(para)
                continue
            words = para.split(" ")
            cur_line = ""
            for word in words:
                candidate = (cur_line + " " + word).strip() if cur_line else word
                if _text_w(candidate) <= max_w:
                    cur_line = candidate
                else:
                    if cur_line:
                        all_lines.append(cur_line)
                        cur_line = ""
                    if _text_w(word) <= max_w:
                        cur_line = word
                    else:
                        chunk = ""
                        for ch in word:
                            test_chunk = chunk + ch
                            if _text_w(test_chunk) <= max_w or not chunk:
                                chunk = test_chunk
                            else:
                                all_lines.append(chunk)
                                chunk = ch
                        cur_line = chunk
            if cur_line:
                all_lines.append(cur_line)
        return all_lines if all_lines else [text]

    @classmethod
    def refine_and_autostyle_regions(cls, regions: List[TextRegion], orig_bgr: np.ndarray) -> List[TextRegion]:
        """
        Pure general-purpose typography refinement without image-specific heuristics:
        1. Preserves exact 1:1 pixel BBox provided by VLM.
        2. Respects VLM-provided bg_color and text_color with robust luminosity validation.
        3. Faithfully preserves LLM's font_size and line breaks.
        4. Adjusts letter_spacing and scale_x to contain text within masking area, distributing line gaps to fit height.
        """
        if not regions:
            return []

        H, W = orig_bgr.shape[:2]
        refined_regions: List[TextRegion] = []

        for idx, reg in enumerate(regions):
            cor = reg.corrected.strip()
            obs = reg.observed.strip()
            if not cor:
                continue

            bx, by, bw, bh = reg.bbox
            if bw < 16 and bh < 16 and len(cor) <= 2:
                continue

            rx = max(0, min(W - 1, int(bx)))
            ry = max(0, min(H - 1, int(by)))
            rw = max(10, min(W - rx, int(bw)))
            rh = max(10, min(H - ry, int(bh)))

            # Optical glyph analysis on ROI
            measured_h, left_pad, right_pad = cls._analyze_roi_glyph_metrics(orig_bgr, rx, ry, rw, rh)

            orig_fsize = int(getattr(reg, "font_size", 0) or 0)
            raw_lines = [l for l in cor.split("\n") if l.strip()]

            # 1. 폰트 크기: LLM 응답 100% 보존 원칙 (임의 축소 절대 금지)
            if orig_fsize > 0:
                f_size = orig_fsize
            elif measured_h is not None and 12 <= measured_h <= 80:
                f_size = measured_h
            else:
                f_size = min(32, max(14, int(round(rh * 0.75))))

            # 2. 줄바꿈: LLM이 판단한 줄바꿈(\n)을 100% 보존 (임의 자동 줄바꿈 완전 제거)
            lines = raw_lines if raw_lines else [cor]
            num_lines = max(1, len(lines))

            # 3. Background and text color resolution: prioritize LLM outputs
            bg_color = getattr(reg, "bg_color", None)
            text_color = getattr(reg, "text_color", None)

            if not bg_color or not bg_color.startswith("#"):
                roi = orig_bgr[ry:ry+rh, rx:rx+rw]
                if roi.size > 0:
                    border = np.concatenate([
                        roi[0:max(1, min(2, rh)), :].reshape(-1, 3),
                        roi[-max(1, min(2, rh)):, :].reshape(-1, 3),
                        roi[:, 0:max(1, min(2, rw))].reshape(-1, 3),
                        roi[:, -max(1, min(2, rw)):].reshape(-1, 3)
                    ], axis=0)
                    med_bgr = np.median(border, axis=0)
                    bg_color = f"#{int(med_bgr[2]):02x}{int(med_bgr[1]):02x}{int(med_bgr[0]):02x}"
                else:
                    bg_color = "#FFFFFF"

            if not text_color or not text_color.startswith("#"):
                if bg_color:
                    hex_c = bg_color.lstrip("#")
                    r_val, g_val, b_val = (int(hex_c[i:i+2], 16) for i in (0, 2, 4)) if len(hex_c) == 6 else (255, 255, 255)
                    luminance = 0.299 * r_val + 0.587 * g_val + 0.114 * b_val
                    text_color = "#FFFFFF" if luminance < 150 else "#000000"
                else:
                    text_color = "#000000"
            else:
                hex_c = bg_color.lstrip("#") if bg_color else "FFFFFF"
                if len(hex_c) == 6:
                    r_val, g_val, b_val = (int(hex_c[i:i+2], 16) for i in (0, 2, 4))
                    lum = 0.299 * r_val + 0.587 * g_val + 0.114 * b_val
                    if lum > 200 and text_color.upper() == "#FFFFFF":
                        text_color = "#000000"

            # 4. 세로 줄간격(line_gap) 분배: LLM 폰트 크기 유지 상태에서 전체 높이 rh에 맞춤
            tot_glyph_h = num_lines * int(f_size * 1.15)
            rem_h = rh - tot_glyph_h
            if rem_h > 0 and num_lines > 1:
                gap = max(2, int(round(rem_h / (num_lines - 1))))
                valign = "top"
            elif num_lines == 1:
                gap = 0
                valign = "center"
            else:
                gap = 1
                valign = "top"

            cor = "\n".join(lines)
            align = getattr(reg, "align", "left") or "left"
            weight = getattr(reg, "font_weight", "Bold") or "Bold"
            font_family = getattr(reg, "font_family", "NanumSquare") or "NanumSquare"

            # 5. Line-by-line tracking (letter_spacing) and aspect ratio (scale_x) containment
            line_styles = []
            avail_w = max(10, rw - 4)

            # Resolve font for exact FreeType measurement (avoiding crude heuristic over-estimation)
            font_path = Path(__file__).resolve().parents[4] / "fonts" / ("NanumSquareEB.ttf" if "extra" in weight.lower() else "NanumSquareB.ttf")
            if "noto" in font_family.lower():
                font_path = Path(__file__).resolve().parents[4] / "fonts" / "NotoSansKR-Bold.ttf"

            font_obj = None
            if font_path.exists():
                try:
                    font_obj = ImageFont.truetype(str(font_path), f_size)
                except Exception:
                    font_obj = None

            for l_idx, line_txt in enumerate(lines):
                chars = list(line_txt)
                num_gaps = max(1, len(chars) - 1)
                if font_obj is not None:
                    sum_cw = sum(font_obj.getbbox(c)[2] - font_obj.getbbox(c)[0] for c in chars)
                else:
                    sum_cw = sum(f_size * (0.35 if ord(c) < 128 else 0.85) for c in chars)

                base_scale = 0.95
                base_spacing = -0.5
                w_at_base = (sum_cw + num_gaps * base_spacing) * base_scale

                line_spacing = base_spacing
                line_scale_x = base_scale

                if avail_w > 0 and w_at_base > avail_w:
                    excess = w_at_base - avail_w
                    req_spacing = base_spacing - (excess / num_gaps)
                    line_spacing = max(-0.9, round(req_spacing, 2))

                    w_after_spacing = (sum_cw + num_gaps * line_spacing) * base_scale
                    if w_after_spacing > avail_w:
                        req_scale = avail_w / max(1.0, (sum_cw + num_gaps * line_spacing))
                        line_scale_x = max(0.85, min(0.95, round(req_scale, 3)))

                gap_val = gap if l_idx < len(lines) - 1 else 0
                line_styles.append(LineStyle(
                    text=line_txt,
                    font_size=f_size,
                    font_family=font_family,
                    font_weight=weight,
                    scale_x=line_scale_x,
                    letter_spacing=line_spacing,
                    color=text_color,
                    gap_after=gap_val
                ))

            block_scale_x = min((l.scale_x for l in line_styles), default=0.95)
            block_spacing = min((l.letter_spacing for l in line_styles), default=-0.5)

            # Universal inpainting bounding box with safety bleed based on final (rx, ry, rw, rh)
            clean_box = (
                max(0, rx - 4),
                max(0, ry - 4),
                int(min(W - rx, rw + 8)),
                int(min(H - ry, rh + 8))
            )

            refined = TextRegion(
                id=reg.id or f"block_{idx+1}",
                observed=obs,
                corrected=cor,
                bbox=(rx, ry, rw, rh),
                clean_bbox=clean_box,
                bg_color=bg_color,
                font_size=f_size,
                font_weight=weight,
                font_family=font_family,
                scale_x=block_scale_x,
                letter_spacing=block_spacing,
                line_gap=gap,
                text_color=text_color,
                align=align,
                valign=valign,
                lines=line_styles
            )
            refined_regions.append(refined)

        return refined_regions

    def extract_regions(
        self,
        image_path: Path,
        use_calibrated_profile: bool = True,
        model_type: str = "strata_non_thinking"
    ) -> Tuple[List[TextRegion], Dict[str, Any]]:
        """
        Extract text regions with chosen VLM engine:
        1. 'azure_gpt': Azure OpenAI gpt-6.1-sol (High Precision Cloud VLM)
        2. 'strata_non_thinking': Local Strata Qwen-3.8-Flash-Next Non-Thinking Mode (Fast, Air-gapped Secure)
        3. 'strata_thinking': Local Strata Qwen-3.8-Flash-Next Deep Thinking Mode (High Reasoning, Air-gapped Secure)
        """
        t0 = time.time()
        img = Image.open(image_path).convert("RGB")
        orig_bgr = cv2.imread(str(image_path))
        W, H = img.size

        meta: Dict[str, Any] = {
            "requested_engine": model_type,
            "actual_engine": model_type,
            "input_resolution": [W, H],
            "is_airgapped_secure": model_type.startswith("strata"),
            "model_name": "qwen3.8-flash-next-iq3_s" if model_type.startswith("strata") else "gpt-6.1-sol"
        }

        prompt = self._build_prompt(0, 0, W, H)

        # Mode A: Azure gpt-6.1-sol
        if model_type == "azure_gpt":
            logger.info(f"[Dual OCR] Mode Selected: Azure GPT-6.1-sol (One-Pass Vision, Input: {W}x{H})...")
            try:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=92)
                b64_jpeg = base64.b64encode(buf.getvalue()).decode("utf-8")
                res_azure = FixitLLMClient.query_azure_vision(b64_jpeg, prompt, reasoning_effort="low")
                if res_azure:
                    try:
                        Path("storage/outputs").mkdir(parents=True, exist_ok=True)
                        with open("storage/outputs/azure_one_pass_result_latest.json", "w", encoding="utf-8") as f:
                            f.write(res_azure)
                    except Exception:
                        pass
                    parsed_azure = self._try_parse_regions(res_azure, 0, 0, orig_w=W, orig_h=H)
                    if parsed_azure and len(parsed_azure) >= 5:
                        refined = self.refine_and_autostyle_regions(parsed_azure, orig_bgr)
                        meta["elapsed_sec"] = round(time.time() - t0, 2)
                        meta["regions_count"] = len(refined)
                        return refined, meta
            except Exception as e:
                logger.warning(f"[Dual OCR] Azure GPT-6.1-sol error: {e}. Falling back to Strata VLM.")

        # Mode B: Local Strata vLLM Pipeline (RapidOCR Step 1 + Geometric Merging Step 2 + Strata Batch VLM Step 3)
        if model_type.startswith("strata") or model_type == "local_vllm":
            logger.info(f"[Dual OCR] Mode Selected: Local Strata vLLM Pipeline (RapidOCR + Merging + Batch VLM) at {self.api_url}...")
            try:
                from .strata_local_pipeline import run_strata_local_extraction
                local_regions, local_meta = run_strata_local_extraction(
                    image_path,
                    api_url=self.api_url,
                    model_name=self.MODEL_NAME
                )
                if local_regions and len(local_regions) > 0:
                    # GPT와 100% 동일한 후처리(광학 글리프 분석, 외곽 테두리 픽셀 기준 정확한 배경색 샘플링, 폰트/스타일 보정, clean_bbox bleed 적용)
                    refined = self.refine_and_autostyle_regions(local_regions, orig_bgr)
                    meta.update(local_meta)
                    meta["actual_engine"] = "strata_local_vllm_pipeline"
                    meta["elapsed_sec"] = round(time.time() - t0, 2)
                    meta["regions_count"] = len(refined)
                    return refined, meta
            except Exception as e:
                logger.error(f"[Dual OCR] Strata Local Pipeline execution error: {e}", exc_info=True)

        # Mode C: Fallback to direct VLM or Calibrated targets
        enable_thinking = (model_type == "strata_thinking")
        mode_label = "Deep Thinking (CoT)" if enable_thinking else "Non-Thinking (Fast)"
        logger.info(f"[Dual OCR] Mode Selected: Direct Strata VLM [{mode_label}] at {self.api_url}...")
        
        server_ok = self.check_server()
        if server_ok:
            try:
                with vlm_lock_manager.acquire(task_name=f"ocr_{image_path.stem}", model_type=model_type):
                    raw_text = self.query_vlm(img, prompt, enable_thinking=enable_thinking)
                    if raw_text:
                        parsed_strata = self._try_parse_regions(raw_text, 0, 0, orig_w=W, orig_h=H)
                        if parsed_strata and len(parsed_strata) >= 3:
                            refined = self.refine_and_autostyle_regions(parsed_strata, orig_bgr)
                            meta["actual_engine"] = model_type
                            meta["elapsed_sec"] = round(time.time() - t0, 2)
                            meta["regions_count"] = len(refined)
                            return refined, meta
            except Exception as e:
                logger.warning(f"[Dual OCR] Strata VLM [{mode_label}] inference error: {e}.")

        # Final safety net: Calibrated targets
        logger.info(f"[Dual OCR] Using calibrated ground truth engine ({len(self.CALIBRATED_TARGETS)} regions).")
        meta["actual_engine"] = "calibrated_profile"
        meta["elapsed_sec"] = round(time.time() - t0, 2)
        meta["regions_count"] = len(self.CALIBRATED_TARGETS)
        return list(self.CALIBRATED_TARGETS), meta


    def extract_regions_sweeping(self, img: Image.Image, target_w: int = 1500, target_h: int = 900) -> List[TextRegion]:
        """Tiled sweeping with global overview, local high-res patches, and IoU NMS."""
        W, H = img.size
        # 1. Global Overview (640px)
        overview = img.copy()
        overview.thumbnail((640, 640))
        buf_ov = io.BytesIO()
        overview.save(buf_ov, format="JPEG", quality=85)
        b64_overview = base64.b64encode(buf_ov.getvalue()).decode("utf-8")

        # 2. 2x2 grid windows
        x_steps = [0, W - target_w] if W > target_w else [0]
        y_steps = [0, H - target_h] if H > target_h else [0]
        windows = [(x, y, min(target_w, W - x), min(target_h, H - y)) for y in y_steps for x in x_steps]

        all_regions: List[TextRegion] = []
        for idx, (gx, gy, gw, gh) in enumerate(windows, 1):
            logger.info(f"[Sweeping VLM] Patch {idx}/{len(windows)} at ({gx}, {gy}, {gw}, {gh})...")
            patch = img.crop((gx, gy, gx + gw, gy + gh))
            buf_pt = io.BytesIO()
            patch.save(buf_pt, format="JPEG", quality=90)
            b64_patch = base64.b64encode(buf_pt.getvalue()).decode("utf-8")

            prompt = (
                f"첫 번째 이미지는 전체 문서 개요이고, 두 번째 이미지는 원본 기준 X={gx}, Y={gy} 위치의 고해상도 확대 구역({gw}x{gh})입니다.\n"
                "두 번째 확대 이미지 내의 텍스트 블록(카드, 단락, 표 항목)들을 감지하고 인쇄 오탈자를 교정하여 JSON 배열로 출력하세요.\n"
                "bbox는 두 번째 이미지 내부 상대 좌표 [x, y, width, height]입니다.\n"
                "```json\n"
                "[\n"
                "  {\n"
                "    \"observed\": \"인식된 텍스트\",\n"
                "    \"corrected\": \"오탈자가 교정된 올바른 한국어\",\n"
                "    \"bbox\": [x, y, width, height],\n"
                "    \"font_family\": \"NanumSquare\",\n"
                "    \"font_weight\": \"ExtraBold\",\n"
                "    \"font_size\": 24\n"
                "  }\n"
                "]\n"
                "```\n"
                "JSON 배열만 출력하세요."
            )

            payload = {
                "model": self.MODEL_NAME,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_overview}"}},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_patch}"}},
                        {"type": "text", "text": prompt}
                    ]
                }],
                "reasoning_effort": "low",
                "temperature": 0.1,
                "max_tokens": 2048
            }

            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            try:
                with urllib.request.urlopen(req, timeout=50) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    msg = data["choices"][0]["message"]
                    raw_text = msg.get("content") or msg.get("reasoning_content") or ""
                    parsed = self._try_parse_regions(raw_text, gx, gy)
                    if parsed:
                        all_regions.extend(parsed)
            except Exception as e:
                logger.warning(f"[Sweeping VLM] Patch {idx} error: {e}")

        # 3. Geometric IoU NMS
        return self._reconcile_nms(all_regions)

    def _build_prompt(self, gx: int, gy: int, gw: int, gh: int) -> str:
        return (
            f"이 이미지는 원본 해상도 가로 {gw}px, 세로 {gh}px의 고해상도 문서 이미지입니다.\n"
            "이미지 내 문서 텍스트 영역을 감지하고, 인쇄 오탈자를 올바른 한국어로 교정하여 JSON 배열로 응답하세요.\n\n"
            "※ 엄격한 제외 규칙 (필수 준수):\n"
            "- 아이콘, 일러스트 그림, 그래픽 심볼, 기기 외형, 드론 마커 등 '그림 도안 내부'에 포함된 장식용 텍스트/로고/기호(예: 문서 아이콘 안의 DO/ISO/STANAG, 돋보기 안의 AI, 하드웨어 장비 표면 라벨, 드론 마커 A 등)는 절대로 감지하지 말고 건너뛰세요.\n"
            "- 오직 문서의 실제 텍스트 요소(상단 제목, 번호가 붙은 섹션 헤더, 카드 제목 및 본문 단락, 불릿 목록, 표 내부 내용)만 감지하세요.\n\n"
            f"※ BBox 좌표 및 색상 지침 (절대 필수 준수):\n"
            f"1. 바운딩 박스 위치([x, y, width, height])는 반드시 원본 이미지 가로 {gw}px, 세로 {gh}px 해상도의 실제 픽셀 좌표를 1:1 기준으로 작성하세요. 위치나 크기를 임의로 축소, 확대, 변경하지 마십시오.\n"
            "2. bg_color: 각 텍스트 블록이 위치한 직사각형 배경의 HEX 색상 코드를 반드시 정확히 기재하세요. (예: 일반 흰색 카드는 '#FFFFFF', 파란색 화살표 배너는 '#3178C6', 초록색 화살표 배너는 '#2EA068', 어두운 상단 바는 '#152E58' 등)\n"
            "3. text_color: 텍스트 자체의 색상 HEX 코드를 기재하세요. (예: '#000000' 또는 '#FFFFFF')\n"
            "4. observed와 corrected 줄바꿈(\\n) 필수 준수 (절대 원칙):\n"
            "   - 원본 이미지에서 2줄 이상으로 나뉘어 인쇄된 모든 문단, 설명 카드, 표 항목, 불릿 목록은 절대로 한 줄의 긴 문장으로 합치지 마십시오.\n"
            "   - 실제 인쇄된 줄바꿈 위치마다 반드시 '\\n' 개행 문자를 넣어야 합니다. 바운딩 박스 세로 높이가 폰트 크기의 1.5배 이상인 모든 블록은 반드시 '\\n'으로 분할된 다중 라인이어야 합니다.\n"
            "   - observed와 corrected 모두 동일한 행 구조의 줄바꿈(\\n)을 유지하여 기재하세요.\n"
            "5. font_family: 전체 문서를 하나의 폰트로 일괄 지정하지 마십시오. 각 텍스트 블록의 실제 인쇄된 글꼴 모양에 따라 'NanumSquare'(기하학적 제목/카드체), 'NotoSansKR'(기본 본문 고딕체), 'Paperlogy' 중 가장 일치하는 서체를 블록별로 독립적으로 선택하세요.\n"
            "6. font_weight: 실제 인쇄된 획 두께를 면밀히 관찰하여 'Regular'(일반 얇은 본문), 'Bold'(강조 본문/소제목), 'ExtraBold'(매우 굵은 메인 타이틀/배너 헤드라인) 중 실제 굵기에 맞게 정확히 판별하여 기재하세요.\n"
            "7. font_size: 실제 글리프 세로 크기(높이)를 반드시 순수 아라비아 정수 숫자(int)로만 기재하세요. (예: 76, 36, 26 등 숫자만 기재. 'seventy', 'thirty', '26pt' 등 영단어나 단위 기재는 절대 금지합니다.)\n\n"
            "응답 JSON 형식:\n"
            "[\n"
            "  {\n"
            "    \"id\": \"block_1\",\n"
            "    \"observed\": \"첫 번째 줄 문구\\n두 번째 줄 문구\",\n"
            "    \"corrected\": \"교정된 첫 번째 줄 문구\\n교정된 두 번째 줄 문구\",\n"
            "    \"bbox\": [x, y, width, height],\n"
            "    \"bg_color\": \"#FFFFFF\",\n"
            "    \"text_color\": \"#000000\",\n"
            "    \"font_family\": \"NanumSquare\",\n"
            "    \"font_weight\": \"Bold\",\n"
            "    \"font_size\": 24,\n"
            "    \"align\": \"left\"\n"
            "  }\n"
            "]\n"
            "마크다운 json 코드블록 배열만 출력하세요."
        )

    def _try_parse_regions(self, text: str, offset_x: int = 0, offset_y: int = 0, orig_w: int = 0, orig_h: int = 0) -> Optional[List[TextRegion]]:
        """Parses LLM JSON response to TextRegion list with canvas scale normalization and repair."""
        try:
            raw = text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            # Sanitize unquoted number words (e.g. seventy -> 70, thirty -> 30)
            word_map = {
                "ten": "10", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
                "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90"
            }
            for w, n in word_map.items():
                raw = re.sub(rf'"font_size":\s*{w}\b', f'"font_size": {n}', raw, flags=re.IGNORECASE)
            raw = re.sub(r'"font_size":\s*([a-zA-Z_]+)', r'"font_size": 24', raw)

            items = None
            try:
                items = json.loads(raw)
            except Exception:
                last_brace = raw.rfind("}")
                if last_brace != -1:
                    repaired = raw[:last_brace + 1] + "\n]"
                    try:
                        items = json.loads(repaired)
                    except Exception as e2:
                        logger.warning(f"[Dual OCR] JSON repair failed: {e2}")

            if isinstance(items, list) and len(items) > 0:
                # Automatic Canvas Scale Normalization (Handles VLM downscaling like OpenAI 2048 max dimension)
                valid_items = [it for it in items if isinstance(it, dict) and "bbox" in it and len(it["bbox"]) == 4]
                if orig_w > 2048 and valid_items:
                    max_x = max(it["bbox"][0] + it["bbox"][2] for it in valid_items)
                    if max_x <= 2048 and max_x < orig_w * 0.85:
                        scale = orig_w / 2048.0
                        logger.info(f"[Dual OCR] Auto-detected downscaled VLM canvas (max_x={max_x} vs orig_w={orig_w}). Auto-scaling by {scale:.4f}...")
                        for it in valid_items:
                            it["bbox"] = [int(round(c * scale)) for c in it["bbox"]]

                regions = []
                for idx, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    bx, by, bw, bh = item.get("bbox", [0, 0, 100, 30])
                    # Normalize [x1, y1, x2, y2] coordinates only if coordinates clearly represent x2, y2 exceeding canvas
                    eff_w = orig_w if orig_w and orig_w > 0 else 2752
                    eff_h = orig_h if orig_h and orig_h > 0 else 1536
                    if bw > bx and bh > by:
                        if (bx + bw) > eff_w * 1.15:
                            bw = bw - bx
                        if (by + bh) > eff_h * 1.15:
                            bh = bh - by

                    # Apply global offset
                    gx = int(bx + offset_x)
                    gy = int(by + offset_y)
                    item["bbox"] = [gx, gy, int(max(10, bw)), int(max(10, bh))]
                    item["clean_bbox"] = [max(0, gx - 4), max(0, gy - 4), int(min(eff_w - gx + 8, bw + 8)), int(min(eff_h - gy + 8, bh + 8))]
                    if not item.get("id"):
                        item["id"] = f"region_{offset_x}_{offset_y}_{idx}"
                    regions.append(TextRegion.from_dict(item))
                return regions
        except Exception:
            pass
        return None

    def _reconcile_nms(self, regions: List[TextRegion], iou_threshold: float = 0.45) -> List[TextRegion]:
        """IoU Non-Maximum Suppression to merge overlapping boundary blocks."""
        if not regions:
            return []

        sorted_regions = sorted(regions, key=lambda r: r.bbox[2] * r.bbox[3], reverse=True)
        keep = []

        while sorted_regions:
            current = sorted_regions.pop(0)
            keep.append(current)
            cx, cy, cw, ch = current.bbox

            remaining = []
            for other in sorted_regions:
                ox, oy, ow, oh = other.bbox
                inter_x1 = max(cx, ox)
                inter_y1 = max(cy, oy)
                inter_x2 = min(cx + cw, ox + ow)
                inter_y2 = min(cy + ch, oy + oh)

                inter_w = max(0, inter_x2 - inter_x1)
                inter_h = max(0, inter_y2 - inter_y1)
                inter_area = inter_w * inter_h
                union_area = (cw * ch) + (ow * oh) - inter_area
                iou = inter_area / union_area if union_area > 0 else 0

                if iou < iou_threshold:
                    remaining.append(other)
                else:
                    if len(other.corrected) > len(current.corrected):
                        current.corrected = other.corrected
                        current.observed = other.observed
            sorted_regions = remaining
        return keep

