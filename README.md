# keep-mcp

MCP server for Google Keep

![keep-mcp](https://github.com/user-attachments/assets/f50c4ae6-4d35-4bb6-a494-51c67385f1b6)

## How to use

### Option 1: Using stdio transport (default)

1. Add the MCP server to your MCP servers:

```json
  "mcpServers": {
    "keep-mcp-pipx": {
      "command": "pipx",
      "args": [
        "run",
        "keep-mcp"
      ],
      "env": {
        "GOOGLE_EMAIL": "Your Google Email",
        "GOOGLE_MASTER_TOKEN": "Your Google Master Token - see README.md"
      }
    }
  }
```

### Option 2: Using HTTP transport

1. Start the server with HTTP transport:

```bash
# Using the start script
./start_http.sh

# Or directly with Python
python -m server.cli --transport http --host 0.0.0.0 --port 8000

# Or using Docker
docker-compose up
```

2. Configure your MCP client to connect via HTTP:

```json
  "mcpServers": {
    "keep-mcp-http": {
      "transport": "http",
      "url": "http://localhost:8000/mcp/"
    }
  }
```

The HTTP server provides:
- MCP endpoint: `http://localhost:8000/mcp/` (note the trailing slash)

Environment variables for HTTP transport:
- `MCP_HOST`: Host to bind to (default: 127.0.0.1)
- `MCP_PORT`: Port to bind to (default: 8000)
- `MCP_PATH`: Path for MCP endpoint (default: /mcp)

### Option 3: Using REST API

A full-featured REST API is available for standard HTTP access to Google Keep:

1. Start the services with Docker Compose:

```bash
docker-compose up -d
```

This starts two services:
- **MCP Server** (port 8000): For AI assistant integration
- **REST API** (port 8001): For standard HTTP/REST access

2. Access the REST API:

```bash
# Health check
curl http://localhost:8001/health

# List all notes
curl http://localhost:8001/api/notes

# Search notes
curl "http://localhost:8001/api/notes/search?query=todo"

# Create a note
curl -X POST http://localhost:8001/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title": "My Note", "text": "Note content"}'

# Create a list
curl -X POST http://localhost:8001/api/lists \
  -H "Content-Type: application/json" \
  -d '{"title": "Shopping List", "items": [{"text": "Milk", "checked": false}, {"text": "Bread", "checked": true}]}'
```

3. Interactive API documentation available at: `http://localhost:8001/docs`

**REST API Features:**
- Full CRUD operations (Create, Read, Update, Delete)
- Search functionality with query parameters
- Health check endpoints for monitoring
- Interactive Swagger documentation
- Proper error handling and validation
- Docker health checks included

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for complete REST API reference, examples, and troubleshooting.

Environment variables for REST API:
- `REST_API_PORT`: Port for REST API (default: 8001)
- `GOOGLE_EMAIL`: Your Google account email
- `GOOGLE_MASTER_TOKEN`: Your Google master token
- `UNSAFE_MODE`: Allow modifying all notes (default: false)

### Credentials

Add your credentials:
* `GOOGLE_EMAIL`: Your Google account email address
* `GOOGLE_MASTER_TOKEN`: Your Google account master token

Check https://gkeepapi.readthedocs.io/en/latest/#obtaining-a-master-token and https://github.com/simon-weber/gpsoauth?tab=readme-ov-file#alternative-flow for more information.

## Features

### Notes
* `find`: Search for notes and lists based on a query string
* `create_note`: Create a new note with title and text (automatically adds keep-mcp label)
* `update_note`: Update a note's title and text
* `delete_note`: Mark a note for deletion

### Lists ✨ **NEW**
* `add_list_item`: Add an item to an existing list (supports nesting via parent_item_id)
* `update_list_item`: Update a specific item in a list (text, checked status, and nesting) with automatic cascading check behavior
* `delete_list_item`: Delete a specific item and all its children recursively, with cascading parent status updates

**Note:** Lists are created and updated using the same `create_note` and `update_note` tools/endpoints, which automatically detect list vs note content. All list item operations include Google Keep-style cascading check behavior:
- Checking a parent checks all children recursively
- Parents are only checked when all children are checked
- Deleting a parent item deletes all its children recursively
- Deleting a checked child updates parent status appropriately

By default, all destructive and modification operations are restricted to notes that have were created by the MCP server (i.e. have the keep-mcp label). Set `UNSAFE_MODE` to `true` to bypass this restriction.

```
"env": {
  ...
  "UNSAFE_MODE": "true"
}
```

## Publishing

To publish a new version to PyPI:

1. Update the version in `pyproject.toml`
2. Build the package:
   ```bash
   pipx run build
   ```
3. Upload to PyPI:
   ```bash
   pipx run twine upload --repository pypi dist/*
   ```

## Troubleshooting

* If you get "DeviceManagementRequiredOrSyncDisabled" check https://admin.google.com/ac/devices/settings/general and turn "Turn off mobile management (Unmanaged)"
