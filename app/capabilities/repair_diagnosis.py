"""A bounded explanation channel for native tool-only repair attempts."""
from typing import Annotated
from pydantic import RootModel, ConfigDict, Field, model_validator


class RepairDiagnosis(RootModel[list[Annotated[str, Field(min_length=1, max_length=500)]]]):
    # A fixed five-part sequence avoids duplicating a large object schema in
    # both text tools. Each part and its position are still validated strictly.
    model_config = ConfigDict(strict=True)
    root: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(min_length=5, max_length=5)

    @property
    def evidence_receipt(self):
        return self.root[0]

    @model_validator(mode='after')
    def nonblank(self):
        if len(self.root[0]) > 128 or any(not value.strip() for value in self.root):
            raise ValueError('Repair diagnosis fields must be nonblank.')
        return self
