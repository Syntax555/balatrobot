-- tests/lua/endpoints/tests/endpoint.lua
-- Test Endpoint for Dispatcher Testing
--
-- Simplified endpoint for testing the dispatcher with the simplified validator

---@type Endpoint
return {
  name = "test_endpoint",

  description = "Test endpoint with schema for dispatcher testing",

  schema = {
    -- Required string field
    required_string = {
      type = "string",
      required = true,
      description = "A required string field",
    },

    -- Optional string field
    optional_string = {
      type = "string",
      description = "Optional string field",
    },

    -- Required integer field
    required_integer = {
      type = "integer",
      required = true,
      description = "Required integer field",
    },

    -- Optional integer field
    optional_integer = {
      type = "integer",
      description = "Optional integer field",
    },

    -- Optional array of integers
    optional_array_integers = {
      type = "array",
      items = "integer",
      description = "Optional array of integers",
    },
  },

  requires_state = nil, -- Can be called from any state

  ---@param args table The validated arguments
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    -- Echo back the received arguments
    send_response({
      success = true,
      received_args = args,
    })
  end,
}
