import os
import shutil
import uuid
import json
import re
import io
import base64
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image
import cv2
import numpy as np

logger = logging.getLogger("fixit_api")

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from fixit_api.config import settings
from fixit_api.database import get_db, get_auth_db, engine, Base, init_db
from fixit_api.models import User, FixitProject, FixitRevision
from fixit_api.auth import verify_password, create_access_token, get_current_user
from fixit_api.pipeline.schema import TextRegion
from fixit_api.pipeline.pipeline import ImageRestorationPipeline
from fixit_api.services.cutout_service import CutoutService
from fixit_api.services.vlm_lock_service import vlm_lock_manager

# Ensure storage directories exist
storage_root = Path(settings.STORAGE_DIR)
storage_root.mkdir(parents=True, exist_ok=True)
upload_dir = storage_root / "uploads"
upload_dir.mkdir(parents=True, exist_ok=True)
output_dir = storage_root / "outputs"
output_dir.mkdir(parents=True, exist_ok=True)

# Ensure database tables are created on the workspace engine
init_db()

app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline_engine = ImageRestorationPipeline(
    strata_url=settings.STRATA_VLM_URL,
    font_dir=settings.FONTS_DIR
)

# Static file serving for storage assets
app.mount("/api/storage", StaticFiles(directory=str(storage_root)), name="storage")

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "database": settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "configured"
    }

# ----------------- Authentication -----------------
class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/login")
def login(req: LoginRequest, auth_db: Session = Depends(get_auth_db)):
    raw_email = req.email.strip().lower()
    candidate_emails = [raw_email]
    if "@" not in raw_email:
        candidate_emails.extend([f"{raw_email}@kiast.or.kr", f"{raw_email}@airsafety.or.kr"])
    elif raw_email.endswith("@airsafety.or.kr"):
        candidate_emails.append(raw_email.replace("@airsafety.or.kr", "@kiast.or.kr"))
    elif raw_email.endswith("@kiast.or.kr"):
        candidate_emails.append(raw_email.replace("@kiast.or.kr", "@airsafety.or.kr"))

    user = auth_db.query(User).filter(User.email.in_(candidate_emails)).first()
    if not user:
        user = auth_db.query(User).filter(User.email.ilike(raw_email)).first()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="아이디(이메일) 또는 비밀번호가 일치하지 않습니다. (사내 기본 비밀번호: ts2020!!)"
        )

    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name or user.email.split("@")[0],
            "department": user.department,
            "is_admin": user.is_admin,
        }
    }

@app.get("/api/auth/me")
def get_me(user: Optional[User] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "department": user.department,
        "is_admin": user.is_admin
    }

# ----------------- Project & Revisions -----------------
class ProjectSaveRequest(BaseModel):
    name: Optional[str] = None
    regions: List[Dict[str, Any]]
    current_image_url: Optional[str] = None
    background_image_url: Optional[str] = None
    increment_version: Optional[bool] = False
    set_version: Optional[int] = None

@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    q = db.query(FixitProject)
    if user:
        q = q.filter((FixitProject.user_id == user.id) | (FixitProject.user_id.is_(None)))
    projects = q.order_by(FixitProject.updated_at.desc()).limit(50).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "version": p.version,
            "original_image_path": p.original_image_path,
            "background_image_path": p.background_image_path,
            "current_image_path": p.current_image_path,
            "regions_count": len(p.regions_json) if isinstance(p.regions_json, list) else 0,
            "metadata": p.metadata_json or {},
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in projects
    ]

