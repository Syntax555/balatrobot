-- src/lua/endpoints/tests/error.lua
-- Test Endpoint that Throws Errors
--
-- Used for testing TIER 4: Execution Error Handling

---@class Endpoint.TestErrorEndpoint.Params
---@field error_type "throw_error"|"success" Whether to throw an error or succeed

---@type Endpoint
return {
  name = "test_error_endpoint",

  description = "Test endpoint that throws runtime errors",

  schema = {
    error_type = {
      type = "string",
      required = true,
      enum = { "throw_error", "success" },
      description = "Whether to throw an error or succeed",
    },
  },

  requires_state = nil,

  ---@param args Endpoint.TestErrorEndpoint.Params The arguments
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    if args.error_type == "throw_error" then
      error("Intentional test error from endpoint execution")
    else
      send_response({
        success = true,
      })
    end
  end,
}
