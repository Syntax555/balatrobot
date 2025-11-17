-- src/lua/endpoints/gamestate.lua
-- Gamestate Endpoint
--
-- Returns the current game state extracted via the gamestate utility
-- Provides a simplified view of the game optimized for bot decision-making

local gamestate = assert(SMODS.load_file("src/lua/utils/gamestate.lua"))()

---@type Endpoint
return {
  name = "gamestate",

  description = "Get current game state",

  schema = {}, -- No arguments required

  requires_state = nil, -- Can be called from any state

  ---@param _ table The arguments (empty for gamestate)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(_, send_response)
    -- Get current game state
    local state_data = gamestate.get_gamestate()

    -- Return the game state
    send_response(state_data)
  end,
}
