#!/usr/bin/env python3
"""
REST API wrapper for Google Keep MCP server.
Provides standard REST endpoints with proper health checks.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os
import json
import toml
from datetime import datetime
from pathlib import Path
from .keep_api import get_client, serialize_note, can_modify_note, share_note, unshare_note, list_collaborators

def get_project_version():
    """Get the project version from pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    try:
        with open(pyproject_path, "r") as f:
            pyproject_data = toml.load(f)
        return pyproject_data["project"]["version"]
    except Exception:
        return "unknown"

app = FastAPI(
    title="Google Keep REST API",
    description="REST API for Google Keep MCP Server",
    version=get_project_version()
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response validation

# Health and common models
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    service: str
    google_keep_connected: bool
    version: str = get_project_version()

# Metadata-only response models (no content)
class NoteMetadataResponse(BaseModel):
    id: str
    title: Optional[str]
    pinned: bool
    color: Optional[str]
    labels: List[Dict[str, str]]
    collaborators: List[str] = []
    type: str

class ListMetadataResponse(BaseModel):
    id: str
    title: Optional[str]
    pinned: bool
    color: Optional[str]
    labels: List[Dict[str, str]]
    collaborators: List[str] = []
    type: str = "list"

# Notes models - for text notes only (no items)
class NoteSearchRequest(BaseModel):
    query: Optional[str] = Field(default="", description="Search query string")

class NoteCreateRequest(BaseModel):
    title: Optional[str] = Field(None, description="Note title")
    text: Optional[str] = Field(None, description="Note text content")

class NotePutRequest(BaseModel):
    title: Optional[str] = Field(None, description="Note title")
    text: Optional[str] = Field(None, description="Note text content")

class NotePatchRequest(BaseModel):
    title: Optional[str] = Field(None, description="New title")
    text: Optional[str] = Field(None, description="New text content")
    color: Optional[str] = Field(None, description="Note color")
    pinned: Optional[bool] = Field(None, description="Pin status")

class NoteResponse(BaseModel):
    id: str
    title: Optional[str]
    text: Optional[str]
    pinned: bool
    color: Optional[str]
    labels: List[Dict[str, str]]
    collaborators: List[str] = []
    type: str = "note"

# Lists models - for list notes with items
class ListCreateRequest(BaseModel):
    title: Optional[str] = Field(None, description="List title")
    items: List['NestedListItemInput'] = Field(default_factory=list, description="List items with optional nesting")

class ListPutRequest(BaseModel):
    title: Optional[str] = Field(None, description="List title")
    items: List['NestedListItemInput'] = Field(default_factory=list, description="List items with optional nesting")

class ListPatchRequest(BaseModel):
    title: Optional[str] = Field(None, description="New title")
    color: Optional[str] = Field(None, description="List color")
    pinned: Optional[bool] = Field(None, description="Pin status")

class ListResponse(BaseModel):
    id: str
    title: Optional[str]
    pinned: bool
    color: Optional[str]
    labels: List[Dict[str, str]]
    collaborators: List[str] = []
    items: List['NestedListItemOutput'] = []
    type: str = "list"

# List items models - for individual item operations
class ItemAddRequest(BaseModel):
    items: List['NestedListItemInput'] = Field(description="Items to add with optional nested children")

class ItemPatchRequest(BaseModel):
    text: Optional[str] = Field(None, description="Updated text")
    checked: Optional[bool] = Field(None, description="Checked status")
    parent_item_id: Optional[str] = Field(None, description="New parent item ID for nesting (null to unindent)")

class ItemResponse(BaseModel):
    id: str
    text: str
    checked: bool
    parent_item_id: Optional[str] = None

class NestedListItemInput(BaseModel):
    text: str
    checked: bool = False
    children: Optional[List['NestedListItemInput']] = Field(default_factory=list, description="Nested child items")

class NestedListItemOutput(BaseModel):
    id: str
    text: str
    checked: bool
    parent_item_id: Optional[str] = None
    children: List['NestedListItemOutput'] = Field(default_factory=list, description="Nested child items")

class CollaboratorRequest(BaseModel):
    email: str = Field(..., description="Email address of the collaborator")

class CollaboratorResponse(BaseModel):
    email: str
    note_id: str

class CollaboratorsListResponse(BaseModel):
    note_id: str
    collaborators: List[str]
    count: int

def _update_item_checked_with_cascade(all_items, target_item, checked):
    """
    Update an item's checked status with cascading behavior for nested items.

    Args:
        all_items: List of all items in the list
        target_item: The item being updated
        checked: New checked status
    """
    # Set the target item's checked status
    target_item.checked = checked

    if checked:
        # If checking an item, check all its children recursively
        _check_all_children(all_items, target_item)
    else:
        # If unchecking an item, uncheck all its children recursively
        _uncheck_all_children(all_items, target_item)

    # Update parent checked status based on children
    _update_parent_checked_status(all_items, target_item)

def _check_all_children(all_items, parent_item):
    """Recursively check all children of a parent item."""
    for item in all_items:
        if item.parent_item and item.parent_item.id == parent_item.id:
            item.checked = True
            _check_all_children(all_items, item)  # Recurse for grandchildren

def _uncheck_all_children(all_items, parent_item):
    """Recursively uncheck all children of a parent item."""
    for item in all_items:
        if item.parent_item and item.parent_item.id == parent_item.id:
            item.checked = False
            _uncheck_all_children(all_items, item)  # Recurse for grandchildren

def _update_parent_checked_status(all_items, child_item):
    """Update parent item's checked status based on whether all siblings are checked."""
    if not child_item.parent_item:
        return  # No parent to update

    parent = child_item.parent_item

    # Check if all direct children of this parent are checked
    all_children_checked = True
    has_children = False

    for item in all_items:
        if item.parent_item and item.parent_item.id == parent.id:
            has_children = True
            if not item.checked:
                all_children_checked = False
                break

    # If parent has children and all are checked, check the parent
    # If parent has children and not all are checked, uncheck the parent
    if has_children:
        parent.checked = all_children_checked

        # Recursively update grandparent if needed
        _update_parent_checked_status(all_items, parent)

def _delete_item_with_children(all_items, target_item):
    """
    Recursively delete an item and all its children.

    Args:
        all_items: List of all items in the list
        target_item: The item to delete along with its children
    """
    # First, recursively delete all children
    children_to_delete = []
    for item in all_items:
        if item.parent_item and item.parent_item.id == target_item.id:
            children_to_delete.append(item)

    # Recursively delete children first
    for child in children_to_delete:
        _delete_item_with_children(all_items, child)

    # Then delete the target item itself
    target_item.delete()

def _add_items_recursively(list_obj, items, parent_item=None):
    """
    Add items to list, recursively handling children.

    Args:
        list_obj: The Google Keep list object
        items: List of NestedListItemInput objects
        parent_item: Parent item to indent children under (optional)

    Returns:
        List of created gkeepapi list items
    """
    created_items = []
    for item_data in items:
        # Add the item
        new_item = list_obj.add(item_data.text, item_data.checked)

        # Indent under parent if specified
        if parent_item:
            parent_item.indent(new_item)

        created_items.append(new_item)

        # Recursively add children
        if item_data.children:
            child_items = _add_items_recursively(
                list_obj, item_data.children, new_item
            )
            created_items.extend(child_items)

    return created_items

def _build_nested_items(all_items):
    """
    Convert flat items list to nested structure.

    Args:
        all_items: List of all gkeepapi list items in the list

    Returns:
        List of nested item dictionaries
    """
    children_map = {}  # parent_id -> [children]
    root_items = []

    for item in all_items:
        if item.parent_item:
            parent_id = item.parent_item.id
            children_map.setdefault(parent_id, []).append(item)
        else:
            root_items.append(item)

    def build_tree(item):
        children = children_map.get(item.id, [])
        return {
            "id": item.id,
            "text": item.text,
            "checked": item.checked,
            "children": [build_tree(child) for child in children]
        }

    return [build_tree(item) for item in root_items]

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "Google Keep REST API",
        "version": get_project_version(),
        "endpoints": {
            "health": "/api/health",
            "notes": {
                "search": "GET /api/notes/search?query=...",
                "create": "POST /api/notes",
                "list": "GET /api/notes",
                "get": "GET /api/notes/{id}",
                "put": "PUT /api/notes/{id}",
                "patch": "PATCH /api/notes/{id}",
                "delete": "DELETE /api/notes/{id}"
            },
            "lists": {
                "create": "POST /api/lists",
                "list": "GET /api/lists",
                "get": "GET /api/lists/{id}",
                "put": "PUT /api/lists/{id}",
                "patch": "PATCH /api/lists/{id}",
                "delete": "DELETE /api/lists/{id}"
            },
            "items": {
                "add": "POST /api/lists/{id}/items",
                "get": "GET /api/lists/{id}/items/{item_id}",
                "patch": "PATCH /api/lists/{id}/items/{item_id}",
                "delete": "DELETE /api/lists/{id}/items/{item_id}"
            },
            "collaborators": {
                "add": "POST /api/notes/{id}/collaborators",
                "get": "GET /api/notes/{id}/collaborators",
                "remove": "DELETE /api/notes/{id}/collaborators/{email}"
            }
        },
        "docs": "/docs"
    }

