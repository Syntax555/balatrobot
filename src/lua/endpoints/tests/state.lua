-- src/lua/endpoints/tests/state.lua
-- Test Endpoint with State Requirements
--
-- Used for testing TIER 3: Game State Validation

---@type Endpoint
return {
  name = "test_state_endpoint",

  description = "Test endpoint that requires specific game states",

  schema = {}, -- No argument validation

  -- This endpoint can only be called from SPLASH or MENU states
  requires_state = { "SPLASH", "MENU" },

  ---@param _args table The arguments (empty)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(_args, send_response)
    send_response({
      success = true,
      state_validated = true,
    })
  end,
}
