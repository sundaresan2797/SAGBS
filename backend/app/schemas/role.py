from pydantic import BaseModel


class RolePermissionUpdate(BaseModel):
    granted: bool


class PermissionOut(BaseModel):
    code: str
    description: str


class RolePermissionsOut(BaseModel):
    role: str
    permission_codes: list[str]


class PermissionsMatrixOut(BaseModel):
    permissions: list[PermissionOut]
    roles: list[RolePermissionsOut]