# Health check endpoint
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint that verifies Google Keep connection.
    """
    try:
        # Try to initialize the Keep client
        keep = get_client()
        connected = True
        status = "healthy"
    except Exception as e:
        connected = False
        status = "unhealthy"

    return {
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "google-keep-rest-api",
        "google_keep_connected": connected
    }

# Search/find notes (ALL note types, metadata only)
@app.get("/api/notes/search")
async def search_notes(query: str = ""):
    """
    Search for all notes (text + lists) matching query (case-insensitive).
    Returns metadata only - use GET /api/notes/{id} or /api/lists/{id} for full content.

    Args:
        query: Search query string (searches titles only)

    Returns:
        List of matching notes (metadata only, all types)
    """
    try:
        keep = get_client()

        if not query:
            # Return all notes (both types, metadata only)
            all_notes = keep.find(archived=False, trashed=False)
        else:
            # Case-insensitive search on titles for all note types
            all_notes = keep.find(archived=False, trashed=False)
            query_lower = query.lower()
            all_notes = [
                note for note in all_notes
                if query_lower in (note.title or "").lower()
            ]

        from .keep_api import serialize_note_metadata
        notes_data = [serialize_note_metadata(note) for note in all_notes]
        return {"notes": notes_data, "count": len(notes_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# List all notes (ALL types, metadata only)
@app.get("/api/notes")
async def list_notes():
    """
    List all notes (text + lists, non-archived, non-trashed).
    Returns metadata only - use GET /api/notes/{id} or /api/lists/{id} for full content.

    Returns:
        List of all notes (metadata only, all types)
    """
    return await search_notes(query="")

# Get a specific note (text notes only)
@app.get("/api/notes/{note_id}", response_model=NoteResponse)
async def get_note(note_id: str):
    """
    Get a specific text note by ID.

    Args:
        note_id: The ID of the text note

    Returns:
        Note details

    Raises:
        HTTPException: If note not found or is a list (use /api/lists/{id} instead)
    """
    try:
        keep = get_client()
        note = keep.get(note_id)

        if not note:
            raise HTTPException(status_code=404, detail=f"Note with ID {note_id} not found")

        # Validate this is a text note, not a list
        if hasattr(note, 'items') and note.items is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {note_id} is a list. Use GET /api/lists/{note_id} instead"
            )

        from .keep_api import serialize_note_only
        return serialize_note_only(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Create a new note (text notes only)
@app.post("/api/notes", response_model=NoteResponse)
async def create_note(note: NoteCreateRequest):
    """
    Create a new text note (not a list).

    Args:
        note: Note creation request with title and text

    Returns:
        Created note details

    Raises:
        HTTPException: If request contains items (should use /api/lists instead)
    """
    try:
        keep = get_client()
        new_note = keep.createNote(title=note.title, text=note.text)

        # Get or create the keep-mcp label
        label = keep.findLabel('keep-mcp')
        if not label:
            label = keep.createLabel('keep-mcp')

        # Add the label to the note
        new_note.labels.add(label)
        keep.sync()  # Ensure the note is created and labeled on the server

        from .keep_api import serialize_note_only
        return serialize_note_only(new_note)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Replace entire note (PUT)
@app.put("/api/notes/{note_id}", response_model=NoteResponse)
async def put_note(note_id: str, note_update: NotePutRequest):
    """
    Replace a text note entirely (title and text).

    Args:
        note_id: The ID of the text note to replace
        note_update: Complete note data to replace with

    Returns:
        Updated note details

    Raises:
        HTTPException: If note not found or is a list
    """
    try:
        keep = get_client()
        note = keep.get(note_id)

        if not note:
            raise HTTPException(status_code=404, detail=f"Note with ID {note_id} not found")

        # Validate this is a text note, not a list
        if hasattr(note, 'items') and note.items is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {note_id} is a list. Use PUT /api/lists/{note_id} instead"
            )

        if not can_modify_note(note):
            raise HTTPException(
                status_code=403,
                detail=f"Note with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Replace all fields
        note.title = note_update.title
        note.text = note_update.text

        keep.sync()  # Ensure changes are saved to the server

        from .keep_api import serialize_note_only
        return serialize_note_only(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Partially update a note (PATCH)
@app.patch("/api/notes/{note_id}", response_model=NoteResponse)
async def patch_note(note_id: str, note_update: NotePatchRequest):
    """
    Partially update a text note (title, text, color, or pinned status).

    Args:
        note_id: The ID of the text note to update
        note_update: Partial note data to update

    Returns:
        Updated note details

    Raises:
        HTTPException: If note not found or is a list
    """
    try:
        keep = get_client()
        note = keep.get(note_id)

        if not note:
            raise HTTPException(status_code=404, detail=f"Note with ID {note_id} not found")

        # Validate this is a text note, not a list
        if hasattr(note, 'items') and note.items is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {note_id} is a list. Use PATCH /api/lists/{note_id} instead"
            )

        if not can_modify_note(note):
            raise HTTPException(
                status_code=403,
                detail=f"Note with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Update only provided fields
        if note_update.title is not None:
            note.title = note_update.title
        if note_update.text is not None:
            note.text = note_update.text
        if note_update.color is not None:
            note.color = note_update.color
        if note_update.pinned is not None:
            note.pinned = note_update.pinned

        keep.sync()  # Ensure changes are saved to the server

        from .keep_api import serialize_note_only
        return serialize_note_only(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Delete a note (text notes only)
@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: str):
    """
    Delete a text note (mark for deletion).

    Args:
        note_id: The ID of the text note to delete

    Returns:
        Success message

    Raises:
        HTTPException: If note not found or is a list
    """
    try:
        keep = get_client()
        note = keep.get(note_id)

        if not note:
            raise HTTPException(status_code=404, detail=f"Note with ID {note_id} not found")

        # Validate this is a text note, not a list
        if hasattr(note, 'items') and note.items is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {note_id} is a list. Use DELETE /api/lists/{note_id} instead"
            )

        if not can_modify_note(note):
            raise HTTPException(
                status_code=403,
                detail=f"Note with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        note.delete()
        keep.sync()  # Ensure deletion is saved to the server
        return {"message": f"Note {note_id} marked for deletion", "status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Lists endpoints

# Create a new list
@app.post("/api/lists", response_model=ListResponse)
async def create_list(list_data: ListCreateRequest):
    """
    Create a new list with optional initial items.

    Args:
        list_data: List creation request with title and optional nested items

    Returns:
        Created list details with nested items
    """
    try:
        keep = get_client()
        from .keep_api import create_list, serialize_list

        list_obj = create_list(keep, list_data.title, list_data.items)
        return serialize_list(list_obj)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# List all lists (metadata only)
@app.get("/api/lists")
async def list_lists():
    """
    List all lists (non-archived, non-trashed).
    Returns metadata only - use GET /api/lists/{id} for full content with items.

    Returns:
        List of all lists (metadata only, no items)
    """
    try:
        keep = get_client()

        # Find all lists (notes that have items)
        all_notes = keep.find(archived=False, trashed=False)
        lists = [note for note in all_notes if hasattr(note, 'items') and note.items is not None]

        from .keep_api import serialize_note_metadata
        lists_data = [serialize_note_metadata(list_obj) for list_obj in lists]
        return {"lists": lists_data, "count": len(lists_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get a specific list
@app.get("/api/lists/{list_id}", response_model=ListResponse)
async def get_list(list_id: str):
    """
    Get a specific list by ID with all items included.

    Args:
        list_id: The ID of the list

    Returns:
        List details with nested items

    Raises:
        HTTPException: If list not found or is a text note
    """
    try:
        keep = get_client()
        list_obj = keep.get(list_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {list_id} not found")

        # Validate this is a list, not a text note
        if not hasattr(list_obj, 'items') or list_obj.items is None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {list_id} is a text note. Use GET /api/notes/{list_id} instead"
            )

        from .keep_api import serialize_list
        return serialize_list(list_obj)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Replace entire list (PUT)
@app.put("/api/lists/{list_id}", response_model=ListResponse)
async def put_list(list_id: str, list_update: ListPutRequest):
    """
    Replace a list entirely (title and all items).

    Args:
        list_id: The ID of the list to replace
        list_update: Complete list data to replace with

    Returns:
        Updated list details with nested items

    Raises:
        HTTPException: If list not found or is a text note
    """
    try:
        keep = get_client()
        list_obj = keep.get(list_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {list_id} not found")

        # Validate this is a list, not a text note
        if not hasattr(list_obj, 'items') or list_obj.items is None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {list_id} is a text note. Use PUT /api/notes/{list_id} instead"
            )

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {list_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Delete all existing items
        for item in list(list_obj.items):
            item.delete()

        # Update title
        list_obj.title = list_update.title

        # Add new items if provided
        if list_update.items:
            _add_items_recursively(list_obj, list_update.items)

        keep.sync()  # Ensure changes are saved to the server

        from .keep_api import serialize_list
        return serialize_list(list_obj)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Partially update list metadata (PATCH)
@app.patch("/api/lists/{list_id}", response_model=ListResponse)
async def patch_list(list_id: str, list_update: ListPatchRequest):
    """
    Partially update list metadata (title, color, pinned) without affecting items.

    Args:
        list_id: The ID of the list to update
        list_update: Partial list metadata to update

    Returns:
        Updated list details with nested items

    Raises:
        HTTPException: If list not found or is a text note
    """
    try:
        keep = get_client()
        list_obj = keep.get(list_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {list_id} not found")

        # Validate this is a list, not a text note
        if not hasattr(list_obj, 'items') or list_obj.items is None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {list_id} is a text note. Use PATCH /api/notes/{list_id} instead"
            )

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {list_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Update only provided metadata fields (not items)
        if list_update.title is not None:
            list_obj.title = list_update.title
        if list_update.color is not None:
            list_obj.color = list_update.color
        if list_update.pinned is not None:
            list_obj.pinned = list_update.pinned

        keep.sync()  # Ensure changes are saved to the server

        from .keep_api import serialize_list
        return serialize_list(list_obj)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Delete a list
@app.delete("/api/lists/{list_id}")
async def delete_list(list_id: str):
    """
    Delete a list entirely (mark for deletion).

    Args:
        list_id: The ID of the list to delete

    Returns:
        Success message

    Raises:
        HTTPException: If list not found or is a text note
    """
    try:
        keep = get_client()
        list_obj = keep.get(list_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {list_id} not found")

        # Validate this is a list, not a text note
        if not hasattr(list_obj, 'items') or list_obj.items is None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {list_id} is a text note. Use DELETE /api/notes/{list_id} instead"
            )

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {list_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        list_obj.delete()
        keep.sync()  # Ensure deletion is saved to the server
        return {"message": f"List {list_id} marked for deletion", "status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# List items endpoints

# Add items to a list
@app.post("/api/lists/{list_id}/items")
async def add_list_items(list_id: str, items_request: ItemAddRequest):
    """
    Add one or more items to an existing list. Supports nested children.

    Args:
        list_id: The ID of the list to add items to
        items_request: Array of items to add with optional nested structure

    Returns:
        Success response with added items count

    Raises:
        HTTPException: If list not found or is a text note
    """
    try:
        keep = get_client()
        list_obj = keep.get(list_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {list_id} not found")

        # Validate this is a list, not a text note
        if not hasattr(list_obj, 'items') or list_obj.items is None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {list_id} is a text note. Use PATCH /api/notes/{list_id} instead"
            )

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {list_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Add items recursively
        created_items = _add_items_recursively(list_obj, items_request.items)
        keep.sync()  # Ensure changes are saved to the server

        return {
            "message": f"Added {len(created_items)} items to list {list_id}",
            "items_added": len(created_items),
            "status": "success"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get a specific list item
@app.get("/api/lists/{list_id}/items/{item_id}", response_model=ItemResponse)
async def get_list_item(list_id: str, item_id: str):
    """
    Get a specific item from a list.

    Args:
        list_id: The ID of the list containing the item
        item_id: The ID of the item to retrieve

    Returns:
        Item details

    Raises:
        HTTPException: If list or item not found
    """
    try:
        keep = get_client()
        list_obj = keep.get(list_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {list_id} not found")

        # Validate this is a list, not a text note
        if not hasattr(list_obj, 'items') or list_obj.items is None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {list_id} is a text note"
            )

        # Find the item by ID
        target_item = None
        for item in list_obj.items:
            if item.id == item_id:
                target_item = item
                break

        if not target_item:
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found in list {list_id}")

        return ItemResponse(
            id=target_item.id,
            text=target_item.text,
            checked=target_item.checked,
            parent_item_id=target_item.parent_item.id if target_item.parent_item else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Update a specific list item
@app.patch("/api/lists/{list_id}/items/{item_id}", response_model=ItemResponse)
async def patch_list_item(list_id: str, item_id: str, item_update: ItemPatchRequest):
    """
    Update a specific item in a list (text, checked status, or parent_item_id).

    Args:
        list_id: The ID of the list containing the item
        item_id: The ID of the item to update
        item_update: Item fields to update

    Returns:
        Updated item details

    Raises:
        HTTPException: If list or item not found
    """
    try:
        keep = get_client()
        list_obj = keep.get(list_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {list_id} not found")

        # Validate this is a list, not a text note
        if not hasattr(list_obj, 'items') or list_obj.items is None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {list_id} is a text note"
            )

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {list_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Find the item by ID
        target_item = None
        for item in list_obj.items:
            if item.id == item_id:
                target_item = item
                break

        if not target_item:
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found in list {list_id}")

        # Update provided fields
        if item_update.text is not None:
            target_item.text = item_update.text

        # Handle checked status with cascading logic
        if item_update.checked is not None:
            _update_item_checked_with_cascade(list_obj.items, target_item, item_update.checked)

        # Handle nesting changes
        if item_update.parent_item_id is not None:
            if item_update.parent_item_id:
                # Find the new parent item
                new_parent = None
                for item in list_obj.items:
                    if item.id == item_update.parent_item_id:
                        new_parent = item
                        break

                if not new_parent:
                    raise HTTPException(status_code=400, detail=f"Parent item with ID {item_update.parent_item_id} not found")

                # Indent under the new parent
                new_parent.indent(target_item)
            else:
                # Unindent (dedent) the item
                if target_item.parent_item:
                    target_item.parent_item.dedent(target_item)

        keep.sync()  # Ensure changes are saved to the server

        return ItemResponse(
            id=target_item.id,
            text=target_item.text,
            checked=target_item.checked,
            parent_item_id=target_item.parent_item.id if target_item.parent_item else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Delete a specific list item
@app.delete("/api/lists/{list_id}/items/{item_id}")
async def delete_list_item(list_id: str, item_id: str):
    """
    Delete a specific item from a list, including all its children.

    Args:
        list_id: The ID of the list containing the item
        item_id: The ID of the item to delete

    Returns:
        Success message

    Raises:
        HTTPException: If list or item not found
    """
    try:
        keep = get_client()
        list_obj = keep.get(list_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {list_id} not found")

        # Validate this is a list, not a text note
        if not hasattr(list_obj, 'items') or list_obj.items is None:
            raise HTTPException(
                status_code=400,
                detail=f"Note with ID {list_id} is a text note"
            )

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {list_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Find the item to delete
        target_item = None
        for item in list_obj.items:
            if item.id == item_id:
                target_item = item
                break

        if not target_item:
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found in list {list_id}")

        # Store parent reference before deletion for status update
        parent_item = target_item.parent_item

        # Recursively delete the item and all its children
        _delete_item_with_children(list_obj.items, target_item)

        # Update parent's checked status if the deleted item was checked
        if parent_item and target_item.checked:
            _update_parent_checked_status(list_obj.items, parent_item)

        keep.sync()  # Ensure changes are saved to the server

        return {
            "message": f"Item {item_id} and its children deleted from list {list_id}",
            "status": "success"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Collaborator endpoints

@app.post("/api/notes/{note_id}/collaborators", response_model=CollaboratorResponse)
async def add_collaborator(note_id: str, collaborator: CollaboratorRequest):
    """
    Add a collaborator to a note.

    Args:
        note_id: The ID of the note to share
        collaborator: Collaborator information with email

    Returns:
        Collaborator response with note_id and email
    """
    try:
        result = share_note(note_id, collaborator.email)
        return CollaboratorResponse(email=result["email"], note_id=result["note_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/notes/{note_id}/collaborators/{email}")
async def remove_collaborator(note_id: str, email: str):
    """
    Remove a collaborator from a note.

    Args:
        note_id: The ID of the note
        email: Email address of the collaborator to remove

    Returns:
        Success message
    """
    try:
        result = unshare_note(note_id, email)
        return {"message": result["message"], "status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notes/{note_id}/collaborators", response_model=CollaboratorsListResponse)
async def get_collaborators(note_id: str):
    """
    Get all collaborators for a note.

    Args:
        note_id: The ID of the note

    Returns:
        List of collaborators
    """
    try:
        collaborators = list_collaborators(note_id)
        return CollaboratorsListResponse(
            note_id=note_id,
            collaborators=collaborators,
            count=len(collaborators)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("REST_API_HOST", "0.0.0.0")
    port = int(os.getenv("REST_API_PORT", "8001"))

    print(f"Starting Google Keep REST API server on {host}:{port}")
    print(f"Documentation available at http://{host}:{port}/docs")

    uvicorn.run(app, host=host, port=port)
