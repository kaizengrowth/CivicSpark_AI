import logging
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)


class CivicSparkException(Exception):
    """Base exception class for CivicSpark AI application"""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(CivicSparkException):
    """Raised when input validation fails"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class NotFoundError(CivicSparkException):
    """Raised when a requested resource is not found"""

    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            error_code="NOT_FOUND",
            details={"resource": resource, "identifier": str(identifier)},
            status_code=status.HTTP_404_NOT_FOUND,
        )


class AuthenticationError(CivicSparkException):
    """Raised when authentication fails"""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class AuthorizationError(CivicSparkException):
    """Raised when user lacks permission for an action"""

    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ServiceUnavailableError(CivicSparkException):
    """Raised when an external service is unavailable"""

    def __init__(self, service: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=f"Service unavailable: {service}",
            error_code="SERVICE_UNAVAILABLE",
            details=details,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def civicspark_exception_handler(
    request: Request, exc: CivicSparkException
) -> JSONResponse:
    """Handle CivicSpark-specific exceptions"""
    logger.error(f"CivicSpark exception: {exc.message}", exc_info=True)

    error_response = ErrorResponse(
        error=exc.message, error_code=exc.error_code, details=exc.details
    )

    return JSONResponse(status_code=exc.status_code, content=error_response.dict())


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions"""
    logger.error(f"HTTP exception: {exc.detail}")

    error_response = ErrorResponse(error=exc.detail, error_code="HTTP_ERROR")

    return JSONResponse(status_code=exc.status_code, content=error_response.dict())


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle Pydantic validation exceptions"""
    logger.error(f"Validation exception: {str(exc)}")

    error_response = ErrorResponse(
        error="Validation error",
        error_code="VALIDATION_ERROR",
        details={"message": str(exc)},
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=error_response.dict()
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)

    error_response = ErrorResponse(
        error="Internal server error", error_code="INTERNAL_ERROR"
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_response.dict()
    )
