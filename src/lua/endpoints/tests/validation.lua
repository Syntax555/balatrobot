-- tests/lua/endpoints/test_validation.lua
-- Comprehensive Validation Test Endpoint
--
-- Endpoint with schema for testing simplified validator capabilities:
-- - Type validation (string, integer, array)
-- - Required field validation
-- - Array item type validation (integer arrays only)

---@type Endpoint
return {
  name = "test_validation",

  description = "Comprehensive validation test endpoint for validator module testing",

  schema = {
    -- Required field (only required field in the schema)
    required_field = {
      type = "string",
      required = true,
      description = "Required string field for basic validation testing",
    },

    -- Type validation fields
    string_field = {
      type = "string",
      description = "Optional string field for type validation",
    },

    integer_field = {
      type = "integer",
      description = "Optional integer field for type validation",
    },

    array_field = {
      type = "array",
      description = "Optional array field for type validation",
    },

    -- Array item type validation
    array_of_integers = {
      type = "array",
      items = "integer",
      description = "Optional array that must contain only integers",
    },
  },

  requires_state = nil, -- Can be called from any state

  ---@param args table The validated arguments
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    -- Simply return success with the received arguments
    send_response({
      success = true,
      received_args = args,
    })
  end,
}
