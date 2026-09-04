"""Routes for file-based genre prediction."""

import asyncio
import logging
from typing import TYPE_CHECKING

import filetype
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from backend.app.schemas import BPMBulkResponse, BPMResult

if TYPE_CHECKING:
    from backend.app.predict import Predictor

logger = logging.getLogger(__name__)

# Constants
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".flac", ".mp3", ".aiff")
SUPPORTED_AUDIO_MIME_TYPES = frozenset(
    [
        "audio/mpeg",  # MP3
        "audio/x-wav",  # WAV
        "audio/x-flac",  # FLAC
        "audio/aiff",  # AIFF
        "audio/x-aiff",  # AIFF variant
    ]
)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

# Ceiling on the whole request body, enforced from Content-Length before the
# multipart parser runs and again while reading. Without it a batch of N files
# could legitimately declare N * MAX_FILE_SIZE_BYTES, and every byte would be
# spooled to the pod's disk before any per-file check could reject it.
#
# 100 MB matches the request-body limit Cloudflare imposes on Free/Pro plans, so
# a larger body would be rejected at the edge anyway once the tunnel is live.
MAX_REQUEST_BYTES = 100 * 1024 * 1024  # 100 MB

MAX_BATCH_SIZE = 20

# Read granularity when streaming an upload. Small enough that the cap is caught
# promptly, large enough not to make a 50 MB file thousands of awaits.
READ_CHUNK_BYTES = 1024 * 1024  # 1 MB

# How much of the file's head is needed to identify the container from its magic
# bytes. `filetype` looks at a handful of leading bytes; 8 KB is generous.
MAGIC_PREFIX_BYTES = 8192

router = APIRouter(prefix="/predict", tags=["predict"])


class _ByteBudget:
    """Shared cap on the total bytes a single request may pull into memory.

    One instance is shared by every file in a batch, so concurrent reads are
    bounded in aggregate rather than only per file. `asyncio.gather` interleaves
    the readers, but `take` does not await, so its check-and-increment cannot be
    interrupted between the two.
    """

    def __init__(self, limit: int) -> None:
        """Start an unspent budget of ``limit`` bytes."""
        self.limit = limit
        self.used = 0

    def take(self, count: int) -> None:
        """Charge ``count`` bytes against the budget.

        Args:
            count: Number of bytes just read.

        Raises:
            HTTPException: 413 once the request exceeds the total cap.
        """
        self.used += count
        if self.used > self.limit:
            raise HTTPException(
                status_code=413,
                detail=(f"Upload too large. Maximum total request size is {self.limit // (1024 * 1024)} MB."),
            )


def reject_oversized_request(content_length: str | None) -> None:
    """Reject a request whose declared body exceeds the total cap.

    Called from middleware so it runs before the multipart parser touches the
    body. A missing or unparseable Content-Length is not an error here: the
    streaming cap in `_read_capped` still bounds such requests.

    Args:
        content_length: Raw Content-Length header value, if the client sent one.

    Raises:
        HTTPException: 413 if the declared length exceeds MAX_REQUEST_BYTES.
    """
    if content_length is None:
        return
    try:
        declared = int(content_length)
    except ValueError:
        return
    if declared > MAX_REQUEST_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Upload too large. Maximum total request size is {MAX_REQUEST_BYTES // (1024 * 1024)} MB."
            ),
        )


def _validate_filename(file: UploadFile) -> str:
    """Check the upload has a filename with a supported audio extension.

    Args:
        file: The uploaded file object.

    Returns:
        The validated filename.

    Raises:
        HTTPException: If the filename is missing or the extension is unsupported.
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
    return filename


def _validate_magic_bytes(filename: str, prefix: bytes) -> None:
    """Check the file's leading bytes identify a supported audio container.

    Runs on the first chunk rather than the whole upload, so a file that is not
    audio is rejected after ~8 KB instead of after the full 50 MB.

    Args:
        filename: Name of the upload, for logging.
        prefix: Leading bytes of the file.

    Raises:
        HTTPException: 415 if the content is not a supported audio format.
    """
    kind = filetype.guess(prefix)
    detected_mime = kind.mime if kind else None
    if detected_mime not in SUPPORTED_AUDIO_MIME_TYPES:
        logger.warning("Rejected upload '%s': detected MIME type '%s'", filename, detected_mime)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File content does not appear to be a supported audio format (detected: {detected_mime})."
            ),
        )


async def _read_capped(file: UploadFile, filename: str, budget: _ByteBudget) -> bytes:
    """Read an upload in chunks, aborting as soon as it exceeds a cap.

    The magic-byte check runs on the first chunk, so non-audio uploads are
    rejected before the rest of the body is buffered. Bytes are charged to the
    shared request budget as they are read, which bounds a whole batch and not
    merely each file within it.

    Args:
        file: The uploaded file object.
        filename: Validated filename, for error messages and logging.
        budget: Shared per-request byte budget.

    Returns:
        The file's bytes.

    Raises:
        HTTPException: 413 if the file or the request exceeds its cap, or 415 if
            the content is not a supported audio format.
    """
    chunks: list[bytes] = []
    total = 0
    checked_magic = False

    while True:
        chunk = await file.read(READ_CHUNK_BYTES)
        if not chunk:
            break

        total += len(chunk)
        if total > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File too large. Maximum allowed size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                ),
            )
        budget.take(len(chunk))
        chunks.append(chunk)

        if not checked_magic and total >= MAGIC_PREFIX_BYTES:
            _validate_magic_bytes(filename, b"".join(chunks)[:MAGIC_PREFIX_BYTES])
            checked_magic = True

    data = b"".join(chunks)
    # Files shorter than the prefix never reached the check inside the loop.
    if not checked_magic:
        _validate_magic_bytes(filename, data)
    return data


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
    budget = _ByteBudget(MAX_REQUEST_BYTES)
    try:
        filename = _validate_filename(file)
        data = await _read_capped(file, filename, budget)
        result: BPMResult = await predictor.predict_bytes(data, filename=filename)
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
            status_code=413,
            detail=f"Too many files. Maximum batch size is {MAX_BATCH_SIZE}.",
        )

    predictor: Predictor = request.app.state.predictor
    # One budget for the whole batch, so concurrent readers are bounded in
    # aggregate rather than each being free to buffer MAX_FILE_SIZE_BYTES.
    budget = _ByteBudget(MAX_REQUEST_BYTES)

    async def _process_one(file: UploadFile) -> BPMResult:
        try:
            filename = _validate_filename(file)
            data = await _read_capped(file, filename, budget)
            return await predictor.predict_bytes(data, filename=filename)
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
