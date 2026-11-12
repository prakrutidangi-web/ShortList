from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from shortlist_api.deps import get_cached_encoder, get_session, get_user_id
from shortlist_api.schemas import DeleteOut, DocumentPreview, ProfileIn, ProfileOut, SuggestionOut
from shortlist_ml.embeddings.encoder import Encoder
from shortlist_ml.profile import resume as resume_mod
from shortlist_ml.profile import service
from shortlist_ml.profile.build import profile_document, suggest_from_text

router = APIRouter(prefix="/profile", tags=["profile"])


def _to_input(body: ProfileIn) -> service.ProfileInput:
    return service.ProfileInput(
        skills=body.skills, target_roles=body.target_roles, target_locations=body.target_locations,
        remote_ok=body.remote_ok, grad_date=body.grad_date, needs_sponsorship=body.needs_sponsorship,
        about_text=body.about_text,
    )  # fmt: skip


@router.get("", response_model=ProfileOut)
def read_profile(
    session: Annotated[Session, Depends(get_session)], user_id: Annotated[int, Depends(get_user_id)]
) -> ProfileOut:
    row = service.get_profile(session, user_id)
    if row is None:
        raise HTTPException(404, "no profile yet")
    return ProfileOut(
        skills=row.skills, target_roles=row.target_roles, target_locations=row.target_locations,
        remote_ok=row.remote_ok, grad_date=row.grad_date, needs_sponsorship=row.needs_sponsorship,
        about_text=row.about_text, profile_document=row.profile_document, updated_at=row.updated_at,
    )  # fmt: skip


@router.post("/resume", response_model=SuggestionOut)
async def suggest_from_resume(
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form()] = None,
) -> SuggestionOut:
    """Parse an uploaded PDF or pasted text IN MEMORY and return suggestions. Nothing is stored or logged."""
    try:
        if file is not None:
            data = await file.read(resume_mod.MAX_PDF_BYTES + 1)
            body, source = resume_mod.extract_pdf_text(data), "pdf"
        elif text is not None:
            body, source = resume_mod.pasted_text(text), "text"
        else:
            raise resume_mod.ResumeError("missing", "Upload a PDF or paste your resume text.")
    except resume_mod.ResumeError as exc:
        raise HTTPException(422, {"code": exc.code, "message": exc.message}) from exc
    s = suggest_from_text(body)
    return SuggestionOut(
        source=source,
        characters_read=len(body),
        skills=s.skills,
        grad_date=s.grad_date,
        grad_date_evidence=s.grad_date_evidence,
    )


@router.post("/preview-document", response_model=DocumentPreview)
def preview_document(body: ProfileIn) -> DocumentPreview:
    """The exact text that would be embedded for this profile (shown to the user before saving)."""
    try:
        v = service.validate(_to_input(body))
    except service.ProfileValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return DocumentPreview(
        profile_document=profile_document(v.skills, v.target_roles, v.about_text, v.grad_date)
    )


@router.put("", response_model=ProfileOut)
def save_profile(
    body: ProfileIn,
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[int, Depends(get_user_id)],
    encoder: Annotated[Encoder, Depends(get_cached_encoder)],
) -> ProfileOut:
    try:
        row = service.save_profile(session, user_id, _to_input(body), encoder)
    except service.ProfileValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ProfileOut(
        skills=row.skills, target_roles=row.target_roles, target_locations=row.target_locations,
        remote_ok=row.remote_ok, grad_date=row.grad_date, needs_sponsorship=row.needs_sponsorship,
        about_text=row.about_text, profile_document=row.profile_document, updated_at=row.updated_at,
    )  # fmt: skip


@router.delete("", response_model=DeleteOut)
def delete_profile(
    session: Annotated[Session, Depends(get_session)], user_id: Annotated[int, Depends(get_user_id)]
) -> DeleteOut:
    """Delete the profile, everything derived from the resume, and the profile embedding."""
    return DeleteOut(deleted=service.delete_profile(session, user_id))
