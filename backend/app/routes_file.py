"""Routes for file-based genre prediction."""

import asyncio
import logging

import filetype
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from backend.app.predict import Predictor
from backend.app.schemas import BPMBulkResponse, BPMResult

logger = logging.getLogger(__name__)

# Constants
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".aiff")
SUPPORTED_AUDIO_MIME_TYPES = frozenset(
    [
        "audio/mpeg",          # MP3
        "audio/x-wav",         # WAV
        "audio/x-flac",        # FLAC
        "audio/aiff",          # AIFF
        "audio/x-aiff",        # AIFF variant
    ]
)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_BATCH_SIZE = 20

router = APIRouter(prefix="/predict", tags=["predict"])


def _validate_audio_file(file: UploadFile, data: bytes) -> None:
    """Validate that the uploaded file is a supported audio format.

    Checks file size, filename extension, and the actual file content (magic bytes).

    Args:
        file: The uploaded file object.
        data: The already-read file bytes.

    Raises:
        HTTPException: If the file is too large, the filename is missing, the extension
            is unsupported, or the file content does not match a known audio MIME type.
    """
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )
    filename = file.filename
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )
    if not filename.lower().endswith(SUPPORTED_AUDIO_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported file type. Supported types: "
                f"{', '.join(ext.upper()[1:] for ext in SUPPORTED_AUDIO_EXTENSIONS)}"
            ),
        )
    kind = filetype.guess(data)
    detected_mime = kind.mime if kind else None
    if detected_mime not in SUPPORTED_AUDIO_MIME_TYPES:
        logger.warning("Rejected upload '%s': detected MIME type '%s'", filename, detected_mime)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File content does not appear to be a supported audio format (detected: {detected_mime}).",
        )


@router.post("/file", response_model=BPMResult, status_code=status.HTTP_200_OK)
async def predict_file(
    request: Request,
    file: UploadFile = File(...),
) -> BPMResult:
    """Analyze BPM from an audio file and return a BPMResult.

    Args:
        request: The incoming HTTP request (used to access app state).
        file: Audio file to analyze (WAV, FLAC, AIFF, or MP3)

    Returns:
        BPMResult: Estimated tempo for the file (in BPM)

    Raises:
        HTTPException: If file type is unsupported or processing fails
    """
    predictor: Predictor = request.app.state.predictor
    try:
        data = await file.read()
        _validate_audio_file(file, data)
        result: BPMResult = await predictor.predict_bytes(data, filename=file.filename or "unknown")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to process audio file '%s': %s", file.filename, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to process audio: {str(e)}"
        )


@router.post("/files", response_model=BPMBulkResponse, status_code=status.HTTP_200_OK)
async def predict_files(
    request: Request,
    files: list[UploadFile] = File(...),
) -> BPMBulkResponse:
    """Analyze BPM from a list of audio files and return a BPMBulkResponse.

    Args:
        request: The incoming HTTP request (used to access app state).
        files: List of audio files to analyze (WAV, FLAC, AIFF, or MP3)

    Returns:
        BPMBulkResponse: List of BPM analysis results for each submitted file

    Raises:
        HTTPException: If no files are uploaded, the batch is too large,
            a file type is unsupported, or processing fails.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded for processing."
        )
    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Too many files. Maximum batch size is {MAX_BATCH_SIZE}.",
        )

    predictor: Predictor = request.app.state.predictor

    async def _process_one(file: UploadFile) -> BPMResult:
        try:
            data = await file.read()
            _validate_audio_file(file, data)
            return await predictor.predict_bytes(data, filename=file.filename or "unknown")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to process audio file '%s': %s", file.filename, e)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to process audio: {str(e)}"
            )

    results: list[BPMResult] = list(await asyncio.gather(*[_process_one(f) for f in files]))
    total_analysis_time = sum(r.analysis_time for r in results)
    return BPMBulkResponse(results=results, analysis_time=total_analysis_time)
