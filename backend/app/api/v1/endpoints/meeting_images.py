from pathlib import Path

from app.core.config import settings
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

# NOTE: This endpoint is primarily for backward compatibility.
# New meeting images are served directly from GitHub raw URLs.
IMAGES_BASE_DIR = Path(settings.storage_dir) / "meeting-images"


@router.get("/{year}/{month}/{day}/{meeting_folder}/{image_name}")
async def get_meeting_image(
    year: int, month: int, day: int, meeting_folder: str, image_name: str
):
    """Serve meeting document images"""
    try:
        # Construct the full file path from parameters
        image_path = f"{year}/{month:02d}/{day:02d}/{meeting_folder}/{image_name}"
        file_path = IMAGES_BASE_DIR / image_path

        # Security check: ensure the path is within our images directory
        if not str(file_path.resolve()).startswith(str(IMAGES_BASE_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Access forbidden")

        # Check if file exists
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Image not found")

        # Return the image file
        return FileResponse(
            path=str(file_path), media_type="image/png", filename=file_path.name
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error serving image: {str(e)}")
