# Google Keep MCP & REST API Documentation

## Overview

This project provides both MCP and REST API interfaces to Google Keep:

1. **Google Keep MCP Server** - Model Context Protocol server for AI assistants
2. **Google Keep REST API** - Full REST API for standard HTTP access

## Services

### Google Keep MCP Server
- **Port**: 8000
- **MCP Endpoint**: `http://localhost:8000/mcp/`
- **Protocol**: MCP over HTTP (Server-Sent Events)
- **Use Case**: Integration with AI assistants like Claude Code

### Google Keep REST API
- **Port**: 8001
- **Base URL**: `http://localhost:8001`
- **Health Check**: `http://localhost:8001/health`
- **Documentation**: `http://localhost:8001/docs` (Swagger UI)
- **Use Case**: Standard REST API access for any HTTP client

## API Architecture

The REST API provides clean separation between different resource types with proper HTTP semantics:

### Notes Resource (`/api/notes`) - All note types (text + lists)
- `POST /api/notes` - Create text note
- `GET /api/notes` - List all notes (text + lists, metadata only)
- `GET /api/notes/search?query=x` - Search all notes by title (metadata only)
- `GET /api/notes/{id}` - Get single text note (full content)
- `PUT /api/notes/{id}` - Replace entire text note
- `PATCH /api/notes/{id}` - Partial update (title/text/color/pinned)
- `DELETE /api/notes/{id}` - Delete text note

### Lists Resource (`/api/lists`) - List notes with nested items
- `POST /api/lists` - Create list with nested items
- `GET /api/lists` - List all lists
- `GET /api/lists/{id}` - Get list with all nested items
- `PUT /api/lists/{id}` - Replace entire list (title + items)
- `PATCH /api/lists/{id}` - Update list metadata only
- `DELETE /api/lists/{id}` - Delete list

### Items Sub-Resource (`/api/lists/{id}/items`) - Individual list items
- `POST /api/lists/{id}/items` - Add items (accepts arrays)
- `GET /api/lists/{id}/items/{item_id}` - Get single item
- `PATCH /api/lists/{id}/items/{item_id}` - Update item
- `DELETE /api/lists/{id}/items/{item_id}` - Delete item + children

### Collaborators (`/api/notes/{id}/collaborators`) - Sharing
- `POST /api/notes/{id}/collaborators` - Add collaborator
- `GET /api/notes/{id}/collaborators` - List collaborators
- `DELETE /api/notes/{id}/collaborators/{email}` - Remove collaborator

## Metadata vs Full Content Pattern

The API uses a two-tier approach to optimize performance and bandwidth:

### List Endpoints (Metadata Only)
- `GET /api/notes` - Returns all notes (text + lists) with basic metadata
- `GET /api/lists` - Returns all lists with basic metadata
- `GET /api/notes/search?query=x` - Returns matching notes with basic metadata

**Metadata includes:**
- `id`, `title`, `pinned`, `color`, `labels`, `collaborators`, `type`
- **Excludes:** `text` content for notes, `items` arrays for lists

### Detail Endpoints (Full Content)
- `GET /api/notes/{id}` - Returns complete text note with `text` content
- `GET /api/lists/{id}` - Returns complete list with full nested `items` array

### Benefits
- **Faster browsing**: List operations are lightweight and fast
- **Reduced bandwidth**: Only fetch full content when needed
- **Better UX**: Clients can show quick lists, then load details on demand
- **Unified search**: Single endpoint searches across all note types

## REST API Endpoints

### Health Check
```bash
GET /health
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-02-07T14:11:15.474034",
  "service": "google-keep-rest-api",
  "google_keep_connected": true,
  "version": "1.0.0"
}
```

## Notes Endpoints (Text Notes Only)

### Create Text Note
```bash
POST /api/notes
Content-Type: application/json

{
  "title": "Meeting Notes",
  "text": "Discussed project timeline and budget"
}
```

**Response:**
```json
{
  "id": "1753881285774.973567934",
  "title": "Meeting Notes",
  "text": "Discussed project timeline and budget",
  "pinned": false,
  "color": "DEFAULT",
  "labels": [{"id": "label_123", "name": "keep-mcp"}],
  "collaborators": [],
  "type": "note"
}
```

