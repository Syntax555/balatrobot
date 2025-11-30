-- src/lua/core/validator.lua
-- Schema Validator for Endpoint Arguments
--
-- Validates endpoint arguments against schema definitions using fail-fast validation.
-- Stops at the first error encountered and returns detailed error information.
--
-- Validation Approach:
-- - No automatic defaults (endpoints handle optional arguments explicitly)
-- - Fail-fast (returns first validation error encountered)
-- - Type-strict (enforces exact type matches, no implicit conversions)
-- - Minimal schema (only type, required, items, description fields)
--
-- Supported Types:
-- - string: Basic string type
-- - integer: Integer number (validated with math.floor check)
-- - boolean: Boolean type (true/false)
-- - array: Array of items (validated with sequential numeric indices)
-- - table: Generic table type (non-array tables)
--
-- Range/Length Validation:
-- Min/max validation is NOT handled by the validator. Endpoints implement
-- their own dynamic validation based on game state (e.g., valid card indices,
-- valid stake ranges, etc.)

---@type ErrorCodes
local errors = assert(SMODS.load_file("src/lua/utils/errors.lua"))()

---@class SchemaField
---@field type "string"|"integer"|"array"|"boolean"|"table" The field type
---@field required boolean? Whether the field is required
---@field items "integer"? Type of array items (only "integer" supported, only for array type)
---@field description string Description of the field (required)

---@class Validator
local Validator = {}

--- Check if a value is an integer
---@param value any Value to check
---@return boolean is_integer
local function is_integer(value)
  return type(value) == "number" and math.floor(value) == value
end

--- Check if a value is an array (table with sequential numeric indices)
---@param value any Value to check
---@return boolean is_array
local function is_array(value)
  if type(value) ~= "table" then
    return false
  end
  local count = 0
  for k, _v in pairs(value) do
    count = count + 1
    if type(k) ~= "number" or k ~= count then
      return false
    end
  end
  return true
end

--- Validate a single field against its schema definition
---@param field_name string Name of the field being validated
---@param value any The value to validate
---@param field_schema SchemaField The schema definition for this field
---@return boolean success
---@return string? error_message
---@return string? error_code
local function validate_field(field_name, value, field_schema)
  local expected_type = field_schema.type

  -- Check type
  if expected_type == "integer" then
    if not is_integer(value) then
      return false, "Field '" .. field_name .. "' must be an integer", errors.BAD_REQUEST
    end
  elseif expected_type == "array" then
    if not is_array(value) then
      return false, "Field '" .. field_name .. "' must be an array", errors.BAD_REQUEST
    end
  elseif expected_type == "table" then
    -- Empty tables are allowed, non-empty arrays are rejected
    if type(value) ~= "table" or (next(value) ~= nil and is_array(value)) then
      return false, "Field '" .. field_name .. "' must be a table", errors.BAD_REQUEST
    end
  else
    -- Standard Lua types: string, boolean
    if type(value) ~= expected_type then
      return false, "Field '" .. field_name .. "' must be of type " .. expected_type, errors.BAD_REQUEST
    end
  end

  -- Validate array item types if specified (only for array type)
  if expected_type == "array" and field_schema.items then
    for i, item in ipairs(value) do
      local item_type = field_schema.items
      local item_valid = false

      if item_type == "integer" then
        item_valid = is_integer(item)
      else
        item_valid = type(item) == item_type
      end

      if not item_valid then
        return false,
          "Field '" .. field_name .. "' array item at index " .. (i - 1) .. " must be of type " .. item_type,
          errors.BAD_REQUEST
      end
    end
  end

  return true
end

--- Validate arguments against a schema definition
---@param args table The arguments to validate
---@param schema table<string, SchemaField> The schema definition
---@return boolean success
---@return string? error_message
---@return string? error_code
function Validator.validate(args, schema)
  -- Ensure args is a table
  if type(args) ~= "table" then
    return false, "Arguments must be a table", errors.BAD_REQUEST
  end

  -- Validate each field in the schema
  for field_name, field_schema in pairs(schema) do
    local value = args[field_name]

    -- Check required fields
    if field_schema.required and value == nil then
      return false, "Missing required field '" .. field_name .. "'", errors.BAD_REQUEST
    end

    -- Validate field if present (skip optional fields that are nil)
    if value ~= nil then
      local success, err_msg, err_code = validate_field(field_name, value, field_schema)
      if not success then
        return false, err_msg, err_code
      end
    end
  end

  return true
end

return Validator
