"""Routes for file-based genre prediction."""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from server.predict import Predictor
from server.schemas import BPMResult

logger = logging.getLogger(__name__)

# Constants
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".aiff")

router = APIRouter(prefix="/predict", tags=["predict"])
_predictor = Predictor.load()


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
    if not file.filename.lower().endswith(SUPPORTED_AUDIO_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported file type. Supported types: "
                f"{', '.join(ext.upper()[1:] for ext in SUPPORTED_AUDIO_EXTENSIONS)}"
            ),
        )
    try:
        data = await file.read()
        # Just get BPMResult with filename
        result: BPMResult = _predictor.predict_bytes(data, filename=file.filename)
        return result
    except Exception as e:
        logger.info(f"Failed to process audio: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to process audio: {str(e)}"
        )
