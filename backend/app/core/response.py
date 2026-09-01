"""Unified Response Envelope and RFC 7807 Problem Normalization Models (ADR-0033)."""

from typing import Generic, TypeVar, Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field

from app.core.trace import get_trace_id

T = TypeVar("T")


def to_camel(snake_str: str) -> str:
    """Converts a snake_case string to camelCase."""
    components = snake_str.split("_")
    return components[0] + "".join(x.capitalize() for x in components[1:])


class CamelModel(BaseModel):
    """Base Pydantic model enforcing camelCase serialization over the wire."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class OffsetPaginationDescriptor(CamelModel):
    """Offset pagination descriptor encapsulated in the response telemetry carrier."""
    page: int = Field(..., description="Current 1-indexed page number")
    page_size: int = Field(..., description="Number of items per page")
    total_items: int = Field(..., description="Total count of items matching query")
    total_pages: int = Field(..., description="Total calculated pages available")
    has_next: bool = Field(..., description="Whether a subsequent page exists")
    has_prev: bool = Field(..., description="Whether a preceding page exists")


class ResponseMeta(CamelModel):
    """Request metadata carrier for distributed tracing, timing, and pagination."""
    trace_id: str = Field(..., description="Distributed correlation trace UUID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO 8601 UTC timestamp of response generation",
    )
    process_time_ms: Optional[float] = Field(
        default=None,
        description="Total server-side processing latency in milliseconds",
    )
    pagination: Optional[OffsetPaginationDescriptor] = Field(
        default=None,
        description="Optional pagination metadata when returning record collections",
    )


class RFC7807Problem(CamelModel):
    """Normalized RFC 7807 Problem Details representation."""
    type: str = Field(..., description="URI identifier describing the problem type")
    title: str = Field(..., description="Short, human-readable summary of the problem")
    status: int = Field(..., description="HTTP status code applicable to this occurrence")
    detail: str = Field(..., description="Human-readable explanation specific to this occurrence")
    instance: Optional[str] = Field(default=None, description="URI reference identifying specific occurrence")
    invalid_params: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional parameter validation failure details",
    )


class ApiResponse(CamelModel, Generic[T]):
    """Standard Unified Response Envelope for single-entity payloads."""
    success: bool = Field(default=True, description="Boolean flag indicating request success")
    data: T = Field(..., description="Payload containing domain entity or response DTO")
    meta: ResponseMeta = Field(..., description="Request execution telemetry and trace metadata")

    @classmethod
    def create(
        cls,
        data: T,
        trace_id: Optional[str] = None,
        process_time_ms: Optional[float] = None,
        pagination: Optional[OffsetPaginationDescriptor] = None,
    ) -> "ApiResponse[T]":
        """Factory constructor that automatically populates active trace ID and timestamp."""
        tid = trace_id or get_trace_id()
        meta = ResponseMeta(
            trace_id=tid,
            timestamp=datetime.now(timezone.utc),
            process_time_ms=process_time_ms,
            pagination=pagination,
        )
        return cls(success=True, data=data, meta=meta)


class ApiListResponse(CamelModel, Generic[T]):
    """Standard Unified Response Envelope for collection / list payloads."""
    success: bool = Field(default=True, description="Boolean flag indicating request success")
    data: List[T] = Field(default_factory=list, description="List of domain entities")
    meta: ResponseMeta = Field(..., description="Request execution telemetry and pagination metadata")

    @classmethod
    def create(
        cls,
        data: List[T],
        trace_id: Optional[str] = None,
        process_time_ms: Optional[float] = None,
        pagination: Optional[OffsetPaginationDescriptor] = None,
    ) -> "ApiListResponse[T]":
        """Factory constructor that automatically populates active trace ID, timestamp, and pagination."""
        tid = trace_id or get_trace_id()
        meta = ResponseMeta(
            trace_id=tid,
            timestamp=datetime.now(timezone.utc),
            process_time_ms=process_time_ms,
            pagination=pagination,
        )
        return cls(success=True, data=data, meta=meta)


class ApiErrorResponse(CamelModel):
    """Hybrid RFC 7807 Problem Envelope for all 4xx and 5xx responses."""
    success: bool = Field(default=False, description="Explicit failure discriminator flag")
    error: RFC7807Problem = Field(..., description="RFC 7807 problem details document")
    meta: ResponseMeta = Field(..., description="Request correlation and timing metadata")

    @classmethod
    def create(
        cls,
        type_: str,
        title: str,
        status_code: int,
        detail: str,
        instance: Optional[str] = None,
        invalid_params: Optional[List[Dict[str, Any]]] = None,
        trace_id: Optional[str] = None,
        process_time_ms: Optional[float] = None,
    ) -> "ApiErrorResponse":
        """Factory constructor for structured problem envelopes."""
        tid = trace_id or get_trace_id()
        problem = RFC7807Problem(
            type=type_,
            title=title,
            status=status_code,
            detail=detail,
            instance=instance,
            invalid_params=invalid_params,
        )
        meta = ResponseMeta(
            trace_id=tid,
            timestamp=datetime.now(timezone.utc),
            process_time_ms=process_time_ms,
        )
        return cls(success=False, error=problem, meta=meta)
