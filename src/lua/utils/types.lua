---@meta types

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
---@field pack Area? Currently open pack (available during opeing pack phase)
---@field shop Area? Shop area (available during shop phase)
---@field vouchers Area? Vouchers area (available during shop phase)
---@field packs Area? Booster packs area (available during shop phase)
---@field won boolean? Whether the game has been won

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
---@field type Blind.Type Type of the blind
---@field status Blind.Status Status of the bilnd
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
---@field key Card.Key Specific card key (e.g., "c_fool", "j_brainstorm, "v_overstock", ...)
---@field set Card.Set Card set/type
---@field label string Display label/name of the card
---@field value Card.Value Value information for the card
---@field modifier Card.Modifier Modifier information (seals, editions, enhancements)
---@field state Card.State Current state information (debuff, hidden, highlighted)
---@field cost Card.Cost Cost information (buy/sell prices)

---@class Card.Value
---@field suit Card.Value.Suit? Suit (Hearts, Diamonds, Clubs, Spades) - only for playing cards
---@field rank Card.Value.Rank? Rank - only for playing cards
---@field effect string Description of the card's effect (from UI)

---@class Card.Modifier
---@field seal Card.Modifier.Seal? Seal type (playing cards)
---@field edition Card.Modifier.Edition? Edition type (jokers, playing cards and NEGATIVE consumables)
---@field enhancement Card.Modifier.Enhancement? Enhancement type (playing cards)
---@field eternal boolean? If true, card cannot be sold or destroyed (jokers only)
---@field perishable integer? Number of rounds remaining (only if > 0) (jokers only)
---@field rental boolean? If true, card costs money at end of round (jokers only)

---@class Card.State
---@field debuff boolean? If true, card is debuffed and won't score
---@field hidden boolean? If true, card is face down (facing == "back")
---@field highlight boolean? If true, card is currently highlighted

---@class Card.Cost
---@field sell integer Sell value of the card
---@field buy integer Buy price of the card (if in shop)

-- ==========================================================================
-- Endpoint Type
-- ==========================================================================

---@class Endpoint
---@field name string The endpoint name
---@field description string Brief description of the endpoint
---@field schema table<string, SchemaField> Schema definition for arguments validation
---@field requires_state integer[]? Optional list of required game states
---@field execute fun(args: Request.Params, send_response: fun(response: table)) Execute function

-- ==========================================================================
-- Request Types (JSON-RPC 2.0)
-- ==========================================================================

---@class Request
---@field jsonrpc "2.0"
---@field method Request.Method Request method name. This corresponse to the endpoint name
---@field params Request.Params Params to use for the requests
---@field id integer|string|nil Request ID

---@alias Request.Method
---| "echo" | "endpoint" | "error" | "state" | "validation" #  Test Endpoints
---| "add" | "buy" | "cash_out" | "discard" | "gamestate" | "health" | "load"
---| "menu" | "next_round" | "play" | "rearrange" | "reroll" | "save" | "select"
---| "sell" | "set" | "skip" | "start" | "use"

---@alias Request.Params
---| Endpoint.Add.Params
---| Endpoint.Buy.Params
---| Endpoint.Discard.Params
---| Endpoint.Load.Params
---| Endpoint.Play.Params
---| Endpoint.Rearrange.Params
---| Endpoint.Save.Params
---| Endpoint.Sell.Params
---| Endpoint.Set.Params
---| Endpoint.Run.Params
---| Endpoint.Use.Params
---| TestEndpoint.Echo.Params
---| TestEndpoint.Endpoint.Params
---| TestEndpoint.Error.Params
---| TestEndpoint.State.Params
---| TestEndpoint.Validation.Params

-- ==========================================================================
-- Response Types (JSON-RPC 2.0)
-- ==========================================================================

---@class PathResponse
---@field success boolean Whether the request was successful
---@field path string Path to the file

---@class HealthResponse
---@field success boolean Whether the request was successful

---@alias GameStateResponse GameState

---@class ResponseSuccess
---@field jsonrpc "2.0"
---@field result HealthResponse | PathResponse | GameStateResponse Response payload
---@field id integer|string|nil Request ID

---@class ResponseError
---@field jsonrpc "2.0"
---@field error ResponseError.Error Response error
---@field id integer|string|nil Request ID

---@class ResponseError.Error
---@field code ErrorCode Numeric error code following JSON-RPC 2.0 convention
---@field message string Human-readable error message
---@field data ResponseError.Error.Data

---@class ResponseError.Error.Data
---@field name ErrorName Semantic error code
