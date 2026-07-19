"""
S3 Service for managing file uploads and downloads
"""

import logging
import os
from pathlib import Path
from typing import BinaryIO, List, Optional

from app.core.config import Settings

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    boto3 = None
    ClientError = NoCredentialsError = Exception
    BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)


class S3Service:
    """Service for managing S3 file operations"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.bucket_name = settings.aws_s3_bucket
        self.region = settings.aws_region

        # Initialize S3 client only when boto3 is installed and S3 is the
        # chosen backend; local filesystem storage is the default.
        if not BOTO3_AVAILABLE or settings.storage_backend != "s3":
            self.s3_client = None
            self.is_configured = False
            return

        try:
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                self.s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                    region_name=self.region,
                )
            else:
                # Use default credentials (IAM role, ~/.aws/credentials, etc.)
                self.s3_client = boto3.client("s3", region_name=self.region)

            self.is_configured = True
            logger.info(f"S3 service initialized for bucket: {self.bucket_name}")

        except NoCredentialsError:
            logger.warning("AWS credentials not found. S3 service disabled.")
            self.s3_client = None
            self.is_configured = False
        except Exception as e:
            logger.error(f"Error initializing S3 service: {e}")
            self.s3_client = None
            self.is_configured = False

    def upload_file(self, file_path: str, s3_key: str) -> Optional[str]:
        """
        Upload a file to S3

        Args:
            file_path: Local path to the file
            s3_key: S3 key (path) for the file

        Returns:
            S3 URL if successful, None if failed
        """
        if not self.is_configured:
            logger.error("S3 service not configured")
            return None

        try:
            # Upload file
            self.s3_client.upload_file(
                file_path,
                self.bucket_name,
                s3_key,
                ExtraArgs={"ContentType": self._get_content_type(file_path)},
            )

            # Return S3 URL
            s3_url = (
                f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            )
            logger.info(f"Successfully uploaded {file_path} to {s3_url}")
            return s3_url

        except ClientError as e:
            logger.error(f"Error uploading file to S3: {e}")
            return None

    def upload_meeting_images(
        self, local_images_dir: str, meeting_date: str, pdf_filename: str
    ) -> List[str]:
        """
        Upload all images for a meeting to S3

        Args:
            local_images_dir: Local directory containing images
            meeting_date: Meeting date in YYYY-MM-DD format
            pdf_filename: PDF filename for organizing

        Returns:
            List of S3 URLs
        """
        if not self.is_configured:
            logger.error("S3 service not configured")
            return []

        s3_urls = []
        images_dir = Path(local_images_dir)

        if not images_dir.exists():
            logger.warning(f"Images directory does not exist: {local_images_dir}")
            return []

        # Get all PNG files
        image_files = list(images_dir.glob("*.png"))

        for image_file in image_files:
            # Create S3 key: meeting-images/YYYY/MM/DD/filename/image.png
            date_parts = meeting_date.split("-")
            year, month, day = date_parts[0], date_parts[1], date_parts[2]

            s3_key = (
                f"meeting-images/{year}/{month}/{day}/{pdf_filename}/{image_file.name}"
            )

            # Upload to S3
            s3_url = self.upload_file(str(image_file), s3_key)
            if s3_url:
                s3_urls.append(s3_url)

        logger.info(f"Uploaded {len(s3_urls)} images for meeting {meeting_date}")
        return s3_urls

    def delete_file(self, s3_key: str) -> bool:
        """Delete a file from S3"""
        if not self.is_configured:
            return False

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Deleted {s3_key} from S3")
            return True
        except ClientError as e:
            logger.error(f"Error deleting file from S3: {e}")
            return False

    def file_exists(self, s3_key: str) -> bool:
        """Check if a file exists in S3"""
        if not self.is_configured:
            return False

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False

    def get_file_url(self, s3_key: str) -> str:
        """Get the public URL for an S3 file"""
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"

    def _get_content_type(self, file_path: str) -> str:
        """Get content type based on file extension"""
        extension = Path(file_path).suffix.lower()
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".json": "application/json",
        }
        return content_types.get(extension, "application/octet-stream")


class MeetingImageService:
    """Service specifically for managing meeting images"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.s3_service = S3Service(settings)
        self.use_s3 = settings.storage_backend == "s3"

    def get_image_urls(
        self, meeting_date: str, pdf_filename: str, local_dir: str
    ) -> List[str]:
        """
        Get image URLs for a meeting, using S3 in production or local API in development

        Args:
            meeting_date: Meeting date in YYYY-MM-DD format
            pdf_filename: PDF filename
            local_dir: Local directory path

        Returns:
            List of image URLs
        """
        if self.use_s3 and self.s3_service.is_configured:
            return self._get_s3_urls(meeting_date, pdf_filename, local_dir)
        else:
            return self._get_local_api_urls(meeting_date, pdf_filename, local_dir)

    def _get_s3_urls(
        self, meeting_date: str, pdf_filename: str, local_dir: str
    ) -> List[str]:
        """Get S3 URLs for meeting images"""
        # Check if images are already in S3
        date_parts = meeting_date.split("-")
        year, month, day = date_parts[0], date_parts[1], date_parts[2]

        s3_urls = []
        local_images_dir = Path(local_dir)

        if local_images_dir.exists():
            image_files = list(local_images_dir.glob("*.png"))

            for image_file in sorted(image_files):
                s3_key = f"meeting-images/{year}/{month}/{day}/{pdf_filename}/{image_file.name}"

                # Check if file exists in S3, if not upload it
                if not self.s3_service.file_exists(s3_key):
                    s3_url = self.s3_service.upload_file(str(image_file), s3_key)
                    if s3_url:
                        s3_urls.append(s3_url)
                else:
                    # File exists, just get the URL
                    s3_urls.append(self.s3_service.get_file_url(s3_key))

        return s3_urls

    def _get_local_api_urls(
        self, meeting_date: str, pdf_filename: str, local_dir: str
    ) -> List[str]:
        """Get local API URLs for meeting images"""
        local_urls = []
        local_images_dir = Path(local_dir)

        if local_images_dir.exists():
            # Convert local path to API path
            # Remove the base storage path to get relative path
            base_storage = Path(self.settings.storage_dir) / "meeting-images"
            try:
                relative_path = local_images_dir.relative_to(base_storage)

                image_files = list(local_images_dir.glob("*.png"))
                for image_file in sorted(image_files):
                    api_url = (
                        f"/api/v1/meeting-images/{relative_path}/{image_file.name}"
                    )
                    local_urls.append(api_url)

            except ValueError:
                # Path is not relative to base storage, use direct construction
                date_parts = meeting_date.split("-")
                year, month, day = date_parts[0], date_parts[1], date_parts[2]

                image_files = list(local_images_dir.glob("*.png"))
                for image_file in sorted(image_files):
                    api_url = f"/api/v1/meeting-images/{year}/{month.zfill(2)}/{day.zfill(2)}/{pdf_filename}/{image_file.name}"
                    local_urls.append(api_url)

        return local_urls
