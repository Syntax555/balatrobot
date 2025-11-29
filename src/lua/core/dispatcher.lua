-- src/lua/core/dispatcher.lua
-- Request Dispatcher with 4-Tier Validation
--
-- Routes API calls to endpoints with comprehensive validation:
-- 1. Protocol validation (has name, arguments)
-- 2. Schema validation (via Validator)
-- 3. Game state validation (requires_state check)
-- 4. Execute endpoint (catch semantic errors and enrich)
--
-- Responsibilities:
-- - Auto-discover and register all endpoints at startup (fail-fast)
-- - Validate request structure at protocol level
-- - Route requests to appropriate endpoints
-- - Delegate schema validation to Validator module
-- - Enforce game state requirements
-- - Execute endpoints with comprehensive error handling
-- - Send responses and rich error messages via Server module

---@type Validator
local Validator = assert(SMODS.load_file("src/lua/core/validator.lua"))()
---@type ErrorCodes
local errors = assert(SMODS.load_file("src/lua/utils/errors.lua"))()

-- State name lookup cache (built lazily from G.STATES)
---@type table<number, string>?
local STATE_NAME_CACHE = nil

--- Get the name of a state from its numeric value
--- Builds a reverse mapping from G.STATES on first call
---@param state_value number The numeric state value
---@return string state_name The state name (or stringified number if not found)
local function get_state_name(state_value)
  -- Build cache on first use
  if not STATE_NAME_CACHE then
    STATE_NAME_CACHE = {}
    if G and G.STATES then
      for name, value in pairs(G.STATES) do
        STATE_NAME_CACHE[value] = name
      end
    end
  end

  -- Look up the name, fall back to stringified number
  return STATE_NAME_CACHE[state_value] or tostring(state_value)
end

---@class Dispatcher
---@field endpoints table<string, Endpoint> Endpoint registry mapping names to modules
---@field Server table? Reference to Server module for sending responses
BB_DISPATCHER = {

  -- Endpoint registry: name -> endpoint module
  ---@type table<string, Endpoint>
  endpoints = {},

  -- Reference to Server module (set after initialization)
  ---@type table?
  Server = nil,
}

--- Validate that an endpoint module has the required structure
---@param endpoint Endpoint The endpoint module to validate
---@return boolean success
---@return string? error_message
local function validate_endpoint_structure(endpoint)
  -- Check required fields
  if not endpoint.name or type(endpoint.name) ~= "string" then
    return false, "Endpoint missing 'name' field (string)"
  end

  if not endpoint.description or type(endpoint.description) ~= "string" then
    return false, "Endpoint '" .. endpoint.name .. "' missing 'description' field (string)"
  end

  if not endpoint.schema or type(endpoint.schema) ~= "table" then
    return false, "Endpoint '" .. endpoint.name .. "' missing 'schema' field (table)"
  end

  if not endpoint.execute or type(endpoint.execute) ~= "function" then
    return false, "Endpoint '" .. endpoint.name .. "' missing 'execute' field (function)"
  end

  -- requires_state is optional but must be nil or table if present
  if endpoint.requires_state ~= nil and type(endpoint.requires_state) ~= "table" then
    return false, "Endpoint '" .. endpoint.name .. "' 'requires_state' must be nil or table"
  end

  -- Validate schema structure (basic check)
  for field_name, field_schema in pairs(endpoint.schema) do
    if type(field_schema) ~= "table" then
      return false, "Endpoint '" .. endpoint.name .. "' schema field '" .. field_name .. "' must be a table"
    end
    if not field_schema.type then
      return false, "Endpoint '" .. endpoint.name .. "' schema field '" .. field_name .. "' missing 'type' definition"
    end
  end

  return true
end

--- Register a single endpoint
--- Validates the endpoint structure and adds it to the registry
---@param endpoint Endpoint The endpoint module to register
---@return boolean success
---@return string? error_message
function BB_DISPATCHER.register(endpoint)
  -- Validate endpoint structure
  local valid, err = validate_endpoint_structure(endpoint)
  if not valid then
    return false, err
  end

  -- Check for duplicate names
  if BB_DISPATCHER.endpoints[endpoint.name] then
    return false, "Endpoint '" .. endpoint.name .. "' is already registered"
  end

  -- Register endpoint
  BB_DISPATCHER.endpoints[endpoint.name] = endpoint
  sendDebugMessage("Registered endpoint: " .. endpoint.name, "BB.DISPATCHER")

  return true
end

