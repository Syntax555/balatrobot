-- src/lua/endpoints/add.lua
-- Add Endpoint
--
-- Add a new card to the game using SMODS.add_card

---@class Endpoint.Add.Args
---@field key Card.Key The card key to add (j_* for jokers, c_* for consumables, v_* for vouchers, SUIT_RANK for playing cards)

-- Suit conversion table for playing cards
local SUIT_MAP = {
  H = "Hearts",
  D = "Diamonds",
  C = "Clubs",
  S = "Spades",
}

-- Rank conversion table for playing cards
local RANK_MAP = {
  ["2"] = "2",
  ["3"] = "3",
  ["4"] = "4",
  ["5"] = "5",
  ["6"] = "6",
  ["7"] = "7",
  ["8"] = "8",
  ["9"] = "9",
  T = "10",
  J = "Jack",
  Q = "Queen",
  K = "King",
  A = "Ace",
}

---Detect card type based on key prefix or pattern
---@param key string The card key
---@return string|nil card_type The detected card type or nil if invalid
local function detect_card_type(key)
  local prefix = key:sub(1, 2)

  if prefix == "j_" then
    return "joker"
  elseif prefix == "c_" then
    return "consumable"
  elseif prefix == "v_" then
    return "voucher"
  else
    -- Check if it's a playing card format (SUIT_RANK like H_A)
    if key:match("^[HDCS]_[2-9TJQKA]$") then
      return "playing_card"
    else
      return nil
    end
  end
end

---Parse playing card key into rank and suit
---@param key string The playing card key (e.g., "H_A")
---@return string|nil rank The rank (e.g., "Ace", "10")
---@return string|nil suit The suit (e.g., "Hearts", "Spades")
local function parse_playing_card_key(key)
  local suit_char = key:sub(1, 1)
  local rank_char = key:sub(3, 3)

  local suit = SUIT_MAP[suit_char]
  local rank = RANK_MAP[rank_char]

  if not suit or not rank then
    return nil, nil
  end

  return rank, suit
end

---@type Endpoint
return {
  name = "add",
  description = "Add a new card to the game (joker, consumable, voucher, or playing card)",
  schema = {
    key = {
      type = "string",
      required = true,
      description = "Card key (j_* for jokers, c_* for consumables, v_* for vouchers, SUIT_RANK for playing cards like H_A)",
    },
  },
  requires_state = { G.STATES.SELECTING_HAND, G.STATES.SHOP, G.STATES.ROUND_EVAL },

  ---@param args Endpoint.Add.Args The arguments (key)
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    sendDebugMessage("Init add()", "BB.ENDPOINTS")

    -- Detect card type
    local card_type = detect_card_type(args.key)

    if not card_type then
      send_response({
        error = "Invalid card key format. Expected: joker (j_*), consumable (c_*), voucher (v_*), or playing card (SUIT_RANK)",
        error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
      })
      return
    end

    -- Special validation for playing cards - can only be added in SELECTING_HAND state
    if card_type == "playing_card" and G.STATE ~= G.STATES.SELECTING_HAND then
      send_response({
        error = "Playing cards can only be added in SELECTING_HAND state",
        error_code = BB_ERRORS.STATE_INVALID_STATE,
      })
      return
    end

    -- Special validation for vouchers - can only be added in SHOP state
    if card_type == "voucher" and G.STATE ~= G.STATES.SHOP then
      send_response({
        error = "Vouchers can only be added in SHOP state",
        error_code = BB_ERRORS.STATE_INVALID_STATE,
      })
      return
    end

    -- Build SMODS.add_card parameters based on card type
    local params

    if card_type == "playing_card" then
      -- Parse the playing card key
      local rank, suit = parse_playing_card_key(args.key)
      params = {
        rank = rank,
        suit = suit,
      }
    elseif card_type == "voucher" then
      params = {
        key = args.key,
        area = G.shop_vouchers,
      }
    else
      -- For jokers and consumables - just pass the key
      params = {
        key = args.key,
      }
    end

    -- Track initial state for verification
    local initial_joker_count = G.jokers and #G.jokers.cards or 0
    local initial_consumable_count = G.consumeables and #G.consumeables.cards or 0
    local initial_voucher_count = G.shop_vouchers and #G.shop_vouchers.cards or 0
    local initial_hand_count = G.hand and #G.hand.cards or 0

    sendDebugMessage("Initial voucher count: " .. initial_voucher_count, "BB.ENDPOINTS")

    -- Call SMODS.add_card with error handling
    local success, _ = pcall(SMODS.add_card, params)

    if not success then
      send_response({
        error = "Failed to add card: " .. args.key,
        error_code = BB_ERRORS.SCHEMA_INVALID_VALUE,
      })
      return
    end

    sendDebugMessage("SMODS.add_card called for: " .. args.key .. " (" .. card_type .. ")", "BB.ENDPOINTS")

    -- Wait for card addition to complete with event-based verification
    G.E_MANAGER:add_event(Event({
      trigger = "condition",
      blocking = false,
      func = function()
        -- Verify card was added based on card type
        local added = false

        if card_type == "joker" then
          added = G.jokers and G.jokers.config and G.jokers.config.card_count == initial_joker_count + 1
        elseif card_type == "consumable" then
          added = G.consumeables
            and G.consumeables.config
            and G.consumeables.config.card_count == initial_consumable_count + 1
        elseif card_type == "voucher" then
          added = G.shop_vouchers
            and G.shop_vouchers.config
            and G.shop_vouchers.config.card_count == initial_voucher_count + 1
        elseif card_type == "playing_card" then
          added = G.hand and G.hand.config and G.hand.config.card_count == initial_hand_count + 1
        end

        -- Check state stability
        local state_stable = G.STATE_COMPLETE == true

        -- Check valid state (still in one of the allowed states)
        local valid_state = (
          G.STATE == G.STATES.SHOP
          or G.STATE == G.STATES.SELECTING_HAND
          or G.STATE == G.STATES.ROUND_EVAL
        )

        -- All conditions must be met
        if added and state_stable and valid_state then
          sendDebugMessage("Card added successfully: " .. args.key, "BB.ENDPOINTS")
          send_response(BB_GAMESTATE.get_gamestate())
          return true
        end

        return false
      end,
    }))
  end,
}