**Example:**
```bash
curl -X POST http://localhost:8001/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title": "Meeting Notes", "text": "Discussed project timeline"}'
```

### List All Notes (Text + Lists)
```bash
GET /api/notes
```

Returns metadata only for all note types. Use individual endpoints for full content.

**Response:**
```json
{
  "notes": [
    {
      "id": "1753881285774.973567934",
      "title": "Meeting Notes",
      "pinned": false,
      "color": "DEFAULT",
      "labels": [{"id": "label_123", "name": "keep-mcp"}],
      "collaborators": [],
      "type": "note"
    },
    {
      "id": "1753881285774.123456789",
      "title": "Shopping List",
      "pinned": false,
      "color": "DEFAULT",
      "labels": [{"id": "label_123", "name": "keep-mcp"}],
      "collaborators": [],
      "type": "list"
    }
  ],
  "count": 2
}
```

### Search All Notes
```bash
GET /api/notes/search?query=search_term
```

**Note:** Search is case-insensitive and matches against note titles only. Returns both text notes and lists (metadata only).

**Example:**
```bash
curl "http://localhost:8001/api/notes/search?query=meeting"
```

### Get Specific Text Note
```bash
GET /api/notes/{note_id}
```

**Response:** Same as create response

**Error Response (if note is a list):**
```json
{
  "detail": "Note with ID 1753881285774.123456789 is a list. Use GET /api/lists/1753881285774.123456789 instead"
}
```

### Replace Entire Text Note (PUT)
```bash
PUT /api/notes/{note_id}
Content-Type: application/json

{
  "title": "Updated Meeting Notes",
  "text": "Discussed project timeline, budget, and resources"
}
```

**Note:** PUT requires ALL fields and replaces the entire note.

### Partially Update Text Note (PATCH)
```bash
PATCH /api/notes/{note_id}
Content-Type: application/json

{
  "text": "Discussed project timeline, budget, resources, and timeline"
}
```

**Note:** PATCH only updates provided fields.

### Delete Text Note
```bash
DELETE /api/notes/{note_id}
```

**Response:**
```json
{
  "message": "Note 1753881285774.973567934 marked for deletion",
  "status": "success"
}
```

## Lists Endpoints (List Notes with Nested Items)

### Create List with Nested Items
```bash
POST /api/lists
Content-Type: application/json

{
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
    {
      "text": "Dairy",
      "checked": false,
      "children": [
        {"text": "Milk", "checked": false},
        {"text": "Cheese", "checked": false}
      ]
    }
  ]
}
```

**Response:**
```json
{
  "id": "1753881285774.123456789",
  "title": "Shopping List",
  "pinned": false,
  "color": "DEFAULT",
  "labels": [{"id": "label_123", "name": "keep-mcp"}],
  "collaborators": [],
  "items": [
    {
      "id": "item_1",
      "text": "Produce",
      "checked": false,
      "children": [
        {"id": "item_2", "text": "Apples", "checked": false, "children": []},
        {"id": "item_3", "text": "Bananas", "checked": true, "children": []}
      ]
    },
    {
      "id": "item_4",
      "text": "Dairy",
      "checked": false,
      "children": [
        {"id": "item_5", "text": "Milk", "checked": false, "children": []},
        {"id": "item_6", "text": "Cheese", "checked": false, "children": []}
      ]
    }
  ],
  "type": "list"
}
```

### List All Lists
```bash
GET /api/lists
```

Returns metadata only for all lists. Use individual endpoints for full content with items.

**Response:**
```json
{
  "lists": [
    {
      "id": "1753881285774.123456789",
      "title": "Shopping List",
      "pinned": false,
      "color": "DEFAULT",
      "labels": [{"id": "label_123", "name": "keep-mcp"}],
      "collaborators": [],
      "type": "list"
    }
  ],
  "count": 1
}
```

### Get Specific List with Items
```bash
GET /api/lists/{list_id}
```

