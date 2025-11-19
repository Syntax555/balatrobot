-- src/lua/endpoints/save.lua
-- Save Game State Endpoint
--
-- Saves the current game run state to a file using nativefs

local nativefs = require("nativefs")
local errors = assert(SMODS.load_file("src/lua/utils/errors.lua"))()

---@class Endpoint.Save.Args
---@field path string File path for the save file

---@type Endpoint
return {
  name = "save",

  description = "Save the current run state to a file",

  schema = {
    path = {
      type = "string",
      required = true,
      description = "File path for the save file",
    },
  },

  -- All states that occur during an active run (G.STAGES.RUN)
  -- Excludes: MENU, SPLASH, SANDBOX, TUTORIAL, DEMO_CTA
  requires_state = {
    G.STATES.SELECTING_HAND, -- 1
    G.STATES.HAND_PLAYED, -- 2
    G.STATES.DRAW_TO_HAND, -- 3
    G.STATES.GAME_OVER, -- 4
    G.STATES.SHOP, -- 5
    G.STATES.PLAY_TAROT, -- 6
    G.STATES.BLIND_SELECT, -- 7
    G.STATES.ROUND_EVAL, -- 8
    G.STATES.TAROT_PACK, -- 9
    G.STATES.PLANET_PACK, -- 10
    G.STATES.SPECTRAL_PACK, -- 15
    G.STATES.STANDARD_PACK, -- 17
    G.STATES.BUFFOON_PACK, -- 18
    G.STATES.NEW_ROUND, -- 19
  },

  ---@param args Endpoint.Save.Args The arguments with 'path' field
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    local path = args.path

    -- Validate we're in a run
    if not G.STAGE or G.STAGE ~= G.STAGES.RUN then
      send_response({
        error = "Can only save during an active run",
        error_code = errors.GAME_NOT_IN_RUN,
      })
      return
    end

    -- Call save_run() and use compress_and_save
    save_run() ---@diagnostic disable-line: undefined-global

    local temp_filename = "balatrobot_temp_save.jkr"
    compress_and_save(temp_filename, G.ARGS.save_run) ---@diagnostic disable-line: undefined-global

    -- Read from temp and write to target path using nativefs
    local save_dir = love.filesystem.getSaveDirectory()
    local temp_path = save_dir .. "/" .. temp_filename
    local compressed_data = nativefs.read(temp_path)
    ---@cast compressed_data string

    if not compressed_data then
      send_response({
        error = "Failed to save game state",
        error_code = errors.EXEC_INTERNAL_ERROR,
      })
      return
    end

    local write_success = nativefs.write(path, compressed_data)
    if not write_success then
      send_response({
        error = "Failed to write save file to '" .. path .. "'",
        error_code = errors.EXEC_INTERNAL_ERROR,
      })
      return
    end

    -- Clean up
    love.filesystem.remove(temp_filename)

    send_response({
      success = true,
      path = path,
    })
  end,
}
