"""AWS S3 service for asynchronous file operations using aioboto3."""

from typing import Optional
import io
import structlog
import aioboto3
from botocore.exceptions import ClientError

logger = structlog.get_logger(__name__)


class S3Service:
    """Async S3 client service for document storage and retrieval."""

    def __init__(self, bucket: str, region: str = "us-east-1", endpoint_url: Optional[str] = None):
        """Initialize S3 service.
        
        Args:
            bucket: S3 bucket name.
            region: AWS region (default: us-east-1).
            endpoint_url: Override endpoint URL (for LocalStack or other S3-compatible services).
        """
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.session = aioboto3.Session()

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None
    ) -> str:
        """Upload a file to S3.
        
        Args:
            file_bytes: File content as bytes.
            filename: Filename to use in S3 (can include path prefix).
            content_type: MIME type.
            metadata: Optional metadata dict to store with the object.
            
        Returns:
            S3 URL of the uploaded object.
            
        Raises:
            ClientError: If upload fails.
        """
        try:
            async with self.session.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url
            ) as client:
                # Prepare metadata
                s3_metadata = metadata or {}
                extra_args = {
                    "ContentType": content_type,
                    "Metadata": s3_metadata,
                }

                # Upload
                await client.put_object(
                    Bucket=self.bucket,
                    Key=filename,
                    Body=file_bytes,
                    **extra_args
                )

                logger.info("File uploaded to S3", bucket=self.bucket, key=filename, size=len(file_bytes))

                # Build S3 URL (use endpoint_url if override is set for LocalStack)
                if self.endpoint_url:
                    s3_url = f"{self.endpoint_url}/{self.bucket}/{filename}"
                else:
                    s3_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{filename}"

                return s3_url

        except ClientError as e:
            logger.error("S3 upload failed", bucket=self.bucket, key=filename, error=str(e))
            raise

    async def download_file(self, filename: str) -> bytes:
        """Download a file from S3.
        
        Args:
            filename: S3 key (filename).
            
        Returns:
            File content as bytes.
            
        Raises:
            ClientError: If download fails.
        """
        try:
            async with self.session.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url
            ) as client:
                response = await client.get_object(Bucket=self.bucket, Key=filename)
                content = await response["Body"].read()

                logger.info("File downloaded from S3", bucket=self.bucket, key=filename, size=len(content))
                return content

        except ClientError as e:
            logger.error("S3 download failed", bucket=self.bucket, key=filename, error=str(e))
            raise

    async def delete_file(self, filename: str) -> bool:
        """Delete a file from S3.
        
        Args:
            filename: S3 key (filename).
            
        Returns:
            True if deleted successfully.
            
        Raises:
            ClientError: If deletion fails.
        """
        try:
            async with self.session.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url
            ) as client:
                await client.delete_object(Bucket=self.bucket, Key=filename)

                logger.info("File deleted from S3", bucket=self.bucket, key=filename)
                return True

        except ClientError as e:
            logger.error("S3 deletion failed", bucket=self.bucket, key=filename, error=str(e))
            raise

    async def generate_presigned_url(
        self,
        filename: str,
        expiry_seconds: int = 3600
    ) -> str:
        """Generate a presigned URL for temporary S3 access.
        
        Args:
            filename: S3 key (filename).
            expiry_seconds: How long the URL is valid (default: 1 hour).
            
        Returns:
            Presigned URL string.
            
        Raises:
            ClientError: If URL generation fails.
        """
        try:
            async with self.session.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url
            ) as client:
                url = await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": filename},
                    ExpiresIn=expiry_seconds
                )

                logger.debug("Presigned URL generated", bucket=self.bucket, key=filename, expires_in=expiry_seconds)
                return url

        except ClientError as e:
            logger.error("Presigned URL generation failed", bucket=self.bucket, key=filename, error=str(e))
            raise

    async def list_files(self, prefix: str = "") -> list:
        """List files in S3 bucket with optional prefix filter.
        
        Args:
            prefix: Optional S3 key prefix to filter by.
            
        Returns:
            List of dicts with {Key, Size, LastModified, ...}.
            
        Raises:
            ClientError: If listing fails.
        """
        try:
            async with self.session.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url
            ) as client:
                paginator = client.get_paginator("list_objects_v2")
                pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)

                files = []
                async for page in pages:
                    if "Contents" in page:
                        files.extend(page["Contents"])

                logger.info("Files listed from S3", bucket=self.bucket, prefix=prefix, count=len(files))
                return files

        except ClientError as e:
            logger.error("S3 listing failed", bucket=self.bucket, prefix=prefix, error=str(e))
            raise


# Global S3 service instance
_s3_service: Optional[S3Service] = None


def get_s3_service() -> S3Service:
    """Get or create the global S3 service instance."""
    global _s3_service
    if _s3_service is None:
        from app.config import settings
        _s3_service = S3Service(
            bucket=settings.aws_s3_bucket,
            region=settings.aws_s3_region,
            endpoint_url=settings.aws_endpoint_url if settings.aws_endpoint_url else None
        )
    return _s3_service