**Response:** Complete list with nested items (same as create response)

### Replace Entire List (PUT)
```bash
PUT /api/lists/{list_id}
Content-Type: application/json

{
  "title": "Updated Shopping List",
  "items": [
    {"text": "New Item 1", "checked": false},
    {"text": "New Item 2", "checked": true}
  ]
}
```

**Note:** PUT replaces ALL items. Old items are deleted.

### Update List Metadata Only (PATCH)
```bash
PATCH /api/lists/{list_id}
Content-Type: application/json

{
  "title": "Weekly Shopping List",
  "pinned": true,
  "color": "BLUE"
}
```

**Note:** PATCH only updates list metadata (title/color/pinned), not items.

### Delete List
```bash
DELETE /api/lists/{list_id}
```

**Response:**
```json
{
  "message": "List 1753881285774.123456789 marked for deletion",
  "status": "success"
}
```

## List Items Endpoints

### Add Items to List
```bash
POST /api/lists/{list_id}/items
Content-Type: application/json

{
  "items": [
    {
      "text": "New Category",
      "checked": false,
      "children": [
        {"text": "Sub Item 1", "checked": false}
      ]
    },
    {"text": "Simple Item", "checked": true}
  ]
}
```

**Response:**
```json
{
  "message": "Added 3 items to list 1753881285774.123456789",
  "items_added": 3,
  "status": "success"
}
```

### Get Single Item
```bash
GET /api/lists/{list_id}/items/{item_id}
```

**Response:**
```json
{
  "id": "item_1",
  "text": "Produce",
  "checked": false,
  "parent_item_id": null
}
```

### Update Single Item
```bash
PATCH /api/lists/{list_id}/items/{item_id}
Content-Type: application/json

{
  "text": "Organic Produce",
  "checked": true,
  "parent_item_id": "parent_item_id"  // Or null to unnest
}
```

**Response:** Updated item details

### Delete Single Item
```bash
DELETE /api/lists/{list_id}/items/{item_id}
```

**Response:**
```json
{
  "message": "Item item_1 and its children deleted from list 1753881285774.123456789",
  "status": "success"
}
```

## Collaborator Management

Works for both notes and lists via `/api/notes/{id}/collaborators`

### Add Collaborator
```bash
POST /api/notes/{note_id}/collaborators
Content-Type: application/json

{
  "email": "collaborator@example.com"
}
```

**Example:**
```bash
curl -X POST http://localhost:8001/api/notes/1753881285774.973567934/collaborators \
  -H "Content-Type: application/json" \
  -d '{"email": "friend@gmail.com"}'
```

### List Collaborators
```bash
GET /api/notes/{note_id}/collaborators
```

**Response:**
```json
{
  "note_id": "1753881285774.973567934",
  "collaborators": ["friend@gmail.com", "colleague@company.com"],
  "count": 2
}
```

### Remove Collaborator
```bash
DELETE /api/notes/{note_id}/collaborators/{email}
```

**Response:**
```json
{
  "message": "Removed friend@gmail.com from note 1753881285774.973567934",
  "status": "success"
}
```

## HTTP Method Semantics

### POST - Create/Add
- **Notes**: `POST /api/notes` creates new text note
- **Lists**: `POST /api/lists` creates new list with items
- **Items**: `POST /api/lists/{id}/items` adds items to existing list
- Returns 201 Created with resource location

### GET - Retrieve
- **Collections**: Returns array of resources with count
- **Individuals**: Returns complete resource details
- Always safe (no side effects)

### PUT - Full Replacement
- **Notes**: `PUT /api/notes/{id}` replaces entire note (all fields required)
- **Lists**: `PUT /api/lists/{id}` replaces entire list (title + all items)
- Idempotent - same result regardless of repetitions

### PATCH - Partial Update
- **Notes**: Updates only specified fields (title/text/color/pinned)
- **Lists**: Updates only metadata (title/color/pinned), not items
- **Items**: Updates only specified item fields
- Not idempotent - different results possible

### DELETE - Remove
- Removes entire resource
- Idempotent - safe to call multiple times
- Returns success message

## Security & Safety

