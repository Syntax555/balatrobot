-- src/lua/endpoints/reroll.lua

-- ==========================================================================
-- Reroll Endpoint Params
-- ==========================================================================

---@class Endpoint.Reroll.Params

-- ==========================================================================
-- Reroll Endpoint
-- ==========================================================================

---@type Endpoint
return {

  name = "reroll",

  description = "Reroll to update the cards in the shop area",

  schema = {},

  requires_state = { G.STATES.SHOP },

  ---@param _ Endpoint.Reroll.Params
  ---@param send_response fun(response: EndpointResponse)
  execute = function(_, send_response)
    -- Check affordability
    local reroll_cost = G.GAME.current_round and G.GAME.current_round.reroll_cost or 0

    if G.GAME.dollars < reroll_cost then
      send_response({
        message = "Not enough dollars to reroll. Current: " .. G.GAME.dollars .. ", Required: " .. reroll_cost,
        name = BB_ERROR_NAMES.NOT_ALLOWED,
      })
      return
    end

    sendDebugMessage("Init reroll()", "BB.ENDPOINTS")
    G.FUNCS.reroll_shop(nil)

    -- Wait for shop state to confirm reroll completed
    G.E_MANAGER:add_event(Event({
      trigger = "condition",
      blocking = false,
      func = function()
        local done = G.STATE == G.STATES.SHOP
        if done then
          sendDebugMessage("Return reroll() - shop rerolled", "BB.ENDPOINTS")
          send_response(BB_GAMESTATE.get_gamestate())
        end
        return done
      end,
    }))
  end,
}
