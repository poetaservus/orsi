"""A bounded explanation channel for native tool-only repair attempts."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RepairDiagnosis(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    evidence_receipt: str = Field(min_length=1, max_length=128)
    failure: str = Field(min_length=1, max_length=500)
    suspected_cause: str = Field(min_length=1, max_length=500)
    proposed_change: str = Field(min_length=1, max_length=500)
    confirming_observation: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def nonblank(self):
        if any(not value.strip() for value in self.model_dump().values()):
            raise ValueError('Repair diagnosis fields must be nonblank.')
        return self
