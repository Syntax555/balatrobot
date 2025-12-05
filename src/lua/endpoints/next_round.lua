-- src/lua/endpoints/next_round.lua

-- ==========================================================================
-- NextRound Endpoint Params
-- ==========================================================================

---@class Endpoint.NextRound.Params

-- ==========================================================================
-- NextRound Endpoint
-- ==========================================================================

---@type Endpoint
return {

  name = "next_round",

  description = "Leave the shop and advance to blind selection",

  schema = {},

  requires_state = { G.STATES.SHOP },

  ---@param _ Endpoint.NextRound.Params
  ---@param send_response fun(response: EndpointResponse)
  execute = function(_, send_response)
    sendDebugMessage("Init next_round()", "BB.ENDPOINTS")
    G.FUNCS.toggle_shop({})

    -- Wait for BLIND_SELECT state after leaving shop
    G.E_MANAGER:add_event(Event({
      trigger = "condition",
      blocking = false,
      func = function()
        local blind_pane = G.blind_select_opts[string.lower(G.GAME.blind_on_deck)]
        local select_button = blind_pane:get_UIE_by_ID("select_blind_button")
        local done = G.STATE == G.STATES.BLIND_SELECT and select_button ~= nil
        if done then
          sendDebugMessage("Return next_round() - reached BLIND_SELECT state", "BB.ENDPOINTS")
          send_response(BB_GAMESTATE.get_gamestate())
        end
        return done
      end,
    }))
  end,
}
