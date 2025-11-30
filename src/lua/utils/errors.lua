-- src/lua/utils/errors.lua
-- Error Codes for BalatroBot API

---@class ErrorCodes
---@field BAD_REQUEST string Client sent invalid data (protocol/parameter errors)
---@field INVALID_STATE string Action not allowed in current game state
---@field NOT_ALLOWED string Game rules prevent this action
---@field INTERNAL_ERROR string Server-side failure (runtime/execution errors)

---@type ErrorCodes
return {
  BAD_REQUEST = "BAD_REQUEST",
  INVALID_STATE = "INVALID_STATE",
  NOT_ALLOWED = "NOT_ALLOWED",
  INTERNAL_ERROR = "INTERNAL_ERROR",
}
