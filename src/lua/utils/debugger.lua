-- src/lua/utils/debugger.lua
-- DebugPlus Integration
--
-- Attempts to load and configure DebugPlus API for enhanced debugging
-- Provides logger instance when DebugPlus mod is available

-- Load test endpoints if debug mode is enabled
table.insert(BB_ENDPOINTS, "src/lua/endpoints/tests/echo.lua")
table.insert(BB_ENDPOINTS, "src/lua/endpoints/tests/state.lua")
table.insert(BB_ENDPOINTS, "src/lua/endpoints/tests/error.lua")
table.insert(BB_ENDPOINTS, "src/lua/endpoints/tests/validation.lua")
sendDebugMessage("Loading test endpoints", "BB.BALATROBOT")

BB_DEBUG = {
  -- Logger instance (set by setup if DebugPlus is available)
  ---@type table?
  log = nil,
}
--- Initializes DebugPlus integration if available
--- Registers BalatroBot with DebugPlus and creates logger instance
---@return nil
BB_DEBUG.setup = function()
  local success, dpAPI = pcall(require, "debugplus.api")
  if not success or not dpAPI then
    sendDebugMessage("DebugPlus API not found", "BALATROBOT")
    return
  end
  if not dpAPI.isVersionCompatible(1) then
    sendDebugMessage("DebugPlus API version is not compatible", "BALATROBOT")
    return
  end
  local dp = dpAPI.registerID("BalatroBot")
  if not dp then
    sendDebugMessage("Failed to register with DebugPlus", "BALATROBOT")
    return
  end

  -- Create a logger
  BB_DEBUG.log = dp.logger
  BB_DEBUG.log.debug("DebugPlus API available")

  -- Register commands
  -- ...
end
