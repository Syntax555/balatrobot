-- src/lua/endpoints/health.lua
-- Health Check Endpoint
--
-- Simple synchronous endpoint for connection testing and readiness checks
-- Returns server status and basic game information immediately

---@class Endpoint
---@field name string The endpoint name
---@field description string Brief description of the endpoint
---@field schema table<string, SchemaField> Schema definition for arguments validation
---@field requires_state string[]? Optional list of required game states
---@field execute fun(args: table, send_response: fun(response: table)) Execute function

---@type Endpoint
return {
  name = "health",

  description = "Health check endpoint for connection testing",

  schema = {}, -- No arguments required

  requires_state = nil, -- Can be called from any state

  ---@param _ table The arguments (empty for health check)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(_, send_response)
    -- Return simple status immediately (synchronous)
    send_response({
      status = "ok",
    })
  end,
}
