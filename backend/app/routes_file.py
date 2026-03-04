"""Routes for file-based genre prediction."""

import logging

import filetype
from fastapi import APIRouter, File, HTTPException, UploadFile, status

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

router = APIRouter(prefix="/predict", tags=["predict"])
_predictor = Predictor.load()


def _validate_audio_file(file: UploadFile, data: bytes) -> None:
    """Validate that the uploaded file is a supported audio format.

    Checks both the filename extension and the actual file content (magic bytes).

    Args:
        file: The uploaded file object.
        data: The already-read file bytes.

    Raises:
        HTTPException: If the filename is missing, the extension is unsupported,
            or the file content does not match a known audio MIME type.
    """
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
    file: UploadFile = File(...),
) -> BPMResult:
    """Analyze BPM from an audio file and return a BPMResult.

    Args:
        file: Audio file to analyze (WAV, FLAC, OGG, or MP3)

    Returns:
        BPMResult: Estimated tempo for the file (in BPM)

    Raises:
        HTTPException: If file type is unsupported or processing fails
    """
    try:
        data = await file.read()
        _validate_audio_file(file, data)
        result: BPMResult = await _predictor.predict_bytes(data, filename=file.filename or "unknown")
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
    files: list[UploadFile] = File(...),
) -> BPMBulkResponse:
    """Analyze BPM from a list of audio files and return a BPMBulkResponse.

    Args:
        files: List of audio files to analyze (WAV, FLAC, OGG, or MP3)

    Returns:
        BPMBulkResponse: List of BPM analysis results for each submitted file
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded for processing."
        )
    results = []
    for file in files:
        try:
            data = await file.read()
            _validate_audio_file(file, data)
            result: BPMResult = await _predictor.predict_bytes(data, filename=file.filename or "unknown")
            results.append(result)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to process audio file '%s': %s", file.filename, e)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to process audio: {str(e)}"
            )
    total_analysis_time = sum(r.analysis_time for r in results)
    return BPMBulkResponse(results=results, analysis_time=total_analysis_time)
