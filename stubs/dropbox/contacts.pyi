# -*- coding: utf-8 -*-
# Auto-generated by Stone, do not modify.
# @generated
# flake8: noqa
# pylint: skip-file

from typing import (
    Callable,
    List,
    Text,
    Type,
    TypeVar,
)
from stone.backends.python_rsrc import stone_base as bb  # type: ignore
from stone.backends.python_rsrc import stone_validators as bv  # type: ignore

from dropbox import common  # type: ignore

T = TypeVar('T', bound=bb.AnnotationType)
U = TypeVar('U')

class DeleteManualContactsArg(bb.Struct):
    def __init__(self,
                 email_addresses: List[Text] = ...) -> None: ...
    email_addresses: bb.Attribute[List[Text]] = ...
    def _process_custom_annotations(
        self,
        annotation_type: Type[T],
        field_path: Text,
        processor: Callable[[T, U], U],
    ) -> None: ...

DeleteManualContactsArg_validator: bv.Validator = ...

class DeleteManualContactsError(bb.Union):
    other: DeleteManualContactsError = ...

    def is_contacts_not_found(self) -> bool: ...

    def is_other(self) -> bool: ...

    @classmethod
    def contacts_not_found(cls, val: List[Text]) -> DeleteManualContactsError: ...

    def get_contacts_not_found(self) -> List[Text]: ...

    def _process_custom_annotations(
        self,
        annotation_type: Type[T],
        field_path: Text,
        processor: Callable[[T, U], U],
    ) -> None: ...

DeleteManualContactsError_validator: bv.Validator = ...

delete_manual_contacts: bb.Route = ...
delete_manual_contacts_batch: bb.Route = ...

