---@meta

-- ==========================================================================
-- Endpoint Type
-- ==========================================================================

---@class Endpoint
---@field name string The endpoint name
---@field description string Brief description of the endpoint
---@field schema table<string, SchemaField> Schema definition for arguments validation
---@field requires_state string[]? Optional list of required game states
---@field execute fun(args: table, send_response: fun(response: table)) Execute function

-- ==========================================================================
-- GameState Types
-- ==========================================================================

---@class GameState
---@field deck Deck? Current selected deck
---@field stake Stake? Current selected stake
---@field seed string? Seed used for the run
---@field state State Current game state
---@field round_num integer Current round number
---@field ante_num integer Current ante number
---@field money integer Current money amount
---@field used_vouchers table<string, string>? Vouchers used (name -> description)
---@field hands table<string, Hand>? Poker hands information
---@field round Round? Current round state
---@field blinds table<"small"|"big"|"boss", Blind>? Blind information
---@field jokers Area? Jokers area
---@field consumables Area? Consumables area
---@field hand Area? Hand area (available during playing phase)
---@field shop Area? Shop area (available during shop phase)
---@field vouchers Area? Vouchers area (available during shop phase)
---@field packs Area? Booster packs area (available during shop phase)
---@field won boolean? Whether the game has been won

---@alias Deck
---| "RED" # +1 discard every round
---| "BLUE" # +1 hand every round
---| "YELLOW" # Start with extra $10
---| "GREEN" # At end of each Round, $2 per remaining Hand $1 per remaining Discard Earn no Interest
---| "BLACK" # +1 Joker slot -1 hand every round
---| "MAGIC" # Start run with the Cristal Ball voucher and 2 copies of The Fool
---| "NEBULA" # Start run with the Telescope voucher and -1 consumable slot
---| "GHOST" # Spectral cards  may appear in the shop. Start with a Hex card
---| "ABANDONED" # Start run with no Face Cards in your deck
---| "CHECKERED" # Start run with 26 Spaces and 26 Hearts in deck
---| "ZODIAC" # Start run with Tarot Merchant, Planet Merchant, and Overstock
---| "PAINTED" # +2 hand size, -1 Joker slot
---| "ANAGLYPH" # After defeating each Boss Blind, gain a Double Tag
---| "PLASMA" # Balanced Chips and Mult when calculating score for played hand X2 base Blind size
---| "ERRATIC" # All Ranks and Suits in deck are randomized

---@alias Stake
---| "WHITE" # 1. Base Difficulty
---| "RED" # 2. Small Blind gives no reward money. Applies all previous Stakes
---| "GREEN" # 3. Required scores scales faster for each Ante. Applies all previous Stakes
---| "BLACK" # 4. Shop can have Eternal Jokers. Applies all previous Stakes
---| "BLUE" # 5. -1 Discard. Applies all previous Stakes
---| "PURPLE" # 6. Required score scales faster for each Ante. Applies all previous Stakes
---| "ORANGE" # 7. Shop can have Perishable Jokers. Applies all previous Stakes
---| "GOLD" # 8. Shop can have Rental Jokers. Applies all previous Stakes

---@alias State
---| "SELECTING_HAND" # 1
---| "HAND_PLAYED" # 2
---| "DRAW_TO_HAND" # 3
---| "GAME_OVER" # 4
---| "SHOP" # 5
---| "PLAY_TAROT" # 6
---| "BLIND_SELECT" # 7
---| "ROUND_EVAL" # 8
---| "TAROT_PACK" # 9
---| "PLANET_PACK" # 10
---| "MENU" # 11
---| "TUTORIAL" # 12
---| "SPLASH" # 13
---| "SANDBOX" # 14
---| "SPECTRAL_PACK" # 15
---| "DEMO_CTA" # 16
---| "STANDARD_PACK" # 17
---| "BUFFOON_PACK" # 18
---| "NEW_ROUND" # 19
---| "SMODS_BOOSTER_OPENED" # 999
---| "UNKNOWN"

---@class Hand
---@field order integer The importance/ordering of the hand
---@field level integer Level of the hand in the current run
---@field chips integer Current chip value for this hand
---@field mult integer Current multiplier value for this hand
---@field played integer Total number of times this hand has been played
---@field played_this_round integer Number of times this hand has been played this round
---@field example table<integer, table> Example cards showing what makes this hand (array of [card_key, is_scored])

---@class Round
---@field hands_left integer? Number of hands remaining in this round
---@field hands_played integer? Number of hands played in this round
---@field discards_left integer? Number of discards remaining in this round
---@field discards_used integer? Number of discards used in this round
---@field reroll_cost integer? Current cost to reroll the shop
---@field chips integer? Current chips scored in this round

---@class Blind
---@field type "SMALL" | "BIG" | "BOSS" Type of the blind
---@field status "SELECT" | "CURRENT" | "UPCOMING" | "DEFEATED" | "SKIPPED" Status of the bilnd
---@field name string Name of the blind (e.g., "Small", "Big" or the Boss name)
---@field effect string Description of the blind's effect
---@field score integer Score requirement to beat this blind
---@field tag_name string? Name of the tag associated with this blind (Small/Big only)
---@field tag_effect string? Description of the tag's effect (Small/Big only)

---@class Area
---@field count integer Current number of cards in this area
---@field limit integer Maximum number of cards allowed in this area
---@field highlighted_limit integer? Maximum number of cards that can be highlighted (hand area only)
---@field cards Card[] Array of cards in this area

---@class Card
---@field id integer Unique identifier for the card (sort_id)
---@field set "default" | "joker" | "tarot" | "planet" | "spectral" | "enhanced" | "booster" Card set/type
---@field label string Display label/name of the card
---@field value Card.Value Value information for the card
---@field modifier Card.Modifier Modifier information (seals, editions, enhancements)
---@field state Card.State Current state information (debuff, hidden, highlighted)
---@field cost Card.Cost Cost information (buy/sell prices)

---@class Card.Value
---@field suit "H" | "D" | "C" | "S"? Suit (Hearts, Diamonds, Clubs, Spades) - only for playing cards
---@field value "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "T" | "J" | "Q" | "K" | "A"? Rank - only for playing cards
---@field effect string Description of the card's effect (from UI)

---@class Card.Modifier
---@field seal "red" | "blue" | "gold" | "purple"? Seal type
---@field edition "holo" | "foil" | "polychrome" | "negative"? Edition type
---@field enhancement "bonus" | "mult" | "wild" | "glass" | "steel" | "stone" | "gold" | "lucky"? Enhancement type
---@field eternal boolean? If true, card cannot be sold or destroyed
---@field perishable integer? Number of rounds remaining (only if > 0)
---@field rental boolean? If true, card costs money at end of round

---@class Card.State
---@field debuff boolean? If true, card is debuffed and won't score
---@field hidden boolean? If true, card is face down (facing == "back")
---@field highlight boolean? If true, card is currently highlighted

---@class Card.Cost
---@field sell integer Sell value of the card
---@field buy integer Buy price of the card (if in shop)
