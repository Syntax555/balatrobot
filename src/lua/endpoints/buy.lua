-- src/lua/endpoints/buy.lua
-- Buy Endpoint
--
-- Buy a card from the shop

---@class Endpoint.Buy.Args
---@field card integer? 0-based index of card to buy
---@field voucher integer? 0-based index of voucher to buy
---@field pack integer? 0-based index of pack to buy

---@type Endpoint
return {
  name = "buy",
  description = "Buy a card from the shop",
  schema = {
    card = {
      type = "integer",
      required = false,
      description = "0-based index of card to buy",
    },
    voucher = {
      type = "integer",
      required = false,
      description = "0-based index of voucher to buy",
    },
    pack = {
      type = "integer",
      required = false,
      description = "0-based index of pack to buy",
    },
  },
  requires_state = { G.STATES.SHOP },

  ---@param args Endpoint.Buy.Args The arguments (card)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    sendDebugMessage("Init buy()", "BB.ENDPOINTS")
    local gamestate = BB_GAMESTATE.get_gamestate()
    sendDebugMessage("Gamestate is : " .. gamestate.state, "BB.ENDPOINTS")
    sendDebugMessage(
      "Gamestate native is : " .. (G.consumeables and G.consumeables.config and G.consumeables.config.card_count or 0),
      "BB.ENDPOINTS"
    )
    local area
    local pos
    local set = 0
    if args.card then
      area = gamestate.shop
      pos = args.card + 1
      set = set + 1
    end
    if args.voucher then
      area = gamestate.vouchers
      pos = args.voucher + 1
      set = set + 1
    end
    if args.pack then
      area = gamestate.packs
      pos = args.pack + 1
      set = set + 1
    end

    -- Validate that only one of card, voucher, or pack is provided
    if not area then
      send_response({
        error = "Invalid arguments. You must provide one of: card, voucher, pack",
        error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
      })
      return
    end

    -- Validate that only one of card, voucher, or pack is provided
    if set > 1 then
      send_response({
        error = "Invalid arguments. Cannot provide more than one of: card, voucher, or pack",
        error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
      })
      return
    end

    -- Validate that the area has cards
    if #area.cards == 0 then
      local msg
      if args.card then
        msg = "No jokers/consumables/cards in the shop. Reroll to restock the shop"
      elseif args.voucher then
        msg = "No vouchers to redeem. Defeat boss blind to restock"
      elseif args.pack then
        msg = "No boosters/standard/buffoon packs to open"
      end
      send_response({
        error = msg,
        error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
      })
      return
    end

    -- Validate card index is in range
    if not area.cards[pos] then
      send_response({
        error = "Card index out of range. Index: " .. args.card .. ", Available cards: " .. area.count,
        error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
      })
      return
    end

    -- Get the card
    local card = area.cards[pos]

    -- Check if the card can be afforded
    if card.cost.buy > G.GAME.dollars then
      send_response({
        error = "Card is not affordable. Cost: " .. card.cost.buy .. ", Current money: " .. gamestate.money,
        error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
      })
      return
    end

    -- Ensure there is space in joker area
    if card.set == "JOKER" then
      if gamestate.jokers.count >= gamestate.jokers.limit then
        send_response({
          error = "Cannot purchase joker card, joker slots are full. Current: "
            .. gamestate.jokers.count
            .. ", Limit: "
            .. gamestate.jokers.limit,
          error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
        })
        return
      end
    end

    -- Ensure there is space in consumable area
    if card.set == "PLANET" or card.set == "SPECTRAL" or card.set == "TAROT" then
      if gamestate.consumables.count >= gamestate.consumables.limit then
        send_response({
          error = "Cannot purchase consumable card, consumable slots are full. Current: "
            .. gamestate.consumables.count
            .. ", Limit: "
            .. gamestate.consumables.limit,
          error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
        })
        return
      end
    end

    local initial_shop_count = 0
    local initial_dest_count = 0
    local initial_money = gamestate.money

    if args.card then
      initial_shop_count = gamestate.shop.count
      initial_dest_count = gamestate.jokers.count
        + gamestate.consumables.count
        + (G.deck and G.deck.config and G.deck.config.card_count or 0)
    elseif args.voucher then
      initial_shop_count = gamestate.vouchers.count
      initial_dest_count = 0
      for _ in pairs(gamestate.used_vouchers) do
        initial_dest_count = initial_dest_count + 1
      end
    end

    -- Get the buy button from the card
    local btn
    if args.card then
      btn = G.shop_jokers.cards[pos].children.buy_button.definition
    elseif args.voucher then
      btn = G.shop_vouchers.cards[pos].children.buy_button.definition
    elseif args.pack then
      btn = G.shop_booster.cards[pos].children.buy_button.definition
    end
    if not btn then
      send_response({
        error = "No buy button found for card",
        error_code = BB_ERRORS.GAME_INVALID_STATE,
      })
      return
    end

    -- Use appropriate function: use_card for vouchers, buy_from_shop for others
    if args.voucher or args.pack then
      G.FUNCS.use_card(btn)
    else
      G.FUNCS.buy_from_shop(btn)
    end

    -- Wait for buy completion with comprehensive verification
    G.E_MANAGER:add_event(Event({
      trigger = "condition",
      blocking = false,
      func = function()
        local done = false

        if args.card then
          local shop_count = (G.shop_jokers and G.shop_jokers.config and G.shop_jokers.config.card_count or 0)
          local dest_count = (G.jokers and G.jokers.config and G.jokers.config.card_count or 0)
            + (G.consumeables and G.consumeables.config and G.consumeables.config.card_count or 0)
            + (G.deck and G.deck.config and G.deck.config.card_count or 0)
          local shop_decreased = (shop_count == initial_shop_count - 1)
          local dest_increased = (dest_count == initial_dest_count + 1)
          local money_deducted = (G.GAME.dollars == initial_money - card.cost.buy)
          if shop_decreased and dest_increased and money_deducted and G.STATE == G.STATES.SHOP then
            done = true
          end
        elseif args.voucher then
          local shop_count = (G.shop_vouchers and G.shop_vouchers.config and G.shop_vouchers.config.card_count or 0)
          local dest_count = 0
          if G.GAME.used_vouchers then
            for _ in pairs(G.GAME.used_vouchers) do
              dest_count = dest_count + 1
            end
          end
          local shop_decreased = (shop_count == initial_shop_count - 1)
          local dest_increased = (dest_count == initial_dest_count + 1)
          local money_deducted = (G.GAME.dollars == initial_money - card.cost.buy)

          if shop_decreased and dest_increased and money_deducted and G.STATE == G.STATES.SHOP then
            done = true
          end
        elseif args.pack then
          local money_deducted = (G.GAME.dollars == initial_money - card.cost.buy)
          local pack_cards_count = (G.pack_cards and G.pack_cards.config and G.pack_cards.config.card_count or 0)
          if money_deducted and pack_cards_count > 0 and G.STATE == G.STATES.SMODS_BOOSTER_OPENED then
            done = true
          end
        end

        if done then
          sendDebugMessage("Buy completed successfully", "BB.ENDPOINTS")
          send_response(BB_GAMESTATE.get_gamestate())
          return true
        end

        return false
      end,
    }))
  end,
}