@app.post("/api/projects")
async def create_project(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user)
):
    ext = Path(file.filename or "image.png").suffix or ".png"
    file_id = f"{uuid.uuid4().hex[:12]}{ext}"
    dest_path = upload_dir / file_id
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    proj_name = name or Path(file.filename or "무제 프로젝트").stem
    project = FixitProject(
        user_id=user.id if user else None,
        name=proj_name,
        version=0,  # 최초는 v0 (AI 인식 전)
        original_image_path=f"/api/storage/uploads/{file_id}",
        background_image_path=None,
        current_image_path=f"/api/storage/uploads/{file_id}",
        regions_json=[],
        metadata_json={}
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Initial revision: v0 원본
    rev = FixitRevision(
        project_id=project.id,
        version=0,
        regions_json=[],
        image_path=project.original_image_path,
        background_image_path=project.original_image_path,
        metadata_json={}
    )
    db.add(rev)
    db.commit()

    return {
        "id": project.id,
        "name": project.name,
        "version": project.version,
        "original_image_path": project.original_image_path,
        "current_image_path": project.current_image_path,
        "regions": []
    }

@app.get("/api/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(FixitProject).filter(FixitProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    clean_bg = resolve_clean_background(project, project.background_image_path, None, db)
    if clean_bg and clean_bg != project.background_image_path:
        project.background_image_path = clean_bg
        db.commit()

    # Ensure regions are consistent with active version if project.regions_json is empty
    regions = project.regions_json or []
    if not regions and project.version > 0:
        rev = db.query(FixitRevision).filter(
            FixitRevision.project_id == project.id,
            FixitRevision.version == project.version
        ).first()
        if not rev:
            rev = db.query(FixitRevision).filter(
                FixitRevision.project_id == project.id,
                FixitRevision.version > 0
            ).order_by(FixitRevision.version.desc()).first()
        if rev and rev.regions_json:
            regions = rev.regions_json
            project.regions_json = regions
            db.commit()

    return {
        "id": project.id,
        "name": project.name,
        "version": project.version,
        "original_image_path": project.original_image_path,
        "background_image_path": clean_bg or project.original_image_path,
        "current_image_path": project.current_image_path,
        "regions": regions,
        "metadata": project.metadata_json or {}
    }

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(FixitProject).filter(FixitProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="삭제할 프로젝트를 찾을 수 없습니다.")

    # Delete related revisions first
    db.query(FixitRevision).filter(FixitRevision.project_id == project_id).delete()
    db.delete(project)
    db.commit()

    return {"message": f"'{project.name}' 프로젝트가 삭제되었습니다.", "deleted_id": project_id}

@app.put("/api/projects/{project_id}")
def save_project(project_id: int, req: ProjectSaveRequest, db: Session = Depends(get_db)):
    project = db.query(FixitProject).filter(FixitProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    prev_ver = project.version

    if req.increment_version:
        max_ver = db.query(func.max(FixitRevision.version)).filter(FixitRevision.project_id == project.id).scalar()
        if max_ver is None:
            max_ver = project.version
        target_ver = max(max_ver, project.version) + 1
    elif req.set_version is not None:
        target_ver = req.set_version
    else:
        target_ver = project.version

    project.version = target_ver

    if req.name:
        project.name = req.name
    project.regions_json = req.regions
    if req.current_image_url:
        project.current_image_path = req.current_image_url
    clean_bg = resolve_clean_background(project, req.background_image_url, None, db)
    if clean_bg:
        project.background_image_path = clean_bg

    # Save or update Revision snapshot for the target version
    rev = db.query(FixitRevision).filter(
        FixitRevision.project_id == project.id,
        FixitRevision.version == target_ver
    ).order_by(FixitRevision.id.desc()).first()

    effective_rev_bg = clean_bg or project.background_image_path

    if rev and target_ver == prev_ver:
        # Same version in-place update
        rev.regions_json = req.regions
        if project.current_image_path:
            rev.image_path = project.current_image_path
        if effective_rev_bg:
            rev.background_image_path = effective_rev_bg
        if project.metadata_json:
            rev.metadata_json = project.metadata_json
    else:
        # New version revision snapshot
        rev = FixitRevision(
            project_id=project.id,
            version=target_ver,
            regions_json=req.regions,
            image_path=project.current_image_path,
            background_image_path=effective_rev_bg,
            metadata_json=project.metadata_json
        )
        db.add(rev)

    db.commit()
    db.refresh(project)

    msg = (
        f"v{prev_ver}에서 변경되어 v{target_ver} 새 버전으로 저장되었습니다."
        if target_ver != prev_ver
        else f"v{target_ver} 상태가 저장되었습니다."
    )

    return {
        "id": project.id,
        "version": project.version,
        "prev_version": prev_ver,
        "background_image_path": project.background_image_path,
        "current_image_path": project.current_image_path,
        "metadata": project.metadata_json or {},
        "message": msg
    }

def resolve_clean_background(project: Optional[FixitProject], candidate: Optional[str] = None, rev: Optional[FixitRevision] = None, db: Optional[Session] = None) -> Optional[str]:
    """Ensures background image for edit canvas is NEVER an unmasked raw image from uploads/."""
    if candidate and "uploads/" not in candidate and candidate.strip():
        return candidate
    if rev and rev.background_image_path and "uploads/" not in rev.background_image_path:
        return rev.background_image_path
    if project and project.background_image_path and "uploads/" not in project.background_image_path:
        return project.background_image_path
    if rev and rev.image_path:
        m = re.search(r"/outputs/([a-zA-Z0-9]+)/", rev.image_path)
        if m:
            cand_file = storage_root / "outputs" / m.group(1) / "background_inpainted.png"
            if cand_file.exists():
                return f"/api/storage/outputs/{m.group(1)}/background_inpainted.png"
    if db and project:
        other = db.query(FixitRevision).filter(
            FixitRevision.project_id == project.id,
            FixitRevision.version > 0,
            FixitRevision.background_image_path.isnot(None),
            ~FixitRevision.background_image_path.like("%uploads/%")
        ).order_by(FixitRevision.version.desc()).first()
        if other and other.background_image_path:
            return other.background_image_path
    out_dir = storage_root / "outputs"
    if out_dir.exists():
        for p in out_dir.iterdir():
            if p.is_dir() and (p / "background_inpainted.png").exists():
                return f"/api/storage/outputs/{p.name}/background_inpainted.png"
    return None

@app.get("/api/projects/{project_id}/revisions")
def list_revisions(project_id: int, db: Session = Depends(get_db)):
    project = db.query(FixitProject).filter(FixitProject.id == project_id).first()
    revs = db.query(FixitRevision).filter(FixitRevision.project_id == project_id).order_by(FixitRevision.version.asc(), FixitRevision.id.desc()).all()
    # Deduplicate keeping latest entry per version, then return in version order
    by_version = {}
    for r in revs:
        if r.version not in by_version:
            by_version[r.version] = r

    # Auto-synthesize and persist v0 (원본) if missing
    if project and 0 not in by_version and project.original_image_path:
        v0_rev = FixitRevision(
            project_id=project.id,
            version=0,
            regions_json=[],
            image_path=project.original_image_path,
            background_image_path=project.original_image_path,
            metadata_json={}
        )
        db.add(v0_rev)
        db.commit()
        db.refresh(v0_rev)
        by_version[0] = v0_rev

    unique_revs = sorted(by_version.values(), key=lambda x: x.version)
    return [
        {
            "id": r.id,
            "version": r.version,
            "image_path": r.image_path,
            "background_image_path": (project.original_image_path if project else None) if r.version == 0 else resolve_clean_background(project, getattr(r, "background_image_path", None), r, db),
            "regions_count": len(r.regions_json) if isinstance(r.regions_json, list) else 0,
            "regions": r.regions_json or [],
            "metadata": getattr(r, "metadata_json", {}) or {},
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in unique_revs
    ]

@app.post("/api/projects/{project_id}/revisions/restore")
def restore_revision(project_id: int, target_version: int = Form(...), db: Session = Depends(get_db)):
    project = db.query(FixitProject).filter(FixitProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    rev = db.query(FixitRevision).filter(
        FixitRevision.project_id == project_id,
        FixitRevision.version == target_version
    ).order_by(FixitRevision.id.desc()).first()

    # If target_version == 0 and not found, auto-create
    if not rev and target_version == 0 and project.original_image_path:
        rev = FixitRevision(
            project_id=project.id,
            version=0,
            regions_json=[],
            image_path=project.original_image_path,
            background_image_path=project.original_image_path,
            metadata_json={}
        )
        db.add(rev)
        db.commit()
        db.refresh(rev)

    if not rev:
        raise HTTPException(status_code=404, detail="복원할 대상 버전을 찾을 수 없습니다.")

    # Roll back maintaining the target version number without creating a new incremented revision
    project.version = target_version
    project.regions_json = rev.regions_json or []
    project.current_image_path = rev.image_path

    # Restore background image and metadata for target version
    if target_version == 0:
        effective_bg = project.original_image_path
        project.metadata_json = {}
    else:
        clean_bg = resolve_clean_background(project, getattr(rev, "background_image_path", None), rev, db)
        if clean_bg:
            project.background_image_path = clean_bg
            rev.background_image_path = clean_bg
            effective_bg = clean_bg
        else:
            effective_bg = project.background_image_path or project.original_image_path
        if getattr(rev, "metadata_json", None):
            project.metadata_json = rev.metadata_json

    db.commit()
    db.refresh(project)

    return {
        "id": project.id,
        "version": project.version,
        "regions": project.regions_json or [],
        "current_image_path": project.current_image_path,
        "background_image_path": effective_bg,
        "original_image_path": project.original_image_path,
        "metadata": project.metadata_json or {},
        "message": f"버전 {target_version} 상태로 복원되었습니다."
    }

@app.delete("/api/projects/{project_id}/revisions/{target_version}")
def delete_revision(project_id: int, target_version: int, db: Session = Depends(get_db)):
    project = db.query(FixitProject).filter(FixitProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    # Check total revisions count
    total_revs = db.query(FixitRevision).filter(FixitRevision.project_id == project_id).count()
    if total_revs <= 1 and (project.version == target_version or target_version == 0):
        raise HTTPException(status_code=400, detail="최소 1개의 버전은 유지되어야 하므로 삭제할 수 없습니다.")

    # Delete all revisions matching target_version
    db.query(FixitRevision).filter(
        FixitRevision.project_id == project_id,
        FixitRevision.version == target_version
    ).delete()

    # Find the latest remaining revision
    latest_remaining = db.query(FixitRevision).filter(
        FixitRevision.project_id == project_id,
        FixitRevision.version != target_version
    ).order_by(FixitRevision.version.desc()).first()

    # If the currently active project version was the one deleted, fall back to the most recent remaining revision
    if project.version == target_version:
        if latest_remaining:
            project.version = latest_remaining.version
            project.regions_json = latest_remaining.regions_json or []
            project.current_image_path = latest_remaining.image_path
            if latest_remaining.version == 0:
                project.background_image_path = project.original_image_path
                project.metadata_json = {}
            else:
                project.background_image_path = getattr(latest_remaining, "background_image_path", None) or project.original_image_path
                project.metadata_json = getattr(latest_remaining, "metadata_json", {}) or {}
        else:
            project.version = 0
            project.regions_json = []
            project.current_image_path = project.original_image_path
            project.background_image_path = project.original_image_path
            project.metadata_json = {}

    db.commit()
    db.refresh(project)

    effective_bg = project.original_image_path if project.version == 0 else (project.background_image_path or project.original_image_path)

    return {
        "message": f"버전 {target_version}이(가) 삭제되었습니다.",
        "active_version": project.version,
        "regions": project.regions_json or [],
        "current_image_path": project.current_image_path,
        "background_image_path": effective_bg,
        "metadata": project.metadata_json or {}
    }

# ----------------- Restoration Pipeline Endpoints -----------------
@app.post("/api/restore/auto")
async def restore_auto(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(None),
    model_type: str = Form("strata_non_thinking"),
    db: Session = Depends(get_db)
):
    """One-click automated 4-step restoration pipeline with selectable VLM engine."""
    task_id = uuid.uuid4().hex[:12]
    task_dir = output_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "image.png").suffix or ".png"
    in_file = task_dir / f"input{ext}"
    with open(in_file, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Execute complete pipeline with chosen model_type
    report = pipeline_engine.run(
        str(in_file),
        output_dir=str(task_dir),
        generate_comparisons=True,
        model_type=model_type
    )

    bg_url = f"/api/storage/outputs/{task_id}/background_inpainted.png"
    final_url = f"/api/storage/outputs/{task_id}/{in_file.stem}_restored.png"
    vlm_meta = report.get("metadata", {})

    # If project_id provided, update project state and revision history
    if project_id:
        proj = db.query(FixitProject).filter(FixitProject.id == project_id).first()
        if proj:
            proj.background_image_path = bg_url
            proj.current_image_path = final_url
            proj.regions_json = report["regions"]
            proj.metadata_json = vlm_meta
            proj.version = 1

            # Ensure v0 (원본) exists in revisions
            has_v0 = db.query(FixitRevision).filter(
                FixitRevision.project_id == proj.id,
                FixitRevision.version == 0
            ).first()
            if not has_v0 and proj.original_image_path:
                v0_rev = FixitRevision(
                    project_id=proj.id,
                    version=0,
                    regions_json=[],
                    image_path=proj.original_image_path,
                    background_image_path=proj.original_image_path,
                    metadata_json={}
                )
                db.add(v0_rev)

            # Save initial analysis revision snapshot (v1: AI 인식/복원 완료본)
            rev = db.query(FixitRevision).filter(
                FixitRevision.project_id == proj.id,
                FixitRevision.version == 1
            ).order_by(FixitRevision.id.desc()).first()
            if rev:
                rev.regions_json = report["regions"]
                rev.image_path = final_url
                rev.background_image_path = bg_url
                rev.metadata_json = vlm_meta
            else:
                rev = FixitRevision(
                    project_id=proj.id,
                    version=1,
                    regions_json=report["regions"],
                    image_path=final_url,
                    background_image_path=bg_url,
                    metadata_json=vlm_meta
                )
                db.add(rev)
            db.commit()

    return {
        "task_id": task_id,
        "background_image_url": bg_url,
        "restored_image_url": final_url,
        "regions": report["regions"],
        "metadata": vlm_meta,
        "comparisons": [
            {
                **comp,
                "comparison_url": f"/api/storage/outputs/{task_id}/{Path(comp['comparison_path']).name}"
            }
            for comp in report.get("comparisons", [])
        ],
        "elapsed_seconds": report.get("elapsed_seconds")
    }

@app.post("/api/restore/analyze")
async def restore_analyze(file: UploadFile = File(...)):
    """Step 1: Analyze text regions and correct glitches using Dual VLM."""
    task_id = uuid.uuid4().hex[:12]
    task_dir = output_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    in_file = task_dir / "input.png"
    with open(in_file, "wb") as f:
        shutil.copyfileobj(file.file, f)

    regions = pipeline_engine.analyze(in_file)
    return {
        "task_id": task_id,
        "regions": [r.to_dict() for r in regions]
    }

class InpaintRequest(BaseModel):
    image_url: str
    regions: List[Dict[str, Any]]

@app.post("/api/restore/inpaint")
def restore_inpaint(req: InpaintRequest):
    """Step 2: Generate clean inpainted background image based on regions' clean_bbox."""
    rel_path = req.image_url.replace("/api/storage/", "")
    full_path = storage_root / rel_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="원본 이미지를 찾을 수 없습니다.")

    orig_img = Image.open(full_path)
    regions = [TextRegion.from_dict(r) for r in req.regions]

    inpainted = pipeline_engine.inpaint(orig_img, regions)
    
    out_id = f"bg_{uuid.uuid4().hex[:8]}.png"
    save_path = output_dir / out_id
    inpainted.save(save_path)

    return {
        "background_image_url": f"/api/storage/outputs/{out_id}"
    }

class RenderRequest(BaseModel):
    background_image_url: str
    original_image_url: Optional[str] = None
    regions: List[Dict[str, Any]]
    text_layer_image: Optional[str] = None

@app.post("/api/restore/render")
def restore_render(req: RenderRequest):
    """Step 3: High resolution composite rendering unified with WYSIWYG Canvas."""
    bg_rel = req.background_image_url.replace("/api/storage/", "")
    bg_full = storage_root / bg_rel
    if not bg_full.exists():
        raise HTTPException(status_code=404, detail="배경 이미지를 찾을 수 없습니다.")

    orig_bgr = None
    orig_img = None
    if req.original_image_url:
        orig_rel = req.original_image_url.replace("/api/storage/", "")
        orig_full = storage_root / orig_rel
        if orig_full.exists():
            orig_bgr = cv2.imread(str(orig_full))
            orig_img = Image.open(orig_full)

    regions = [TextRegion.from_dict(r) for r in req.regions]

    # 사용자 마스킹 영역 확장/이동 반영: 원본 이미지가 존재할 경우 최신 regions 기준으로 배경 재인페인팅
    new_bg_url = None
    if orig_img is not None:
        bg_img = pipeline_engine.inpaint(orig_img, regions)
        bg_out_id = f"bg_{uuid.uuid4().hex[:8]}.png"
        bg_img.save(output_dir / bg_out_id)
        new_bg_url = f"/api/storage/outputs/{bg_out_id}"
    else:
        bg_img = Image.open(bg_full)
        bg_img = pipeline_engine.inpaint(bg_img, regions)

    # 100% WYSIWYG Unification: If client canvas supplied exact text layer, composite directly
    rendered = None
    if req.text_layer_image:
        try:
            b64_data = req.text_layer_image
            if "base64," in b64_data:
                b64_data = b64_data.split("base64,")[1]
            layer_bytes = base64.b64decode(b64_data)
            layer_img = Image.open(io.BytesIO(layer_bytes)).convert("RGBA")

            if layer_img.size != bg_img.size:
                layer_img = layer_img.resize(bg_img.size, Image.Resampling.LANCZOS)

            composite_canvas = bg_img.convert("RGBA")
            composite_canvas.alpha_composite(layer_img)
            rendered = composite_canvas.convert("RGB")
            logger.info("[Render Unified] Successfully composited high-res WYSIWYG Canvas text layer directly.")
        except Exception as e:
            logger.warning(f"[Render Unified] Error compositing text_layer_image: {e}, falling back to pipeline_engine.render")
            rendered = None

    if rendered is None:
        rendered = pipeline_engine.render(bg_img, regions, orig_bgr)

    out_id = f"restored_{uuid.uuid4().hex[:8]}.png"
    save_path = output_dir / out_id
    rendered.save(save_path)

    return {
        "restored_image_url": f"/api/storage/outputs/{out_id}",
        "background_image_url": new_bg_url or req.background_image_url
    }

# ----------------- Interactive Cutout (누끼따기) -----------------
class CutoutClickRequest(BaseModel):
    image_url: str
    click_x: int
    click_y: int
    radius: Optional[int] = 160

@app.post("/api/cutout/click")
def cutout_by_click(req: CutoutClickRequest):
    """Interactive foreground extraction at clicked coordinates (x, y)."""
    rel = req.image_url.replace("/api/storage/", "")
    full_path = storage_root / rel
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")

    img_bgr = cv2.imread(str(full_path))
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    rgba = CutoutService.extract_foreground_by_point(img_rgb, req.click_x, req.click_y, radius=req.radius or 160)
    
    out_id = f"cutout_{uuid.uuid4().hex[:8]}.png"
    save_path = output_dir / out_id
    Image.fromarray(rgba).save(save_path, format="PNG")

    return {
        "cutout_url": f"/api/storage/outputs/{out_id}",
        "click": {"x": req.click_x, "y": req.click_y}
    }

# ----------------- On-Premise Local VLM Health & Queue Status -----------------
@app.get("/api/strata/status")
def get_strata_status():
    """Returns local Strata VLM server online status, real-time lock/busy state, and queue info."""
    return vlm_lock_manager.get_status()

# ----------------- Frontend Static Files & SPA Fallback -----------------
def _get_dist_dir() -> Optional[Path]:
    from fixit_api.config import _ROOT
    candidates = [
        Path("/app/dist"),  # Docker container production build
        _ROOT / "apps" / "web" / "dist",  # Local repo build
        Path(__file__).resolve().parent.parent / "dist",  # apps/api/dist
    ]
    for c in candidates:
        if c.exists() and (c / "index.html").exists():
            return c
    return None

frontend_dist = _get_dist_dir()
if frontend_dist:
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="web_assets")
    fonts_dir = frontend_dist / "fonts"
    if fonts_dir.exists():
        app.mount("/fonts", StaticFiles(directory=str(fonts_dir)), name="web_fonts")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Do not hijack API or docs endpoints
        if full_path.startswith("api/") or full_path == "api" or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404, detail="API route not found")
        target_file = frontend_dist / full_path
        if target_file.is_file():
            return FileResponse(target_file)
        return FileResponse(frontend_dist / "index.html")
