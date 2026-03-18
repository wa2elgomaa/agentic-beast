"""Service for managing file storage in S3."""

from datetime import datetime, timedelta
from typing import Optional
import io

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


class FileStorageService:
    """Service for uploading, downloading, and managing files in S3."""

    def __init__(self):
        """Initialize S3 client."""
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix

        # Create S3 client
        s3_kwargs = {
            "region_name": settings.aws_region,
        }

        # Add credentials if provided
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            s3_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            s3_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

        # Add endpoint URL if provided (for localstack or S3-compatible services)
        if settings.s3_endpoint_url:
            s3_kwargs["endpoint_url"] = settings.s3_endpoint_url

        self.s3_client = boto3.client("s3", **s3_kwargs)

    def upload_file(
        self,
        file_data: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        task_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Upload a file to S3.

        Args:
            file_data: Raw file bytes.
            filename: Original filename.
            content_type: MIME type.
            task_id: Optional task ID for organizational prefix.
            metadata: Optional metadata dict to store with the file.

        Returns:
            S3 key (path) of the uploaded file.

        Raises:
            Exception: If upload fails.
        """
        try:
            # Generate S3 key
            if task_id:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                s3_key = f"{self.prefix}/{task_id}/{timestamp}_{filename}"
            else:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                s3_key = f"{self.prefix}/{timestamp}_{filename}"

            logger.info(f"Uploading file to S3", s3_key=s3_key, filename=filename, size=len(file_data))

            # Prepare metadata
            extra_args = {
                "ContentType": content_type,
            }

            if metadata:
                extra_args["Metadata"] = metadata

            # Upload file
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=file_data,
                **extra_args,
            )

            logger.info(f"File uploaded successfully", s3_key=s3_key)
            return s3_key

        except ClientError as e:
            logger.error(f"Failed to upload file to S3", error=str(e), s3_key=s3_key)
            raise Exception(f"S3 upload failed: {str(e)}")

    def download_file(self, s3_key: str) -> bytes:
        """Download a file from S3.

        Args:
            s3_key: S3 key (path) of the file.

        Returns:
            File contents as bytes.

        Raises:
            Exception: If download fails or file not found.
        """
        try:
            logger.info(f"Downloading file from S3", s3_key=s3_key)

            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            file_data = response["Body"].read()

            logger.info(f"File downloaded successfully", s3_key=s3_key, size=len(file_data))
            return file_data

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.error(f"File not found in S3", s3_key=s3_key)
                raise Exception(f"File not found: {s3_key}")
            logger.error(f"Failed to download file from S3", error=str(e), s3_key=s3_key)
            raise Exception(f"S3 download failed: {str(e)}")

    def generate_presigned_url(self, s3_key: str, expiration_seconds: int = 3600) -> str:
        """Generate a presigned URL for a file.

        Args:
            s3_key: S3 key (path) of the file.
            expiration_seconds: URL expiration time in seconds.

        Returns:
            Presigned URL as string.

        Raises:
            Exception: If generation fails.
        """
        try:
            logger.info(f"Generating presigned URL", s3_key=s3_key, expiration_seconds=expiration_seconds)

            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": s3_key},
                ExpiresIn=expiration_seconds,
            )

            logger.info(f"Presigned URL generated successfully", s3_key=s3_key)
            return url

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL", error=str(e), s3_key=s3_key)
            raise Exception(f"Presigned URL generation failed: {str(e)}")

    def delete_file(self, s3_key: str) -> None:
        """Delete a file from S3.

        Args:
            s3_key: S3 key (path) of the file.

        Raises:
            Exception: If deletion fails.
        """
        try:
            logger.info(f"Deleting file from S3", s3_key=s3_key)

            self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)

            logger.info(f"File deleted successfully", s3_key=s3_key)

        except ClientError as e:
            logger.error(f"Failed to delete file from S3", error=str(e), s3_key=s3_key)
            raise Exception(f"S3 deletion failed: {str(e)}")

    def get_file_info(self, s3_key: str) -> dict:
        """Get metadata about a file in S3.

        Args:
            s3_key: S3 key (path) of the file.

        Returns:
            Dict with file size, last modified, content type, etc.

        Raises:
            Exception: If file not found or request fails.
        """
        try:
            logger.info(f"Getting file info from S3", s3_key=s3_key)

            response = self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)

            info = {
                "size": response["ContentLength"],
                "last_modified": response["LastModified"],
                "content_type": response.get("ContentType", "application/octet-stream"),
                "metadata": response.get("Metadata", {}),
            }

            logger.info(f"File info retrieved", s3_key=s3_key, size=info["size"])
            return info

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.error(f"File not found in S3", s3_key=s3_key)
                raise Exception(f"File not found: {s3_key}")
            logger.error(f"Failed to get file info from S3", error=str(e), s3_key=s3_key)
            raise Exception(f"Failed to get file info: {str(e)}")


# Global instance
_file_storage_service: Optional[FileStorageService] = None


def get_file_storage_service() -> FileStorageService:
    """Get or create the global file storage service instance."""
    global _file_storage_service
    if _file_storage_service is None:
        _file_storage_service = FileStorageService()
    return _file_storage_service
