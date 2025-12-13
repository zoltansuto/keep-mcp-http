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
class NoteSearchRequest(BaseModel):
    query: Optional[str] = Field(default="", description="Search query string")

class NoteCreateRequest(BaseModel):
    title: Optional[str] = Field(None, description="Note title")
    text: Optional[str] = Field(None, description="Note text content")

class NoteUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, description="New title")
    text: Optional[str] = Field(None, description="New text content")

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    service: str
    google_keep_connected: bool
    version: str = get_project_version()

class NoteResponse(BaseModel):
    id: str
    title: Optional[str]
    text: Optional[str]
    pinned: bool
    color: Optional[str]
    labels: List[Dict[str, str]]
    collaborators: List[str] = []
    type: str = "note"

class ListItem(BaseModel):
    id: Optional[str] = None
    text: str
    checked: bool = False
    sort: Optional[int] = None
    parent_item_id: Optional[str] = None

class ListResponse(NoteResponse):
    items: List[Dict[str, Any]] = []

class ListCreateRequest(BaseModel):
    title: Optional[str] = Field(None, description="List title")
    items: List[ListItem] = Field(default_factory=list, description="List items")

class ListUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, description="New title")
    items: Optional[List[ListItem]] = Field(None, description="Updated list items")

class ListItemUpdateRequest(BaseModel):
    text: Optional[str] = Field(None, description="Updated text")
    checked: Optional[bool] = Field(None, description="Checked status")
    parent_item_id: Optional[str] = Field(None, description="New parent item ID for nesting (null to unindent)")

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

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "Google Keep REST API",
        "version": get_project_version(),
        "endpoints": {
            "health": "/api/health",
            "search": "GET /api/notes/search?query=...",
            "create_note": "POST /api/notes",
            "get": "GET /api/notes/{note_id}",
            "update_note": "PUT /api/notes/{note_id}",
            "delete_note": "DELETE /api/notes/{note_id}",
            "list": "GET /api/notes",
            "add_item": "POST /api/notes/{note_id}/lists/items",
            "update_item": "PUT /api/notes/{note_id}/lists/items/{item_id}",
            "delete_item": "DELETE /api/notes/{note_id}/lists/items/{item_id}",
            "add_collaborator": "POST /api/notes/{note_id}/collaborators",
            "remove_collaborator": "DELETE /api/notes/{note_id}/collaborators/{email}",
            "get_collaborators": "GET /api/notes/{note_id}/collaborators",
        },
        "docs": "/docs"
    }

