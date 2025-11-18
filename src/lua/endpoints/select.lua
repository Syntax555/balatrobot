local gamestate = assert(SMODS.load_file("src/lua/utils/gamestate.lua"))()

---@type Endpoint
return {
  name = "select",
  description = "Select the current blind",
  schema = {},
  requires_state = { G.STATES.BLIND_SELECT },

  ---@param _ table The arguments (none required)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(_, send_response)
    -- Get current blind and its UI element
    local current_blind = G.GAME.blind_on_deck
    assert(current_blind ~= nil, "select() called with no blind on deck")
    local blind_pane = G.blind_select_opts[string.lower(current_blind)]
    assert(blind_pane ~= nil, "select() blind pane not found: " .. current_blind)
    local select_button = blind_pane:get_UIE_by_ID("select_blind_button")
    assert(select_button ~= nil, "select() select button not found: " .. current_blind)

    -- Execute blind selection
    G.FUNCS.select_blind(select_button)

    -- Wait for completion: transition to SELECTING_HAND with facing_blind flag set
    G.E_MANAGER:add_event(Event({
      no_delete = true,
      trigger = "condition",
      blocking = false,
      func = function()
        local done = G.STATE == G.STATES.SELECTING_HAND
        if done then
          sendDebugMessage("select() completed", "BB.ENDPOINTS")
          local state_data = gamestate.get_gamestate()
          send_response(state_data)
        end
        return done
      end,
    }))
  end,
}
