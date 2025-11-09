-- src/lua/core/server.lua
-- TCP Server for BalatroBot API
--
-- Simplified single-client server (assumes only one client connects)
--
-- Responsibilities:
-- - Create and bind TCP socket (non-blocking) on port 12346
-- - Accept client connections (overwrites previous client)
-- - Receive JSON-only requests (newline-delimited)
-- - Pass requests to Dispatcher
-- - Send responses back to client

local socket = require("socket")
local json = require("json")

BB_SERVER = {

  -- Configuration
  ---@type string
  host = BB_SETTINGS.host,
  ---@type integer
  port = BB_SETTINGS.port,

  -- Sockets
  ---@type TCPSocketServer?
  server_socket = nil,
  ---@type TCPSocketClient?
  client_socket = nil,
}

--- Initialize the TCP server
--- Creates and binds a non-blocking TCP socket on the configured port
--- @return boolean success
function BB_SERVER.init()
  -- Create TCP socket
  local server, err = socket.tcp()
  if not server then
    sendErrorMessage("Failed to create socket: " .. tostring(err), "BB.SERVER")
    return false
  end

  -- Bind to port
  local success, bind_err = server:bind(BB_SERVER.host, BB_SERVER.port)
  if not success then
    sendErrorMessage("Failed to bind to port " .. BB_SERVER.port .. ": " .. tostring(bind_err), "BB.SERVER")
    return false
  end

  -- Start listening (backlog of 1 for single client model)
  local listen_success, listen_err = server:listen(1)
  if not listen_success then
    sendErrorMessage("Failed to listen: " .. tostring(listen_err), "BB.SERVER")
    return false
  end

  -- Set non-blocking mode
  server:settimeout(0)

  BB_SERVER.server_socket = server

  sendDebugMessage("Listening on " .. BB_SERVER.host .. ":" .. BB_SERVER.port, "BB.SERVER")
  return true
end

--- Accept a new client connection
--- Simply accepts any incoming connection (overwrites previous client if any)
--- @return boolean accepted
function BB_SERVER.accept()
  if not BB_SERVER.server_socket then
    return false
  end

  -- Accept new client (will overwrite any existing client)
  local client, err = BB_SERVER.server_socket:accept()
  if err then
    if err ~= "timeout" then
      sendErrorMessage("Failed to accept client: " .. tostring(err), "BB.SERVER")
      return false
    end
    return false
  end
  if client and not err then
    client:settimeout(0) -- Non-blocking
    BB_SERVER.client_socket = client
    sendDebugMessage("Client connected", "BB.SERVER")
    return true
  end

  return false
end

--- Receive and parse a single JSON request from client
--- Ultra-simple protocol: JSON + '\n' (nothing else allowed)
--- Max payload: 256 bytes
--- Rejects pipelined/multiple messages
--- @return table[] requests Array with at most one parsed JSON request object
function BB_SERVER.receive()
  if not BB_SERVER.client_socket then
    return {}
  end

  -- Read one line (non-blocking)
  BB_SERVER.client_socket:settimeout(0)
  local line, err = BB_SERVER.client_socket:receive("*l")

  if not line then
    return {} -- No data available or connection closed
  end

  -- Check message size (line doesn't include the \n, so +1 for newline)
  if #line + 1 > 256 then
    BB_SERVER.send_error("Request too large: maximum 256 bytes including newline", "PROTO_PAYLOAD")
    return {}
  end

  -- Check if there's additional data waiting (pipelined requests)
  BB_SERVER.client_socket:settimeout(0)
  local peek, peek_err = BB_SERVER.client_socket:receive(1)
  if peek then
    -- There's more data! This means client sent multiple messages
    BB_SERVER.send_error(
      "Invalid request: data after newline (pipelining/multiple messages not supported)",
      "PROTO_PAYLOAD"
    )
    return {}
  end

  -- Ignore empty lines
  if line == "" then
    return {}
  end

  -- Check that JSON starts with '{' (must be object, not array/primitive)
  local trimmed = line:match("^%s*(.-)%s*$")
  if not trimmed:match("^{") then
    BB_SERVER.send_error("Invalid JSON in request: must be object (start with '{')", "PROTO_INVALID_JSON")
    return {}
  end

  -- Parse JSON
  local success, parsed = pcall(json.decode, line)
  if success and type(parsed) == "table" then
    return { parsed }
  else
    BB_SERVER.send_error("Invalid JSON in request", "PROTO_INVALID_JSON")
    return {}
  end
end

--- Send a response to the client
-- @param response table Response object to encode as JSON
-- @return boolean success
function BB_SERVER.send_response(response)
  if not BB_SERVER.client_socket then
    return false
  end

  -- Encode to JSON
  local success, json_str = pcall(json.encode, response)
  if not success then
    sendDebugMessage("Failed to encode response: " .. tostring(json_str), "BB.SERVER")
    return false
  end

  -- Send with newline delimiter
  local data = json_str .. "\n"
  local bytes, err = BB_SERVER.client_socket:send(data)

  if err then
    sendDebugMessage("Failed to send response: " .. err, "BB.SERVER")
    return false
  end

  return true
end

--- Send an error response to the client
-- @param message string Error message
-- @param error_code string Error code (e.g., "PROTO_INVALID_JSON")
function BB_SERVER.send_error(message, error_code)
  BB_SERVER.send_response({
    error = message,
    error_code = error_code,
  })
end

--- Update loop - called from game's update cycle
-- Handles accepting connections, receiving requests, and dispatching
-- @param dispatcher table? Dispatcher module for routing requests (optional for now)
function BB_SERVER.update(dispatcher)
  if not BB_SERVER.server_socket then
    return
  end

  -- Accept new connections (single client only)
  BB_SERVER.accept()

  -- Receive and process requests
  if BB_SERVER.client_socket then
    local requests = BB_SERVER.receive()

    for _, request in ipairs(requests) do
      if dispatcher and dispatcher.dispatch then
        -- Pass to Dispatcher when available
        dispatcher.dispatch(request, BB_SERVER.client_socket)
      else
        -- Placeholder: send error that dispatcher not ready
        BB_SERVER.send_error("Server not fully initialized (dispatcher not ready)", "STATE_NOT_READY")
      end
    end
  end
end

--- Cleanup and close server
function BB_SERVER.close()
  if BB_SERVER.client_socket then
    BB_SERVER.client_socket:close()
    BB_SERVER.client_socket = nil
  end

  if BB_SERVER.server_socket then
    BB_SERVER.server_socket:close()
    BB_SERVER.server_socket = nil
    sendDebugMessage("Server closed", "BB.SERVER")
  end
end

return BB_SERVER
