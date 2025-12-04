-- src/lua/utils/errors.lua
-- Error definitions for BalatroBot API

---@alias ErrorName
---| "BAD_REQUEST" Client sent invalid data (protocol/parameter errors)
---| "INVALID_STATE" Action not allowed in current game state
---| "NOT_ALLOWED" Game rules prevent this action
---| "INTERNAL_ERROR" Server-side failure (runtime/execution errors)

---@alias ErrorNames table<ErrorName, ErrorName>

---@alias ErrorCode
---| -32000 # INTERNAL_ERROR
---| -32001 # BAD_REQUEST
---| -32002 # INVALID_STATE
---| -32003 # NOT_ALLOWED

---@alias ErrorCodes table<ErrorName, ErrorCode>

---@type ErrorNames
BB_ERROR_NAMES = {
  INTERNAL_ERROR = "INTERNAL_ERROR",
  BAD_REQUEST = "BAD_REQUEST",
  INVALID_STATE = "INVALID_STATE",
  NOT_ALLOWED = "NOT_ALLOWED",
}

---@type ErrorCodes
BB_ERROR_CODES = {
  INTERNAL_ERROR = -32000,
  BAD_REQUEST = -32001,
  INVALID_STATE = -32002,
  NOT_ALLOWED = -32003,
}

return BB_ERROR_NAMES, BB_ERROR_CODES