--- Load all endpoint modules from a directory
--- Loads .lua files and registers each endpoint (fail-fast)
---@param endpoint_files string[] List of endpoint file paths relative to mod root
---@return boolean success
---@return string? error_message
function BB_DISPATCHER.load_endpoints(endpoint_files)
  local loaded_count = 0

  for _, filepath in ipairs(endpoint_files) do
    sendDebugMessage("Loading endpoint: " .. filepath, "BB.DISPATCHER")

    -- Load endpoint module (fail-fast on errors)
    local success, endpoint = pcall(function()
      return assert(SMODS.load_file(filepath))()
    end)

    if not success then
      return false, "Failed to load endpoint '" .. filepath .. "': " .. tostring(endpoint)
    end

    -- Register endpoint (fail-fast on validation errors)
    local reg_success, reg_err = BB_DISPATCHER.register(endpoint)
    if not reg_success then
      return false, "Failed to register endpoint '" .. filepath .. "': " .. reg_err
    end

    loaded_count = loaded_count + 1
  end

  sendDebugMessage("Loaded " .. loaded_count .. " endpoint(s)", "BB.DISPATCHER")
  return true
end

--- Initialize the dispatcher
--- Loads all endpoints from the provided list
---@param server_module table Reference to Server module for sending responses
---@param endpoint_files string[]? Optional list of endpoint file paths (default: health and gamestate)
---@return boolean success
function BB_DISPATCHER.init(server_module, endpoint_files)
  BB_DISPATCHER.Server = server_module

  -- Default endpoint files if none provided
  endpoint_files = endpoint_files or {
    "src/lua/endpoints/health.lua",
  }

  -- Load all endpoints (fail-fast)
  local success, err = BB_DISPATCHER.load_endpoints(endpoint_files)
  if not success then
    sendErrorMessage("Dispatcher initialization failed: " .. err, "BB.DISPATCHER")
    return false
  end

  sendDebugMessage("Dispatcher initialized successfully", "BB.DISPATCHER")
  return true
end

--- Send an error response via Server module
---@param message string Error message
---@param error_code string Error code
function BB_DISPATCHER.send_error(message, error_code)
  if not BB_DISPATCHER.Server then
    sendDebugMessage("Cannot send error - Server not initialized", "BB.DISPATCHER")
    return
  end

  BB_DISPATCHER.Server.send_error(message, error_code)
end

--- Dispatch a request to the appropriate endpoint
--- Performs 4-tier validation and executes the endpoint
---@param request table The parsed JSON request
function BB_DISPATCHER.dispatch(request)
  -- =================================================================
  -- TIER 1: Protocol Validation
  -- =================================================================

  -- Validate request has 'name' field
  if not request.name or type(request.name) ~= "string" then
    BB_DISPATCHER.send_error("Request missing 'name' field", errors.PROTO_MISSING_NAME)
    return
  end

  -- Validate request has 'arguments' field
  if not request.arguments then
    BB_DISPATCHER.send_error("Request missing 'arguments' field", errors.PROTO_MISSING_ARGUMENTS)
    return
  end

  -- Find endpoint
  local endpoint = BB_DISPATCHER.endpoints[request.name]
  if not endpoint then
    BB_DISPATCHER.send_error("Unknown endpoint: " .. request.name, errors.PROTO_UNKNOWN_ENDPOINT)
    return
  end

  sendDebugMessage("Dispatching: " .. request.name, "BB.DISPATCHER")

  -- =================================================================
  -- TIER 2: Schema Validation
  -- =================================================================

  local valid, err_msg, err_code = Validator.validate(request.arguments, endpoint.schema)
  if not valid then
    -- When validation fails, err_msg and err_code are guaranteed to be non-nil
    BB_DISPATCHER.send_error(err_msg or "Validation failed", err_code or "VALIDATION_ERROR")
    return
  end

  -- =================================================================
  -- TIER 3: Game State Validation
  -- =================================================================

  if endpoint.requires_state then
    local current_state = G and G.STATE or "UNKNOWN"
    local state_valid = false

    for _, required_state in ipairs(endpoint.requires_state) do
      if current_state == required_state then
        state_valid = true
        break
      end
    end

    if not state_valid then
      -- Convert state numbers to names for the error message
      local state_names = {}
      for _, state in ipairs(endpoint.requires_state) do
        table.insert(state_names, get_state_name(state))
      end

      BB_DISPATCHER.send_error(
        "Endpoint '" .. request.name .. "' requires one of these states: " .. table.concat(state_names, ", "),
        errors.STATE_INVALID_STATE
      )
      return
    end
  end

  -- =================================================================
  -- TIER 4: Execute Endpoint
  -- =================================================================

  -- Create send_response callback that uses Server.send_response
  local function send_response(response)
    if BB_DISPATCHER.Server then
      BB_DISPATCHER.Server.send_response(response)
    else
      sendDebugMessage("Cannot send response - Server not initialized", "BB.DISPATCHER")
    end
  end

  -- Execute endpoint with error handling
  local exec_success, exec_error = pcall(function()
    endpoint.execute(request.arguments, send_response)
  end)

  if not exec_success then
    -- Endpoint threw an error
    local error_message = tostring(exec_error)

    BB_DISPATCHER.send_error(error_message, errors.EXEC_INTERNAL_ERROR)
  end
end
