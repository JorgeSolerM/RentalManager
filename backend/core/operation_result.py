from dataclasses import dataclass
from typing import Generic
from typing import TypeVar


T = TypeVar("T")


@dataclass
class OperationResult(Generic[T]):

    success: bool

    message: str = ""

    data: T | None = None