# Search/find notes
@app.get("/api/notes/search")
async def search_notes(query: str = ""):
    """
    Search for notes matching the query string (case-insensitive).

    Args:
        query: Search query string

    Returns:
        List of matching notes
    """
    try:
        keep = get_client()

        if not query:
            # If no query, return all notes
            notes = keep.find(archived=False, trashed=False)
        else:
            # Always do case-insensitive search
            all_notes = keep.find(archived=False, trashed=False)
            query_lower = query.lower()
            notes = [
                note for note in all_notes
                if query_lower in (note.title or "").lower() or query_lower in (note.text or "").lower()
            ]

        notes_data = [serialize_note(note) for note in notes]
        return {"notes": notes_data, "count": len(notes_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# List all notes (same as search with empty query)
@app.get("/api/notes")
async def list_notes():
    """
    List all notes (non-archived, non-trashed).

    Returns:
        List of all notes
    """
    return await search_notes(query="")

# Get a specific note
@app.get("/api/notes/{note_id}")
async def get_note(note_id: str):
    """
    Get a specific note by ID.

    Args:
        note_id: The ID of the note

    Returns:
        Note details
    """
    try:
        keep = get_client()
        note = keep.get(note_id)

        if not note:
            raise HTTPException(status_code=404, detail=f"Note with ID {note_id} not found")

        return serialize_note(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Create a new note
@app.post("/api/notes", response_model=NoteResponse)
async def create_note(note: NoteCreateRequest):
    """
    Create a new note with title and text.

    Args:
        note: Note creation request with title and text

    Returns:
        Created note details
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

        return serialize_note(new_note)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Update a note
@app.put("/api/notes/{note_id}", response_model=NoteResponse)
async def update_note(note_id: str, note_update: NoteUpdateRequest):
    """
    Update a note's title and/or text.

    Args:
        note_id: The ID of the note to update
        note_update: Updated note data

    Returns:
        Updated note details
    """
    try:
        keep = get_client()
        note = keep.get(note_id)

        if not note:
            raise HTTPException(status_code=404, detail=f"Note with ID {note_id} not found")

        if not can_modify_note(note):
            raise HTTPException(
                status_code=403,
                detail=f"Note with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        if note_update.title is not None:
            note.title = note_update.title
        if note_update.text is not None:
            note.text = note_update.text

        keep.sync()  # Ensure changes are saved to the server
        return serialize_note(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Delete a note
@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: str):
    """
    Delete a note (mark for deletion).

    Args:
        note_id: The ID of the note to delete

    Returns:
        Success message
    """
    try:
        keep = get_client()
        note = keep.get(note_id)

        if not note:
            raise HTTPException(status_code=404, detail=f"Note with ID {note_id} not found")

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

# List-specific endpoints

# Add item to list
@app.post("/api/notes/{note_id}/lists/items", response_model=ListResponse)
async def add_list_item(note_id: str, item: ListItem):
    """
    Add an item to an existing list. Supports nested items via parent_item_id.

    Args:
        note_id: The ID of the note/list
        item: Item to add with optional parent_item_id for nesting

    Returns:
        Updated list details
    """
    try:
        keep = get_client()
        list_obj = keep.get(note_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {note_id} not found")

        if not hasattr(list_obj, 'items'):
            raise HTTPException(status_code=400, detail=f"Note with ID {note_id} is not a list")

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Add the item
        new_item = list_obj.add(item.text, item.checked)

        # If parent_item_id is specified, indent the item
        if item.parent_item_id:
            parent_item = None
            for existing_item in list_obj.items:
                if existing_item.id == item.parent_item_id:
                    parent_item = existing_item
                    break

            if parent_item:
                parent_item.indent(new_item)
                # If adding a checked item to a parent, update parent's checked status
                if item.checked:
                    _update_parent_checked_status(list_obj.items, new_item)
            else:
                raise HTTPException(status_code=400, detail=f"Parent item with ID {item.parent_item_id} not found")

        keep.sync()  # Ensure changes are saved to the server

        return serialize_note(list_obj)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Update list item
@app.put("/api/notes/{note_id}/lists/items/{item_id}", response_model=ListResponse)
async def update_list_item(note_id: str, item_id: str, item_update: ListItemUpdateRequest):
    """
    Update a specific item in a list. Supports changing nesting via parent_item_id.
    Automatically handles cascading check behavior for nested items.

    Args:
        note_id: The ID of the note/list
        item_id: The ID of the item to update
        item_update: Updated item data (text, checked, parent_item_id)

    Returns:
        Updated list details
    """
    try:
        keep = get_client()
        list_obj = keep.get(note_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {note_id} not found")

        if not hasattr(list_obj, 'items'):
            raise HTTPException(status_code=400, detail=f"Note with ID {note_id} is not a list")

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Find the item by ID
        target_item = None
        for item in list_obj.items:
            if item.id == item_id:
                target_item = item
                break

        if not target_item:
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found in list {note_id}")

        # Update basic properties
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
        return serialize_note(list_obj)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Delete list item
@app.delete("/api/notes/{note_id}/lists/items/{item_id}", response_model=ListResponse)
async def delete_list_item(note_id: str, item_id: str):
    """
    Delete a specific item from a list. Updates parent checked status if needed.

    Args:
        note_id: The ID of the note/list
        item_id: The ID of the item to delete

    Returns:
        Updated list details
    """
    try:
        keep = get_client()
        list_obj = keep.get(note_id)

        if not list_obj:
            raise HTTPException(status_code=404, detail=f"List with ID {note_id} not found")

        if not hasattr(list_obj, 'items'):
            raise HTTPException(status_code=400, detail=f"Note with ID {note_id} is not a list")

        if not can_modify_note(list_obj):
            raise HTTPException(
                status_code=403,
                detail=f"List with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)"
            )

        # Find the item to delete
        target_item = None
        for item in list_obj.items:
            if item.id == item_id:
                target_item = item
                break

        if not target_item:
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found in list {note_id}")

        # Store parent reference before deletion for status update
        parent_item = target_item.parent_item

        # Recursively delete the item and all its children
        _delete_item_with_children(list_obj.items, target_item)

        # Update parent's checked status if the deleted item was checked
        if parent_item and target_item.checked:
            _update_parent_checked_status(list_obj.items, parent_item)

        keep.sync()  # Ensure changes are saved to the server

        return serialize_note(list_obj)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("REST_API_HOST", "0.0.0.0")
    port = int(os.getenv("REST_API_PORT", "8001"))

    print(f"Starting Google Keep REST API server on {host}:{port}")
    print(f"Documentation available at http://{host}:{port}/docs")

    uvicorn.run(app, host=host, port=port)
