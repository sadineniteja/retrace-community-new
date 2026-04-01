"""
Brain File Upload API — upload and manage files (resumes, documents, etc.) for brains.
"""

import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, CurrentUser
from app.db.database import get_session
from app.services.brain_manager import brain_manager

logger = structlog.get_logger()
router = APIRouter()

# Upload directory — stored relative to backend root
UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "brain_files"

# Allowed MIME types / extensions
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".rtf",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".csv", ".xlsx", ".xls", ".json",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _ensure_upload_dir(brain_id: str) -> Path:
    """Create the upload directory for a brain if it doesn't exist."""
    brain_dir = UPLOAD_DIR / brain_id
    brain_dir.mkdir(parents=True, exist_ok=True)
    return brain_dir


@router.post("/{brain_id}/files")
async def upload_brain_file(
    brain_id: str,
    file: UploadFile = File(...),
    question_key: str = Form(default=""),
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload a file for a brain (e.g. resume during interview setup)."""
    # Verify brain belongs to user
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read and check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")

    # Save file
    file_id = str(uuid4())[:12]
    safe_filename = f"{file_id}_{file.filename.replace(' ', '_')}"
    brain_dir = _ensure_upload_dir(brain_id)
    file_path = brain_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(content)

    file_info = {
        "file_id": file_id,
        "filename": file.filename,
        "stored_filename": safe_filename,
        "size": len(content),
        "content_type": file.content_type or "application/octet-stream",
        "question_key": question_key,
        "path": str(file_path),
    }

    logger.info("Brain file uploaded", brain_id=brain_id, filename=file.filename, size=len(content))

    return file_info


@router.get("/{brain_id}/files")
async def list_brain_files(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all uploaded files for a brain."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    brain_dir = UPLOAD_DIR / brain_id
    if not brain_dir.exists():
        return []

    files = []
    for f in brain_dir.iterdir():
        if f.is_file():
            stat = f.stat()
            # Extract original filename (after the file_id prefix)
            parts = f.name.split("_", 1)
            original_name = parts[1] if len(parts) > 1 else f.name
            files.append({
                "file_id": parts[0] if len(parts) > 1 else f.stem,
                "filename": original_name.replace("_", " "),
                "stored_filename": f.name,
                "size": stat.st_size,
                "path": str(f),
            })

    return files


@router.delete("/{brain_id}/files/{file_id}")
async def delete_brain_file(
    brain_id: str,
    file_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a specific uploaded file."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    brain_dir = UPLOAD_DIR / brain_id
    if not brain_dir.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Find file by file_id prefix
    for f in brain_dir.iterdir():
        if f.name.startswith(file_id):
            f.unlink()
            return {"deleted": True, "file_id": file_id}

    raise HTTPException(status_code=404, detail="File not found")
