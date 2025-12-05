--[[
  TCP Server - Single-client, non-blocking server on port 12346.
  JSON-RPC 2.0 protocol with newline-delimited messages.
]]

local socket = require("socket")
local json = require("json")

BB_SERVER = {
  host = BB_SETTINGS.host,
  port = BB_SETTINGS.port,
  server_socket = nil,
  client_socket = nil,
  current_request_id = nil,
}

---@return boolean success
function BB_SERVER.init()
  local server, err = socket.tcp()
  if not server then
    sendErrorMessage("Failed to create socket: " .. tostring(err), "BB.SERVER")
    return false
  end
  local success, bind_err = server:bind(BB_SERVER.host, BB_SERVER.port)
  if not success then
    sendErrorMessage("Failed to bind to port " .. BB_SERVER.port .. ": " .. tostring(bind_err), "BB.SERVER")
    return false
  end
  local listen_success, listen_err = server:listen(1)
  if not listen_success then
    sendErrorMessage("Failed to listen: " .. tostring(listen_err), "BB.SERVER")
    return false
  end
  server:settimeout(0)
  BB_SERVER.server_socket = server
  sendDebugMessage("Listening on " .. BB_SERVER.host .. ":" .. BB_SERVER.port, "BB.SERVER")
  return true
end

---@return boolean accepted
function BB_SERVER.accept()
  if not BB_SERVER.server_socket then
    return false
  end
  local client, err = BB_SERVER.server_socket:accept()
  if err then
    if err ~= "timeout" then
      sendErrorMessage("Failed to accept client: " .. tostring(err), "BB.SERVER")
    end
    return false
  end
  if client then
    if BB_SERVER.client_socket then
      BB_SERVER.client_socket:close()
      BB_SERVER.client_socket = nil
    end
    client:settimeout(0)
    BB_SERVER.client_socket = client
    sendDebugMessage("Client connected", "BB.SERVER")
    return true
  end
  return false
end

--- Max payload: 256 bytes. Non-blocking, returns empty array if no data.
---@return Request[]
function BB_SERVER.receive()
  if not BB_SERVER.client_socket then
    return {}
  end
  BB_SERVER.client_socket:settimeout(0)
  local line, err = BB_SERVER.client_socket:receive("*l")
  if not line then
    if err == "closed" then
      BB_SERVER.client_socket:close()
      BB_SERVER.client_socket = nil
    end
    return {}
  end
  if #line + 1 > 256 then
    BB_SERVER.current_request_id = nil
    BB_SERVER.send_response({
      message = "Request too large: maximum 256 bytes including newline",
      name = BB_ERROR_NAMES.BAD_REQUEST,
    })
    return {}
  end
  if line == "" then
    return {}
  end
  local trimmed = line:match("^%s*(.-)%s*$")
  if not trimmed:match("^{") then
    BB_SERVER.current_request_id = nil
    BB_SERVER.send_response({
      message = "Invalid JSON in request: must be object (start with '{')",
      name = BB_ERROR_NAMES.BAD_REQUEST,
    })
    return {}
  end
  local success, parsed = pcall(json.decode, line)
  if not success or type(parsed) ~= "table" then
    BB_SERVER.current_request_id = nil
    BB_SERVER.send_response({
      message = "Invalid JSON in request",
      name = BB_ERROR_NAMES.BAD_REQUEST,
    })
    return {}
  end
  if parsed.jsonrpc ~= "2.0" then
    BB_SERVER.current_request_id = parsed.id
    BB_SERVER.send_response({
      message = "Invalid JSON-RPC version: expected '2.0'",
      name = BB_ERROR_NAMES.BAD_REQUEST,
    })
    return {}
  end
  BB_SERVER.current_request_id = parsed.id
  return { parsed }
end

---@param response EndpointResponse
---@return boolean success
function BB_SERVER.send_response(response)
  if not BB_SERVER.client_socket then
    return false
  end
  local wrapped
  if response.message then
    local error_name = response.name or BB_ERROR_NAMES.INTERNAL_ERROR
    local error_code = BB_ERROR_CODES[error_name] or BB_ERROR_CODES.INTERNAL_ERROR
    wrapped = {
      jsonrpc = "2.0",
      error = {
        code = error_code,
        message = response.message,
        data = { name = error_name },
      },
      id = BB_SERVER.current_request_id,
    }
  else
    wrapped = {
      jsonrpc = "2.0",
      result = response,
      id = BB_SERVER.current_request_id,
    }
  end
  local success, json_str = pcall(json.encode, wrapped)
  if not success then
    sendDebugMessage("Failed to encode response: " .. tostring(json_str), "BB.SERVER")
    return false
  end
  local _, err = BB_SERVER.client_socket:send(json_str .. "\n")
  if err then
    sendDebugMessage("Failed to send response: " .. err, "BB.SERVER")
    return false
  end
  return true
end

---@param dispatcher Dispatcher?
function BB_SERVER.update(dispatcher)
  if not BB_SERVER.server_socket then
    return
  end
  BB_SERVER.accept()
  if BB_SERVER.client_socket then
    local requests = BB_SERVER.receive()
    for _, request in ipairs(requests) do
      if dispatcher and dispatcher.dispatch then
        dispatcher.dispatch(request, BB_SERVER.client_socket)
      else
        BB_SERVER.send_response({
          message = "Server not fully initialized (dispatcher not ready)",
          name = BB_ERROR_NAMES.INVALID_STATE,
        })
      end
    end
  end
end

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
