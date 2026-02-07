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

# List all notes (metadata only)
curl http://localhost:8001/api/notes

# Search notes (metadata only)
curl "http://localhost:8001/api/notes/search?query=todo"

# Create a note
curl -X POST http://localhost:8001/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title": "My Note", "text": "Note content"}'

# Create a list with nested items
curl -X POST http://localhost:8001/api/lists \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Shopping List",
    "items": [
      {
        "text": "Produce",
        "checked": false,
        "children": [
          {"text": "Apples", "checked": false},
          {"text": "Bananas", "checked": true}
        ]
      },
      {"text": "Dairy", "checked": false}
    ]
  }'

# Add items to an existing list
curl -X POST http://localhost:8001/api/lists/{list_id}/items \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"text": "New Item", "checked": false},
      {"text": "Another Item", "checked": true}
    ]
  }'
```

3. Interactive API documentation available at: `http://localhost:8001/docs`

**Note:** List endpoints (`GET /api/notes`, `GET /api/lists`, `GET /api/notes/search`) return metadata only for performance. Use individual endpoints (`GET /api/notes/{id}`, `GET /api/lists/{id}`) to fetch full content.

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

## REST API Architecture

The REST API provides clean separation between different resource types with a metadata vs full content pattern:

### Notes Resource (`/api/notes`) - All note types
Unified endpoint for all note types (text notes + lists):
- `POST /api/notes` - Create text note
- `GET /api/notes` - List all notes (text + lists, metadata only)
- `GET /api/notes/search?query=x` - Search all notes by title (metadata only)
- `GET /api/notes/{id}` - Get single text note (full content with text)
- `PUT /api/notes/{id}` - Replace entire text note
- `PATCH /api/notes/{id}` - Partial update (title/text/color/pinned)
- `DELETE /api/notes/{id}` - Delete text note

### Lists Resource (`/api/lists`) - List notes only
List-specific operations:
- `POST /api/lists` - Create list with nested items
- `GET /api/lists` - List all lists (metadata only, no items)
- `GET /api/lists/{id}` - Get list with all nested items (full content)
- `PUT /api/lists/{id}` - Replace entire list (title + items)
- `PATCH /api/lists/{id}` - Update list metadata only
- `DELETE /api/lists/{id}` - Delete list

### Items Sub-Resource (`/api/lists/{id}/items`)
Individual item operations:
- `POST /api/lists/{id}/items` - Add items (accepts arrays)
- `GET /api/lists/{id}/items/{item_id}` - Get single item
- `PATCH /api/lists/{id}/items/{item_id}` - Update item
- `DELETE /api/lists/{id}/items/{item_id}` - Delete item + children

### Collaborators (`/api/notes/{id}/collaborators`)
Sharing functionality for both notes and lists:
- `POST /api/notes/{id}/collaborators` - Add collaborator
- `GET /api/notes/{id}/collaborators` - List collaborators
- `DELETE /api/notes/{id}/collaborators/{email}` - Remove collaborator

## Features

### Text Notes (`/api/notes`)
- Full CRUD operations for text-only notes
- Search functionality with case-insensitive queries
- Partial updates (PATCH) for individual fields
- Type validation prevents mixing with lists
- Automatic keep-mcp label assignment for safety

### Lists with Nested Items (`/api/lists`)
- Create lists with deeply nested item structures
- Full list replacement or metadata-only updates
- Add multiple items at once with nesting support
- Individual item operations (get/update/delete)
- Automatic cascading check behavior for nested items

### Item Operations (`/api/lists/{id}/items`)
- Add items individually or in batches
- Update item properties (text, checked, parent_item_id)
- Recursive deletion of items and children
- Automatic parent status updates on child operations

### Collaborator Management
- Share notes and lists with collaborators
- Email-based collaborator management
- Permission validation (keep-mcp label required)
- List all collaborators for a resource

### Safety Features
By default, all modification operations are restricted to resources with the keep-mcp label. Set `UNSAFE_MODE=true` to allow operations on all notes.

```json
"env": {
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