### Keep-MCP Label Protection
By default, the API can only modify resources that have the `keep-mcp` label. This prevents accidental modification of important notes.

- Resources created via the API automatically get the `keep-mcp` label
- To allow modification of all notes, set `UNSAFE_MODE=true` in environment

### Type Validation
- **Notes endpoints** (`/api/notes/*`) reject operations on lists
- **Lists endpoints** (`/api/lists/*`) reject operations on text notes
- Clear error messages guide users to correct endpoints

### Collaborator Management
Sharing works for both notes and lists:
- Only resources with `keep-mcp` label can be shared (unless `UNSAFE_MODE=true`)
- Owner retains full control over collaborator management
- Collaborators can view shared resources but cannot modify them via API

## Docker Management

### Start Services
```bash
cd "/opt/stacks/Google Keep MCP"
docker-compose up -d
```

### Stop Services
```bash
docker-compose down
```

### View Logs
```bash
# MCP Server logs
docker logs keep-mcp-server

# REST API logs
docker logs keep-rest-api

# Follow logs in real-time
docker logs -f keep-rest-api
```

### Restart Services
```bash
# Restart both services
docker-compose restart

# Restart specific service
docker restart keep-rest-api
```

### Check Service Health
```bash
# Check container status
docker ps | grep keep

# Check health endpoints
curl http://localhost:8001/health
```

## Configuration

### Environment Variables (.env)
```bash
# MCP Server Configuration
MCP_HOST=127.0.0.1
MCP_PORT=8000

# REST API Configuration
REST_API_PORT=8001

# Google Keep Credentials
GOOGLE_EMAIL=your-email@gmail.com
GOOGLE_MASTER_TOKEN=your_master_token_here

# Safety Mode
UNSAFE_MODE=false  # Set to 'true' to allow modification of all notes
```

### Docker Compose Services

Both services are configured in `docker-compose.yml`:
- **keep-mcp**: MCP protocol server on port 8000
- **keep-rest-api**: REST API on port 8001

Both services include:
- Health checks every 30 seconds
- Automatic restart on failure
- Shared data volume for persistence
- Access to Google Keep via same credentials

## Testing & Examples

### Quick Start Examples
```bash
# Health check
curl http://localhost:8001/health

# Create a text note
curl -X POST http://localhost:8001/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title": "Meeting Notes", "text": "Discussed project timeline"}'

# Create a list with nested items
curl -X POST http://localhost:8001/api/lists \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Shopping List",
    "items": [
      {"text": "Produce", "checked": false, "children": [
        {"text": "Apples", "checked": false}
      ]},
      {"text": "Dairy", "checked": false}
    ]
  }'

# List all notes and lists separately
curl http://localhost:8001/api/notes
curl http://localhost:8001/api/lists

# Add items to existing list
curl -X POST http://localhost:8001/api/lists/{list_id}/items \
  -H "Content-Type: application/json" \
  -d '{"items": [{"text": "New Item", "checked": false}]}'

# Update list metadata only
curl -X PATCH http://localhost:8001/api/lists/{list_id} \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated Title"}'
```

### Interactive Documentation
Visit `http://localhost:8001/docs` for complete Swagger UI documentation with:
- All endpoint specifications
- Request/response schemas
- Interactive API testing
- Authentication details

## Troubleshooting

### Port Already in Use
```bash
# Check what's using the port
lsof -i :8001

# Change the port in .env if needed
REST_API_PORT=8002
```

### Container Won't Start
```bash
# Check logs for errors
docker logs keep-rest-api

# Rebuild the container
docker-compose down
docker-compose build --no-cache keep-rest-api
docker-compose up -d
```

### Google Keep Authentication Issues
```bash
# Verify credentials in .env
cat .env | grep GOOGLE

# Test authentication
docker exec keep-rest-api python -c "from server.keep_api import get_client; get_client(); print('Auth successful')"
```

### Health Check Failures
```bash
# Check if service is running
docker ps | grep keep

# Check health endpoint directly
curl -v http://localhost:8001/health

# View detailed logs
docker logs keep-rest-api --tail 50
```

