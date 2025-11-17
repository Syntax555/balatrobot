---Simplified game state extraction utilities
---This module provides a clean, simplified interface for extracting game state
---according to the new gamestate specification
---@module 'gamestate'
local gamestate = {}

-- ==========================================================================
-- State Name Mapping
-- ==========================================================================

---Converts numeric state ID to string state name
---@param state_num number The numeric state value from G.STATE
---@return string state_name The string name of the state (e.g., "SELECTING_HAND")
local function get_state_name(state_num)
  if not G or not G.STATES then
    return "UNKNOWN"
  end

  for name, value in pairs(G.STATES) do
    if value == state_num then
      return name
    end
  end

  return "UNKNOWN"
end

-- ==========================================================================
-- Deck Name Mapping
-- ==========================================================================

local DECK_KEY_TO_NAME = {
  b_red = "RED",
  b_blue = "BLUE",
  b_yellow = "YELLOW",
  b_green = "GREEN",
  b_black = "BLACK",
  b_magic = "MAGIC",
  b_nebula = "NEBULA",
  b_ghost = "GHOST",
  b_abandoned = "ABANDONED",
  b_checkered = "CHECKERED",
  b_zodiac = "ZODIAC",
  b_painted = "PAINTED",
  b_anaglyph = "ANAGLYPH",
  b_plasma = "PLASMA",
  b_erratic = "ERRATIC",
}

---Converts deck key to string deck name
---@param deck_key string The key from G.P_CENTERS (e.g., "b_red")
---@return string? deck_name The string name of the deck (e.g., "RED"), or nil if not found
local function get_deck_name(deck_key)
  return DECK_KEY_TO_NAME[deck_key]
end

-- ==========================================================================
-- Stake Name Mapping
-- ==========================================================================

local STAKE_LEVEL_TO_NAME = {
  [1] = "WHITE",
  [2] = "RED",
  [3] = "GREEN",
  [4] = "BLACK",
  [5] = "BLUE",
  [6] = "PURPLE",
  [7] = "ORANGE",
  [8] = "GOLD",
}

---Converts numeric stake level to string stake name
---@param stake_num number The numeric stake value from G.GAME.stake (1-8)
---@return string? stake_name The string name of the stake (e.g., "WHITE"), or nil if not found
local function get_stake_name(stake_num)
  return STAKE_LEVEL_TO_NAME[stake_num]
end

-- ==========================================================================
-- Card UI Description (from old utils)
-- ==========================================================================

