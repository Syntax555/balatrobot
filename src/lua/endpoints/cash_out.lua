-- src/lua/endpoints/cash_out.lua
-- Cash Out Endpoint
--
-- Cash out and collect round rewards

---@type Endpoint
return {
  name = "cash_out",

  description = "Cash out and collect round rewards",

  schema = {},

  requires_state = { G.STATES.ROUND_EVAL },

  ---@param _ table The arguments (none required)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(_, send_response)
    sendDebugMessage("Init cash_out()", "BB.ENDPOINTS")
    G.FUNCS.cash_out({ config = {} })

    -- Wait for SHOP state after state transition completes
    G.E_MANAGER:add_event(Event({
      trigger = "condition",
      blocking = false,
      func = function()
        local done = false
        if G.STATE == G.STATES.SHOP and G.STATE_COMPLETE then
          local done_vouchers = G.shop_vouchers and G.shop_vouchers.cards and #G.shop_vouchers.cards > 0
          local done_packs = G.shop_booster and G.shop_booster.cards and #G.shop_booster.cards > 0
          local done_jokers = G.shop_jokers and G.shop_jokers.cards and #G.shop_jokers.cards > 0
          done = done_vouchers or done_packs or done_jokers
          if done then
            sendDebugMessage("Return cash_out() - reached SHOP state", "BB.ENDPOINTS")
            send_response(BB_GAMESTATE.get_gamestate())
            return done
          end
        end
        return done
      end,
    }))
  end,
}
