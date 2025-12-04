-- Use Endpoint
--
-- Use a consumable card (Tarot, Planet, or Spectral) with optional target cards

---@class Endpoint.Use.Params
---@field consumable integer 0-based index of consumable to use
---@field cards integer[]? 0-based indices of cards to target

---@type Endpoint
return {
  name = "use",
  description = "Use a consumable card with optional target cards",
  schema = {
    consumable = {
      type = "integer",
      required = true,
      description = "0-based index of consumable to use",
    },
    cards = {
      type = "array",
      required = false,
      description = "0-based indices of cards to target (required only if consumable requires cards)",
      items = "integer",
    },
  },
  requires_state = { G.STATES.SELECTING_HAND, G.STATES.SHOP },

  ---@param args Endpoint.Use.Params The arguments
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    sendDebugMessage("Init use()", "BB.ENDPOINTS")

    -- Step 1: Consumable Index Validation
    if args.consumable < 0 or args.consumable >= #G.consumeables.cards then
      send_response({
        error = "Consumable index out of range: " .. args.consumable,
        error_code = BB_ERRORS.BAD_REQUEST,
      })
      return
    end

    local consumable_card = G.consumeables.cards[args.consumable + 1]

    -- Step 2: Determine Card Selection Requirements
    local requires_cards = consumable_card.ability.consumeable.max_highlighted ~= nil

    -- Step 3: State Validation for Card-Selecting Consumables
    if requires_cards and G.STATE ~= G.STATES.SELECTING_HAND then
      send_response({
        error = "Consumable '"
          .. consumable_card.ability.name
          .. "' requires card selection and can only be used in SELECTING_HAND state",
        error_code = BB_ERRORS.INVALID_STATE,
      })
      return
    end

    -- Step 4: Cards Parameter Validation
    if requires_cards then
      if not args.cards or #args.cards == 0 then
        send_response({
          error = "Consumable '" .. consumable_card.ability.name .. "' requires card selection",
          error_code = BB_ERRORS.BAD_REQUEST,
        })
        return
      end

      -- Validate each card index is in range
      for _, card_idx in ipairs(args.cards) do
        if card_idx < 0 or card_idx >= #G.hand.cards then
          send_response({
            error = "Card index out of range: " .. card_idx,
            error_code = BB_ERRORS.BAD_REQUEST,
          })
          return
        end
      end
    end

    -- Step 5: Explicit Min/Max Card Count Validation
    if requires_cards then
      local min_cards = consumable_card.ability.consumeable.min_highlighted or 1
      local max_cards = consumable_card.ability.consumeable.max_highlighted
      local card_count = #args.cards

      -- Check if consumable requires exact number of cards
      if min_cards == max_cards and card_count ~= min_cards then
        send_response({
          error = string.format(
            "Consumable '%s' requires exactly %d card%s (provided: %d)",
            consumable_card.ability.name,
            min_cards,
            min_cards == 1 and "" or "s",
            card_count
          ),
          error_code = BB_ERRORS.BAD_REQUEST,
        })
        return
      end

      -- For consumables with range, check min and max separately
      if card_count < min_cards then
        send_response({
          error = string.format(
            "Consumable '%s' requires at least %d card%s (provided: %d)",
            consumable_card.ability.name,
            min_cards,
            min_cards == 1 and "" or "s",
            card_count
          ),
          error_code = BB_ERRORS.BAD_REQUEST,
        })
        return
      end

      if card_count > max_cards then
        send_response({
          error = string.format(
            "Consumable '%s' requires at most %d card%s (provided: %d)",
            consumable_card.ability.name,
            max_cards,
            max_cards == 1 and "" or "s",
            card_count
          ),
          error_code = BB_ERRORS.BAD_REQUEST,
        })
        return
      end
    end

    -- Step 6: Card Selection Setup
    if requires_cards then
      -- Clear existing selection
      for i = #G.hand.highlighted, 1, -1 do
        G.hand:remove_from_highlighted(G.hand.highlighted[i], true)
      end

      -- Add cards using proper method
      for _, card_idx in ipairs(args.cards) do
        local hand_card = G.hand.cards[card_idx + 1] -- Convert 0-based to 1-based
        G.hand:add_to_highlighted(hand_card, true) -- silent=true
      end

      sendDebugMessage(
        string.format("Selected %d cards for '%s'", #args.cards, consumable_card.ability.name),
        "BB.ENDPOINTS"
      )
    end

    -- Step 7: Game-Level Validation (e.g. try to use Familiar Spectral when G.hand is not available)
    if not consumable_card:can_use_consumeable() then
      send_response({
        error = "Consumable '" .. consumable_card.ability.name .. "' cannot be used at this time",
        error_code = BB_ERRORS.NOT_ALLOWED,
      })
      return
    end

    -- Step 8: Space Check (not tested)
    if consumable_card:check_use() then
      send_response({
        error = "Cannot use consumable '" .. consumable_card.ability.name .. "': insufficient space",
        error_code = BB_ERRORS.NOT_ALLOWED,
      })
      return
    end

    -- Execution
    sendDebugMessage("Executing use() for consumable: " .. consumable_card.ability.name, "BB.ENDPOINTS")

    -- Track initial count for completion detection
    local initial_consumable_count = G.consumeables.config.card_count

    -- Create mock UI element for game function
    local mock_element = {
      config = {
        ref_table = consumable_card,
      },
    }

    -- Call game's use_card function
    G.FUNCS.use_card(mock_element, true, true)

    -- Completion Detection
    G.E_MANAGER:add_event(Event({
      trigger = "condition",
      blocking = false,
      func = function()
        -- Condition 1: Card was removed
        local card_removed = (G.consumeables.config.card_count < initial_consumable_count)

        -- Condition 2: State restored (not PLAY_TAROT anymore)
        local state_restored = (G.STATE ~= G.STATES.PLAY_TAROT)

        -- Condition 3: Controller unlocked
        local controller_unlocked = not G.CONTROLLER.locks.use

        -- Condition 4: no stop use
        local no_stop_use = not (G.GAME.STOP_USE and G.GAME.STOP_USE > 0)

        if card_removed and state_restored and controller_unlocked and no_stop_use then
          sendDebugMessage("use() completed successfully", "BB.ENDPOINTS")
          send_response(BB_GAMESTATE.get_gamestate())
          return true
        end

        return false
      end,
    }))
  end,
}