## MCP Server Integration

The MCP server on port 8000 provides AI assistant integration using the Model Context Protocol.

### Available MCP Tools
- `find_note(query)` - Search notes (case-insensitive)
- `create_note(title, text)` - Create text note
- `update_note(note_id, title, text)` - Update text note
- `delete_note(note_id)` - Delete note
- `share_note(note_id, email)` - Share note with collaborator
- `unshare_note(note_id, email)` - Remove collaborator
- `list_collaborators(note_id)` - List note collaborators
- `note_add_list_item(note_id, text, checked, parent_item_id)` - Add list item
- `note_update_list_item(note_id, item_id, text, checked, parent_item_id)` - Update list item
- `note_delete_list_item(note_id, item_id)` - Delete list item
- `note_add_list_items_nested(note_id, items_json, mode)` - Add nested items
- `note_get_list_items_nested(note_id)` - Get nested items

### MCP Client Configuration
```json
{
  "mcpServers": {
    "google-keep": {
      "transport": "http",
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```

## Architecture

```
┌─────────────────────────────────────────┐
│         Docker Compose Stack            │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────────────────────────┐   │
│  │   keep-mcp-server (Port 8000)   │   │
│  │   Protocol: MCP over HTTP       │   │
│  └──────────┬──────────────────────┘   │
│             │                           │
│  ┌──────────▼──────────────────────┐   │
│  │   Google Keep API Layer         │   │
│  │   (gkeepapi library)            │   │
│  └──────────┬──────────────────────┘   │
│             │                           │
│  ┌──────────▼──────────────────────┐   │
│  │   keep-rest-api (Port 8001)     │   │
│  │   Protocol: REST/HTTP           │   │
│  │   Endpoints:                    │   │
│  │   • /api/notes (text notes)     │   │
│  │   • /api/lists (list notes)     │   │
│  │   • /api/lists/{id}/items       │   │
│  └─────────────────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

## Project Structure

```
keep-mcp-http/
├── README.md                    # Project overview and usage
├── API_DOCUMENTATION.md         # Complete API reference (this file)
├── MIGRATION_GUIDE.md           # Migration from old API
├── docker-compose.yml           # Service orchestration
├── Dockerfile                   # Container build configuration
├── .env                         # Environment variables
├── pyproject.toml               # Python project configuration
├── src/server/
│   ├── cli.py                   # MCP server with tools
│   ├── keep_api.py              # Google Keep client & utilities
│   ├── rest_api.py              # REST API FastAPI application
│   └── standalone_http.py       # MCP HTTP server entry point
├── start_rest_api.sh            # REST API startup script
├── start_http.sh                # MCP server startup script
└── .cursor/skills/              # Project-specific AI skills
    ├── rest-api-design/         # REST API design patterns
    ├── keep-api-integration/    # Google Keep integration patterns
    └── fastapi-development/     # FastAPI development patterns
```

## Getting Started

1. **Start services**: `docker-compose up -d`
2. **Check health**: `curl http://localhost:8001/health`
3. **View API docs**: Visit `http://localhost:8001/docs`
4. **Test endpoints**: Use the examples above
5. **Migrate old code**: See `MIGRATION_GUIDE.md`

## Support & Troubleshooting

### Common Issues

**Port Already in Use**
```bash
# Check what's using ports
lsof -i :8000  # MCP server
lsof -i :8001  # REST API

# Change ports in docker-compose.yml or .env
```

**Google Keep Authentication**
```bash
# Check credentials
cat .env | grep GOOGLE

# Test authentication in container
docker exec keep-rest-api python -c "from server.keep_api import get_client; get_client(); print('OK')"
```

**Container Won't Start**
```bash
# Check logs
docker logs keep-rest-api

# Rebuild container
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Getting Help

1. **Check health**: `curl http://localhost:8001/health`
2. **View logs**: `docker logs keep-rest-api`
3. **Interactive docs**: `http://localhost:8001/docs`
4. **Migration guide**: See `MIGRATION_GUIDE.md`
5. **Original project**: https://github.com/feuerdev/keep-mcp
