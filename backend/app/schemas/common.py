"""공통 응답 스키마."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """목록 응답 공통 envelope."""

    items: list[T]
    total: int
    page: int
    size: int
