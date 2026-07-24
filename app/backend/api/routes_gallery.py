from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.core import gallery

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


@router.get("")
def list_folders() -> list[dict]:
    return gallery.list_folders()


@router.get("/{job_id}")
def list_files(job_id: str) -> dict:
    try:
        return gallery.list_files(job_id)
    except gallery.GalleryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{job_id}")
def delete_folder(job_id: str) -> dict:
    try:
        gallery.delete_folder(job_id)
    except gallery.GalleryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.delete("/{job_id}/clips/{clip_id}")
def delete_file(job_id: str, clip_id: str) -> dict:
    try:
        gallery.delete_file(job_id, clip_id)
    except gallery.GalleryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{job_id}/reveal")
def reveal_folder(job_id: str) -> dict:
    try:
        gallery.reveal_folder(job_id)
    except gallery.GalleryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{job_id}/clips/{clip_id}/reveal")
def reveal_file(job_id: str, clip_id: str) -> dict:
    try:
        gallery.reveal_file(job_id, clip_id)
    except gallery.GalleryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
