-- Load required files
assert(SMODS.load_file("src/lua/settings.lua"))() -- define BB_SETTINGS

-- Configure Balatro with appropriate settings from environment variables
BB_SETTINGS.setup()

-- Endpoints for the BalatroBot API
BB_ENDPOINTS = {
  "src/lua/endpoints/health.lua",
  "src/lua/endpoints/save.lua",
  "src/lua/endpoints/load.lua",
  -- If debug mode is enabled, debugger.lua will load test endpoints
}

-- Enable debug mode
if BB_SETTINGS.debug then
  assert(SMODS.load_file("src/lua/utils/debugger.lua"))() -- define BB_DEBUG
  BB_DEBUG.setup()
end

-- Load core modules
assert(SMODS.load_file("src/lua/core/server.lua"))() -- define BB_SERVER
assert(SMODS.load_file("src/lua/core/dispatcher.lua"))() -- define BB_DISPATCHER

-- Initialize Server
local server_success = BB_SERVER.init()
if not server_success then
  return
end

local dispatcher_ok = BB_DISPATCHER.init(BB_SERVER, BB_ENDPOINTS)
if not dispatcher_ok then
  return
end

-- Hook into love.update to run server update loop
local love_update = love.update
love.update = function(dt) ---@diagnostic disable-line: duplicate-set-field
  love_update(dt)
  BB_SERVER.update(BB_DISPATCHER)
end

sendInfoMessage("BalatroBot loaded - version " .. SMODS.current_mod.version, "BB.BALATROBOT")
