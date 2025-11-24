-- src/lua/endpoints/load.lua
-- Load Game State Endpoint
--
-- Loads a saved game run state from a file using nativefs

local nativefs = require("nativefs")

---@class Endpoint.Load.Args
---@field path string File path to the save file

---@type Endpoint
return {
  name = "load",

  description = "Load a saved run state from a file",

  schema = {
    path = {
      type = "string",
      required = true,
      description = "File path to the save file",
    },
  },

  requires_state = nil,

  ---@param args Endpoint.Load.Args The arguments with 'path' field
  ---@param send_response fun(response: table) Callback to send response
  execute = function(args, send_response)
    local path = args.path

    -- Check if file exists
    local file_info = nativefs.getInfo(path)
    if not file_info or file_info.type ~= "file" then
      send_response({
        error = "File not found: '" .. path .. "'",
        error_code = BB_ERRORS.EXEC_FILE_NOT_FOUND,
      })
      return
    end

    -- Read file using nativefs
    local compressed_data = nativefs.read(path)
    ---@cast compressed_data string
    if not compressed_data then
      send_response({
        error = "Failed to read save file",
        error_code = BB_ERRORS.EXEC_INTERNAL_ERROR,
      })
      return
    end

    -- Write to temp location for get_compressed to read
    local temp_filename = "balatrobot_temp_load.jkr"
    local save_dir = love.filesystem.getSaveDirectory()
    local temp_path = save_dir .. "/" .. temp_filename

    local write_success = nativefs.write(temp_path, compressed_data)
    if not write_success then
      send_response({
        error = "Failed to prepare save file for loading",
        error_code = BB_ERRORS.EXEC_INTERNAL_ERROR,
      })
      return
    end

    -- Load using game's built-in functions
    G:delete_run()
    G.SAVED_GAME = get_compressed(temp_filename) ---@diagnostic disable-line: undefined-global

    if G.SAVED_GAME == nil then
      send_response({
        error = "Invalid save file format",
        error_code = BB_ERRORS.EXEC_INVALID_SAVE_FORMAT,
      })
      love.filesystem.remove(temp_filename)
      return
    end

    G.SAVED_GAME = STR_UNPACK(G.SAVED_GAME)
    G:start_run({ savetext = G.SAVED_GAME })

    -- Clean up
    love.filesystem.remove(temp_filename)

    G.E_MANAGER:add_event(Event({
      no_delete = true,
      trigger = "condition",
      blocking = false,
      func = function()
        local done = false
        if G.STATE == G.STATES.BLIND_SELECT then
          done = G.GAME.blind_on_deck ~= nil
            and G.blind_select_opts ~= nil
            and G.blind_select_opts["small"]:get_UIE_by_ID("tag_Small") ~= nil
        end

        if G.STATE == G.STATES.SELECTING_HAND then
          done = G.hand ~= nil
        end

        if G.STATE == G.STATES.ROUND_EVAL and G.round_eval then
          for _, b in ipairs(G.I.UIBOX) do
            if b:get_UIE_by_ID("cash_out_button") then
              done = true
            end
          end
        end

        if G.STATE == G.STATES.SHOP and G.STATE_COMPLETE then
          local done_vouchers = G.shop_vouchers and G.shop_vouchers.cards and #G.shop_vouchers.cards > 0
          local done_packs = G.shop_booster and G.shop_booster.cards and #G.shop_booster.cards > 0
          local done_jokers = G.shop_jokers and G.shop_jokers.cards and #G.shop_jokers.cards > 0
          done = done_vouchers or done_packs or done_jokers
        end

        --- TODO: add other states here ...

        if done then
          send_response({
            success = true,
            path = path,
          })
        end
        return done
      end,
    }))
  end,
}
