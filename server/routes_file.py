"""Routes for file-based genre prediction."""

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import conint

from server.predict import Predictor
from server.schemas import PredictionResponse, PredictionResult

# Constants
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".aiff")

router = APIRouter(prefix="/predict", tags=["predict"])
_predictor = Predictor.load()


@router.post("/file", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
async def predict_file(
    file: UploadFile = File(...),
    top_k: conint(ge=1, le=10) = Query(3, description="Number of top predictions to return"),
) -> PredictionResponse:
    """Predict music genre from an audio file.

    Args:
        file: Audio file to analyze (WAV, FLAC, OGG, or MP3)
        top_k: Number of top genre predictions to return (1-10)

    Returns:
        PredictionResponse: Predicted genres and their confidence scores

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
        result: PredictionResult = _predictor.predict_bytes(data, top_k=top_k)
        # Convert to plain data to avoid nested Pydantic-instance validation issues
        resp = {
            "source": "file",
            "filename": file.filename,
            **result.model_dump(),
        }
        return PredictionResponse.model_validate(resp)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to process audio: {str(e)}"
        )
