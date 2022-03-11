# -*- coding: utf-8 -*-
# Auto-generated by Stone, do not modify.
# @generated
# flake8: noqa
# pylint: skip-file

from typing import (
    Callable,
    Text,
    Type,
    TypeVar,
)
from stone.backends.python_rsrc import stone_base as bb  # type: ignore
from stone.backends.python_rsrc import stone_validators as bv  # type: ignore

T = TypeVar('T', bound=bb.AnnotationType)
U = TypeVar('U')

class LaunchResultBase(bb.Union):
    def is_async_job_id(self) -> bool: ...

    @classmethod
    def async_job_id(cls, val: Text) -> LaunchResultBase: ...

    def get_async_job_id(self) -> Text: ...

    def _process_custom_annotations(
        self,
        annotation_type: Type[T],
        field_path: Text,
        processor: Callable[[T, U], U],
    ) -> None: ...

LaunchResultBase_validator: bv.Validator = ...

class LaunchEmptyResult(LaunchResultBase):
    complete: LaunchEmptyResult = ...

    def is_complete(self) -> bool: ...

    def _process_custom_annotations(
        self,
        annotation_type: Type[T],
        field_path: Text,
        processor: Callable[[T, U], U],
    ) -> None: ...

LaunchEmptyResult_validator: bv.Validator = ...

class PollArg(bb.Struct):
    def __init__(self,
                 async_job_id: Text = ...) -> None: ...
    async_job_id: bb.Attribute[Text] = ...
    def _process_custom_annotations(
        self,
        annotation_type: Type[T],
        field_path: Text,
        processor: Callable[[T, U], U],
    ) -> None: ...

PollArg_validator: bv.Validator = ...

class PollResultBase(bb.Union):
    in_progress: PollResultBase = ...

    def is_in_progress(self) -> bool: ...

    def _process_custom_annotations(
        self,
        annotation_type: Type[T],
        field_path: Text,
        processor: Callable[[T, U], U],
    ) -> None: ...

PollResultBase_validator: bv.Validator = ...

class PollEmptyResult(PollResultBase):
    complete: PollEmptyResult = ...

    def is_complete(self) -> bool: ...

    def _process_custom_annotations(
        self,
        annotation_type: Type[T],
        field_path: Text,
        processor: Callable[[T, U], U],
    ) -> None: ...

PollEmptyResult_validator: bv.Validator = ...

class PollError(bb.Union):
    invalid_async_job_id: PollError = ...
    internal_error: PollError = ...
    other: PollError = ...

    def is_invalid_async_job_id(self) -> bool: ...

    def is_internal_error(self) -> bool: ...

    def is_other(self) -> bool: ...

    def _process_custom_annotations(
        self,
        annotation_type: Type[T],
        field_path: Text,
        processor: Callable[[T, U], U],
    ) -> None: ...

PollError_validator: bv.Validator = ...

AsyncJobId_validator: bv.Validator = ...
