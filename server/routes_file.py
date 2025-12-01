"""Routes for file-based genre prediction."""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from server.predict import Predictor
from server.schemas import BPMBulkResponse, BPMResult

logger = logging.getLogger(__name__)

# Constants
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".aiff")

router = APIRouter(prefix="/predict", tags=["predict"])
_predictor = Predictor.load()


def _validate_audio_file(file: UploadFile) -> None:
    if not file.filename.lower().endswith(SUPPORTED_AUDIO_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported file type. Supported types: "
                f"{', '.join(ext.upper()[1:] for ext in SUPPORTED_AUDIO_EXTENSIONS)}"
            ),
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
    _validate_audio_file(file)
    try:
        data = await file.read()
        # Await async predictor
        result: BPMResult = await _predictor.predict_bytes(data, filename=file.filename)
        return result
    except Exception as e:
        logger.error(f"Failed to process audio: {str(e)}")
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
        _validate_audio_file(file)
        try:
            data = await file.read()
            result: BPMResult = await _predictor.predict_bytes(data, filename=file.filename)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to process audio: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to process audio: {str(e)}"
            )
    total_analysis_time = sum(r.analysis_time for r in results)
    return BPMBulkResponse(results=results, analysis_time=total_analysis_time)
