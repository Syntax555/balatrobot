-- src/lua/endpoints/menu.lua
-- Menu Endpoint
--
-- Returns to the main menu from any game state

local gamestate = assert(SMODS.load_file("src/lua/utils/gamestate.lua"))()

---@type Endpoint
return {
  name = "menu",

  description = "Return to the main menu from any game state",

  schema = {},

  requires_state = nil,

  ---@param _ table The arguments (empty for menu)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(_, send_response)
    sendDebugMessage("Init menu()", "BB.ENDPOINTS")
    G.FUNCS.go_to_menu({})

    -- Wait for menu state using Balatro's Event Manager
    G.E_MANAGER:add_event(Event({
      no_delete = true,
      trigger = "condition",
      blocking = true,
      func = function()
        local done = G.STATE == G.STATES.MENU and G.MAIN_MENU_UI

        if done then
          sendDebugMessage("Return menu()", "BB.ENDPOINTS")
          local state_data = gamestate.get_gamestate()
          send_response(state_data)
        end

        return done
      end,
    }))
  end,
}