---Gets the description text for a card by reading from its UI elements
---@param card table The card object
---@return string description The description text from UI
local function get_card_ui_description(card)
  -- Generate the UI structure (same as hover tooltip)
  card:hover()
  card:stop_hover()
  local ui_table = card.ability_UIBox_table
  if not ui_table then
    return ""
  end

  -- Extract all text nodes from the UI tree
  local texts = {}

  -- The UI table has main/info/type sections
  if ui_table.main then
    for _, line in ipairs(ui_table.main) do
      local line_texts = {}
      for _, section in ipairs(line) do
        if section.config and section.config.text then
          -- normal text and colored text
          line_texts[#line_texts + 1] = section.config.text
        elseif section.nodes then
          for _, node in ipairs(section.nodes) do
            if node.config and node.config.text then
              -- hightlighted text
              line_texts[#line_texts + 1] = node.config.text
            end
          end
        end
      end
      texts[#texts + 1] = table.concat(line_texts, "")
    end
  end

  -- Join text lines with spaces (in the game these are separated by newlines)
  return table.concat(texts, " ")
end

-- ==========================================================================
-- Card Component Extractors
-- ==========================================================================

---Extracts modifier information from a card
---@param card table The card object
---@return Card.Modifier modifier The Card.Modifier object
local function extract_card_modifier(card)
  local modifier = {}

  -- Seal (direct property)
  if card.seal then
    modifier.seal = card.seal
  end

  -- Edition (table with type/key)
  if card.edition and card.edition.type then
    modifier.edition = card.edition.type
  end

  -- Enhancement (from ability.name for enhanced cards)
  if card.ability and card.ability.effect and card.ability.effect ~= "Base" then
    modifier.enhancement = card.ability.effect
  end

  -- Eternal (boolean from ability)
  if card.ability and card.ability.eternal then
    modifier.eternal = true
  end

  -- Perishable (from perish_tally - only include if > 0)
  if card.ability and card.ability.perish_tally and card.ability.perish_tally > 0 then
    modifier.perishable = card.ability.perish_tally
  end

  -- Rental (boolean from ability)
  if card.ability and card.ability.rental then
    modifier.rental = true
  end

  return modifier
end

---Extracts value information from a card
---@param card table The card object
---@return Card.Value value The Card.Value object
local function extract_card_value(card)
  local value = {}

  -- Suit and rank (for playing cards)
  if card.config and card.config.card then
    if card.config.card.suit then
      value.suit = card.config.card.suit
    end
    if card.config.card.value then
      value.value = card.config.card.value
    end
  end

  -- Effect description (for all cards)
  value.effect = get_card_ui_description(card)

  return value
end

---Extracts state information from a card
---@param card table The card object
---@return Card.State state The Card.State object
local function extract_card_state(card)
  local state = {}

  -- Debuff
  if card.debuff then
    state.debuff = true
  end

  -- Hidden (facing == "back")
  if card.facing and card.facing == "back" then
    state.hidden = true
  end

  -- Highlighted
  if card.highlighted then
    state.highlight = true
  end

  return state
end

---Extracts cost information from a card
---@param card table The card object
---@return Card.Cost cost The Card.Cost object
local function extract_card_cost(card)
  return {
    sell = card.sell_cost or 0,
    buy = card.cost or 0,
  }
end

-- ==========================================================================
-- Card Extractor
-- ==========================================================================

---Extracts a complete Card object from a game card
---@param card table The game card object
---@return Card card The Card object
local function extract_card(card)
  -- Determine set
  local set = "default"
  if card.ability and card.ability.set then
    local ability_set = card.ability.set
    if ability_set == "Joker" then
      set = "joker"
    elseif ability_set == "Tarot" then
      set = "tarot"
    elseif ability_set == "Planet" then
      set = "planet"
    elseif ability_set == "Spectral" then
      set = "spectral"
    elseif card.ability.effect and card.ability.effect ~= "Base" then
      set = "enhanced"
    end
  end

  return {
    id = card.sort_id or 0,
    set = set,
    label = card.label or "",
    value = extract_card_value(card),
    modifier = extract_card_modifier(card),
    state = extract_card_state(card),
    cost = extract_card_cost(card),
  }
end

-- ==========================================================================
-- Area Extractor
-- ==========================================================================

---Extracts an Area object from a game area (like G.jokers, G.hand, etc.)
---@param area table The game area object
---@return Area? area_data The Area object
local function extract_area(area)
  if not area then
    return nil
  end

  local cards = {}
  if area.cards then
    for i, card in pairs(area.cards) do
      cards[i] = extract_card(card)
    end
  end

  local area_data = {
    count = (area.config and area.config.card_count) or 0,
    limit = (area.config and area.config.card_limit) or 0,
    cards = cards,
  }

  -- Add highlighted_limit if available (for hand area)
  if area.config and area.config.highlighted_limit then
    area_data.highlighted_limit = area.config.highlighted_limit
  end

  return area_data
end

-- ==========================================================================
-- Poker Hands Extractor
-- ==========================================================================

---Extracts poker hands information
---@param hands table The G.GAME.hands table
---@return table<string, Hand> hands_data The hands information
local function extract_hand_info(hands)
  if not hands then
    return {}
  end

  local hands_data = {}
  for name, hand in pairs(hands) do
    hands_data[name] = {
      order = hand.order or 0,
      level = hand.level or 1,
      chips = hand.chips or 0,
      mult = hand.mult or 0,
      played = hand.played or 0,
      played_this_round = hand.played_this_round or 0,
      example = hand.example or {},
    }
  end

  return hands_data
end

-- ==========================================================================
-- Round Info Extractor
-- ==========================================================================

---Extracts round state information
---@return Round round The Round object
local function extract_round_info()
  if not G or not G.GAME or not G.GAME.current_round then
    return {}
  end

  local round = {}

  if G.GAME.current_round.hands_left then
    round.hands_left = G.GAME.current_round.hands_left
  end

  if G.GAME.current_round.hands_played then
    round.hands_played = G.GAME.current_round.hands_played
  end

  if G.GAME.current_round.discards_left then
    round.discards_left = G.GAME.current_round.discards_left
  end

  if G.GAME.current_round.discards_used then
    round.discards_used = G.GAME.current_round.discards_used
  end

  if G.GAME.current_round.reroll_cost then
    round.reroll_cost = G.GAME.current_round.reroll_cost
  end

  -- Chips is stored in G.GAME not G.GAME.current_round
  if G.GAME.chips then
    round.chips = G.GAME.chips
  end

  return round
end

-- ==========================================================================
-- Blind Information (adapted from old utils)
-- ==========================================================================

---Gets comprehensive blind information for the current ante
---@return table<string, Blind> blinds Information about small, big, and boss blinds
local function get_blinds_info()
  local blinds = {
    small = {
      name = "Small",
      score = 0,
      status = "pending",
      effect = "",
      tag_name = "",
      tag_effect = "",
    },
    big = {
      name = "Big",
      score = 0,
      status = "pending",
      effect = "",
      tag_name = "",
      tag_effect = "",
    },
    boss = {
      name = "",
      score = 0,
      status = "pending",
      effect = "",
      tag_name = "",
      tag_effect = "",
    },
  }

  if not G.GAME or not G.GAME.round_resets then
    return blinds
  end

  -- Get base blind amount for current ante
  local ante = G.GAME.round_resets.ante or 1
  local base_amount = get_blind_amount(ante) ---@diagnostic disable-line: undefined-global

  -- Apply ante scaling
  local ante_scaling = G.GAME.starting_params.ante_scaling or 1

  -- Small blind (1x multiplier)
  blinds.small.score = math.floor(base_amount * 1 * ante_scaling)
  if G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Small then
    local status = G.GAME.round_resets.blind_states.Small
    if status == "Defeated" or status == "Skipped" then
      blinds.small.status = "completed"
    elseif status == "Current" or status == "Select" then
      blinds.small.status = "current"
    end
  end

  -- Big blind (1.5x multiplier)
  blinds.big.score = math.floor(base_amount * 1.5 * ante_scaling)
  if G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Big then
    local status = G.GAME.round_resets.blind_states.Big
    if status == "Defeated" or status == "Skipped" then
      blinds.big.status = "completed"
    elseif status == "Current" or status == "Select" then
      blinds.big.status = "current"
    end
  end

  -- Boss blind
  local boss_choice = G.GAME.round_resets.blind_choices and G.GAME.round_resets.blind_choices.Boss
  if boss_choice and G.P_BLINDS and G.P_BLINDS[boss_choice] then
    local boss_blind = G.P_BLINDS[boss_choice]
    blinds.boss.name = boss_blind.name or ""
    blinds.boss.score = math.floor(base_amount * (boss_blind.mult or 2) * ante_scaling)

    if G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Boss then
      local status = G.GAME.round_resets.blind_states.Boss
      if status == "Defeated" or status == "Skipped" then
        blinds.boss.status = "completed"
      elseif status == "Current" or status == "Select" then
        blinds.boss.status = "current"
      end
    end

    -- Get boss effect description
    if boss_blind.key and localize then ---@diagnostic disable-line: undefined-global
      local loc_target = localize({ ---@diagnostic disable-line: undefined-global
        type = "raw_descriptions",
        key = boss_blind.key,
        set = "Blind",
        vars = { "" },
      })
      if loc_target and loc_target[1] then
        blinds.boss.effect = loc_target[1]
        if loc_target[2] then
          blinds.boss.effect = blinds.boss.effect .. " " .. loc_target[2]
        end
      end
    end
  else
    blinds.boss.name = "Boss"
    blinds.boss.score = math.floor(base_amount * 2 * ante_scaling)
    if G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Boss then
      local status = G.GAME.round_resets.blind_states.Boss
      if status == "Defeated" or status == "Skipped" then
        blinds.boss.status = "completed"
      elseif status == "Current" or status == "Select" then
        blinds.boss.status = "current"
      end
    end
  end

  -- Get tag information for Small and Big blinds
  if G.GAME.round_resets.blind_tags and G.P_TAGS then
    -- Small blind tag
    local small_tag_key = G.GAME.round_resets.blind_tags.Small
    if small_tag_key and G.P_TAGS[small_tag_key] then
      local tag_data = G.P_TAGS[small_tag_key]
      blinds.small.tag_name = tag_data.name or ""

      -- Get tag effect description
      if localize then ---@diagnostic disable-line: undefined-global
        local tag_effect = localize({ ---@diagnostic disable-line: undefined-global
          type = "raw_descriptions",
          key = small_tag_key,
          set = "Tag",
          vars = { "" },
        })
        if tag_effect and tag_effect[1] then
          blinds.small.tag_effect = tag_effect[1]
          if tag_effect[2] then
            blinds.small.tag_effect = blinds.small.tag_effect .. " " .. tag_effect[2]
          end
        end
      end
    end

    -- Big blind tag
    local big_tag_key = G.GAME.round_resets.blind_tags.Big
    if big_tag_key and G.P_TAGS[big_tag_key] then
      local tag_data = G.P_TAGS[big_tag_key]
      blinds.big.tag_name = tag_data.name or ""

      -- Get tag effect description
      if localize then ---@diagnostic disable-line: undefined-global
        local tag_effect = localize({ ---@diagnostic disable-line: undefined-global
          type = "raw_descriptions",
          key = big_tag_key,
          set = "Tag",
          vars = { "" },
        })
        if tag_effect and tag_effect[1] then
          blinds.big.tag_effect = tag_effect[1]
          if tag_effect[2] then
            blinds.big.tag_effect = tag_effect[2] .. " " .. tag_effect[2]
          end
        end
      end
    end
  end

  -- Boss blind has no tags (tag_name and tag_effect remain empty strings)

  return blinds
end

-- ==========================================================================
-- Main Gamestate Extractor
-- ==========================================================================

---Extracts the simplified game state according to the new specification
---@return GameState gamestate The complete simplified game state
function gamestate.get_gamestate()
  if not G then
    return {
      state = "UNKNOWN",
      round_num = 0,
      ante_num = 0,
      money = 0,
    }
  end

  local state_data = {
    state = get_state_name(G.STATE),
  }

  -- Basic game info
  if G.GAME then
    state_data.round_num = G.GAME.round or 0
    state_data.ante_num = (G.GAME.round_resets and G.GAME.round_resets.ante) or 0
    state_data.money = G.GAME.dollars or 0

    -- Deck (optional)
    if G.GAME.selected_back and G.GAME.selected_back.effect and G.GAME.selected_back.effect.center then
      local deck_key = G.GAME.selected_back.effect.center.key
      state_data.deck = get_deck_name(deck_key)
    end

    -- Stake (optional)
    if G.GAME.stake then
      state_data.stake = get_stake_name(G.GAME.stake)
    end

    -- Seed (optional)
    if G.GAME.pseudorandom and G.GAME.pseudorandom.seed then
      state_data.seed = G.GAME.pseudorandom.seed
    end

    -- Used vouchers (table<string, string>)
    if G.GAME.used_vouchers then
      local used_vouchers = {}
      for voucher_name, voucher_data in pairs(G.GAME.used_vouchers) do
        if type(voucher_data) == "table" and voucher_data.description then
          used_vouchers[voucher_name] = voucher_data.description
        else
          used_vouchers[voucher_name] = ""
        end
      end
      state_data.used_vouchers = used_vouchers
    end

    -- Poker hands
    if G.GAME.hands then
      state_data.hands = extract_hand_info(G.GAME.hands)
    end

    -- Round info
    state_data.round = extract_round_info()

    -- Blinds info
    state_data.blinds = get_blinds_info()
  end

  -- Always available areas
  state_data.jokers = extract_area(G.jokers)
  state_data.consumables = extract_area(G.consumeables) -- Note: typo in game code

  -- Phase-specific areas
  -- Hand (available during playing phase)
  if G.hand then
    state_data.hand = extract_area(G.hand)
  end

  -- Shop areas (available during shop phase)
  if G.shop_jokers then
    state_data.shop = extract_area(G.shop_jokers)
  end

  if G.shop_vouchers then
    state_data.vouchers = extract_area(G.shop_vouchers)
  end

  return state_data
end

return gamestate
