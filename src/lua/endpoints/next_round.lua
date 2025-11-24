-- src/lua/endpoints/next_round.lua
-- Next Round Endpoint
--
-- Leave the shop and advance to blind selection

---@type Endpoint
return {
  name = "next_round",

  description = "Leave the shop and advance to blind selection",

  schema = {},

  requires_state = { G.STATES.SHOP },

  ---@param _ table The arguments (none required)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(_, send_response)
    sendDebugMessage("Init next_round()", "BB.ENDPOINTS")
    G.FUNCS.toggle_shop({})

    -- Wait for BLIND_SELECT state after leaving shop
    G.E_MANAGER:add_event(Event({
      trigger = "condition",
      blocking = false,
      func = function()
        local done = G.STATE == G.STATES.BLIND_SELECT
        if done then
          sendDebugMessage("Return next_round() - reached BLIND_SELECT state", "BB.ENDPOINTS")
          send_response(BB_GAMESTATE.get_gamestate())
        end
        return done
      end,
    }))
  end,
}
