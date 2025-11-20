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

    G.E_MANAGER:add_event(Event({
      no_delete = true,
      trigger = "condition",
      blocking = false,
      func = function()
        local done = G.STATE == G.STATES.SHOP and G.shop and G.SHOP_SIGN and G.STATE_COMPLETE

        if done then
          sendDebugMessage("Return cash_out()", "BB.ENDPOINTS")
          local state_data = BB_GAMESTATE.get_gamestate()
          send_response(state_data)
        end

        return done
      end,
    }))
  end,
}
