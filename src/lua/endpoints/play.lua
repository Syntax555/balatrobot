-- src/lua/endpoints/play.lua
-- Play Endpoint
--
-- Play a card from the hand

---@class Endpoint.Play.Params
---@field cards integer[] 0-based indices of cards to play

---@type Endpoint
return {
  name = "play",
  description = "Play a card from the hand",
  schema = {
    cards = {
      type = "array",
      required = true,
      items = "integer",
      description = "0-based indices of cards to play",
    },
  },
  requires_state = { G.STATES.SELECTING_HAND },

  ---@param args Endpoint.Play.Params The arguments (cards)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    if #args.cards == 0 then
      send_response({
        error = "Must provide at least one card to play",
        error_code = BB_ERROR_NAMES.BAD_REQUEST,
      })
      return
    end

    if #args.cards > G.hand.config.highlighted_limit then
      send_response({
        error = "You can only play " .. G.hand.config.highlighted_limit .. " cards",
        error_code = BB_ERROR_NAMES.BAD_REQUEST,
      })
      return
    end

    for _, card_index in ipairs(args.cards) do
      if not G.hand.cards[card_index + 1] then
        send_response({
          error = "Invalid card index: " .. card_index,
          error_code = BB_ERROR_NAMES.BAD_REQUEST,
        })
        return
      end
    end

    -- NOTE: Clear any existing highlights before selecting new cards
    -- prevent state pollution. This is a bit of a hack but could interfere
    -- with Boss Blind like Cerulean Bell.
    G.hand:unhighlight_all()

    for _, card_index in ipairs(args.cards) do
      G.hand.cards[card_index + 1]:click()
    end

    ---@diagnostic disable-next-line: undefined-field
    local play_button = UIBox:get_UIE_by_ID("play_button", G.buttons.UIRoot)
    assert(play_button ~= nil, "play() play button not found")
    G.FUNCS.play_cards_from_highlighted(play_button)

    local hand_played = false
    local draw_to_hand = false

    -- NOTE: GAME_OVER detection cannot happen inside this event function
    -- because when G.STATE becomes GAME_OVER, the game sets G.SETTINGS.paused = true,
    -- which stops all event processing. This callback is set so that love.update
    -- (which runs even when paused) can detect GAME_OVER immediately.
    BB_GAMESTATE.on_game_over = send_response

    G.E_MANAGER:add_event(Event({
      trigger = "condition",
      blocking = false,
      blockable = false,
      created_on_pause = true,
      func = function()
        -- State progression:
        -- Loss: HAND_PLAYED -> NEW_ROUND -> (game paused) -> GAME_OVER
        -- Win round: HAND_PLAYED -> NEW_ROUND -> ROUND_EVAL
        -- Win game: HAND_PLAYED -> NEW_ROUND -> ROUND_EVAL (with G.GAME.won = true)
        -- Keep playing current round: HAND_PLAYED -> DRAW_TO_HAND -> SELECTING_HAND

        -- Track state transitions
        if G.STATE == G.STATES.HAND_PLAYED then
          hand_played = true
        end

        if G.STATE == G.STATES.DRAW_TO_HAND then
          draw_to_hand = true
        end

        -- if G.STATE == G.STATES.GAME_OVER then
        --   -- NOTE: GAME_OVER is detected by gamestate.on_game_over callback in love.update
        --   return true
        -- end

        if G.STATE == G.STATES.ROUND_EVAL and G.round_eval then
          -- Go to the cash out stage
          for _, b in ipairs(G.I.UIBOX) do
            if b:get_UIE_by_ID("cash_out_button") then
              local state_data = BB_GAMESTATE.get_gamestate()
              sendDebugMessage("Return play() - cash out", "BB.ENDPOINTS")
              send_response(state_data)
              return true
            end
          end
          -- Game is won
          if G.GAME.won then
            sendDebugMessage("Return play() - won", "BB.ENDPOINTS")
            local state_data = BB_GAMESTATE.get_gamestate()
            send_response(state_data)
            return true
          end
        end

        if draw_to_hand and hand_played and G.buttons and G.STATE == G.STATES.SELECTING_HAND then
          sendDebugMessage("Return play() - same round", "BB.ENDPOINTS")
          local state_data = BB_GAMESTATE.get_gamestate()
          send_response(state_data)
          return true
        end

        return false
      end,
    }))
  end,
}
