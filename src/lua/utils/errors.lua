-- src/lua/utils/errors.lua
-- Semantic Error Codes with Category Prefixes
--
-- Error codes are organized by category for easier handling and debugging:
-- - PROTO_*    : Protocol-level errors (malformed requests)
-- - SCHEMA_*   : Schema validation errors (argument type/constraint errors)
-- - STATE_*    : Game state validation errors (wrong state for action)
-- - GAME_*     : Game logic errors (game rules violations)
-- - SEMANTIC_* : Endpoint-specific semantic errors
-- - EXEC_*     : Execution errors (runtime failures)

---@class ErrorCodes
---@field PROTO_INVALID_JSON string
---@field PROTO_MISSING_NAME string
---@field PROTO_MISSING_ARGUMENTS string
---@field PROTO_UNKNOWN_ENDPOINT string
---@field PROTO_PAYLOAD string
---@field SCHEMA_INVALID_TYPE string
---@field SCHEMA_MISSING_REQUIRED string
---@field SCHEMA_INVALID_ARRAY_ITEMS string
---@field STATE_INVALID_STATE string
---@field STATE_NOT_READY string
---@field EXEC_INTERNAL_ERROR string

---@type ErrorCodes
return {
  -- PROTO_* : Protocol-level errors (malformed requests)
  PROTO_INVALID_JSON = "PROTO_INVALID_JSON", -- Invalid JSON syntax or non-object
  PROTO_MISSING_NAME = "PROTO_MISSING_NAME", -- Request missing 'name' field
  PROTO_MISSING_ARGUMENTS = "PROTO_MISSING_ARGUMENTS", -- Request missing 'arguments' field
  PROTO_UNKNOWN_ENDPOINT = "PROTO_UNKNOWN_ENDPOINT", -- Unknown endpoint name
  PROTO_PAYLOAD = "PROTO_PAYLOAD", -- Request exceeds 256 byte limit

  -- SCHEMA_* : Schema validation errors (argument type/constraint errors)
  SCHEMA_INVALID_TYPE = "SCHEMA_INVALID_TYPE", -- Argument type mismatch
  SCHEMA_MISSING_REQUIRED = "SCHEMA_MISSING_REQUIRED", -- Required argument missing
  SCHEMA_INVALID_ARRAY_ITEMS = "SCHEMA_INVALID_ARRAY_ITEMS", -- Invalid array item type

  -- STATE_* : Game state validation errors (wrong state for action)
  STATE_INVALID_STATE = "STATE_INVALID_STATE", -- Action not allowed in current state
  STATE_NOT_READY = "STATE_NOT_READY", -- Server/dispatcher not initialized

  -- EXEC_* : Execution errors (runtime failures)
  EXEC_INTERNAL_ERROR = "EXEC_INTERNAL_ERROR", -- Unexpected runtime error

  -- TODO: Define future error codes as needed:
  --
  -- Here are some examples of future error codes:
  -- PROTO_INCOMPLETE - No newline terminator
  -- STATE_TRANSITION_FAILED - State transition error
  -- GAME_INSUFFICIENT_FUNDS - Not enough money
  -- GAME_NO_SPACE - No space in inventory/shop
  -- GAME_ITEM_NOT_FOUND - Item/card not found
  -- GAME_MISSING_OBJECT - Required game object missing
  -- GAME_INVALID_ACTION - Invalid game action
  -- SEMANTIC_CARD_NOT_SELLABLE - Card cannot be sold
  -- SEMANTIC_CONSUMABLE_REQUIRES_TARGET - Consumable needs target
  -- SEMANTIC_CONSUMABLE_NOT_USABLE - Consumable cannot be used
  -- SEMANTIC_CANNOT_SKIP_BOSS - Boss blind cannot be skipped
  -- SEMANTIC_NO_DISCARDS_LEFT - No discards remaining
  -- SEMANTIC_UNIQUE_ITEM_OWNED - Already own unique item
  -- EXEC_TIMEOUT - Request timeout
  -- EXEC_DISCONNECT - Client disconnected
}
