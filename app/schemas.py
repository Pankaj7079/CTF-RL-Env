# Pydantic request/response models for the API.

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str


class ReleaseInfo(BaseModel):
    release: str
    artifact_count: int


class ReleasesResponse(BaseModel):
    releases: list[ReleaseInfo]


class ArtifactInfo(BaseModel):
    id: str
    release: str
    name: str
    scope: str
    status: str = Field(description="'available' or 'quarantined'.")


class ArtifactsResponse(BaseModel):
    artifacts: list[ArtifactInfo]


class MintRequest(BaseModel):
    artifact_id: str


class MintResponse(BaseModel):
    ticket: str
    scope: str
    note: str


class FlagRequest(BaseModel):
    flag: str


class FlagResponse(BaseModel):
    correct: bool
    message: str


class StatusResponse(BaseModel):
    attempt_id: str
    events: list[str]
    state: dict


class ResetResponse(BaseModel):
    attempt_id: str
