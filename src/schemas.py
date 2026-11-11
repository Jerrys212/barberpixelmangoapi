from typing import ClassVar

from pydantic import BaseModel, model_validator


class PatchModel(BaseModel):
    # Omitted fields stay untouched; only nullable columns accept an explicit null.
    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_on_required_columns(self) -> PatchModel:
        for field in self.model_fields_set - self.nullable_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} no puede ser null")
        return self

    def changes(self) -> dict[str, object]:
        return self.model_dump(exclude_unset=True)
