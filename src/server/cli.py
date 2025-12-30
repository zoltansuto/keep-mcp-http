"""
MCP plugin for Google Keep integration.
Provides tools for interacting with Google Keep notes through MCP.
"""

import json
from typing import Optional
from mcp.server.fastmcp import FastMCP
from .keep_api import get_client, serialize_note, can_modify_note, share_note, unshare_note, list_collaborators

mcp = FastMCP("keep")

def _is_null_like(value: Optional[str]) -> bool:
    """
    Check if a value represents null/None in various string forms.

    Args:
        value: The value to check

    Returns:
        True if the value represents null/None, False otherwise
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.lower().strip() in ("null", "none", "undefined", "")
    return False

@mcp.tool()
def find_note(query="") -> str:
    """
    Find notes based on a search query (case-insensitive).

    Args:
        query (str, optional): A string to match against the title and text

    Returns:
        str: JSON string containing the matching notes with their id, title, text, pinned status, color and labels
    """
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
    return json.dumps(notes_data)

@mcp.tool()
def create_note(title: str = None, text: str = None) -> str:
    """
    Create a new note in Google Keep.

    This tool creates a brand new note that doesn't exist yet. Do not use this tool to modify existing notes.

    Args:
        title (str, optional): The title of the new note
        text (str, optional): The content/text of the new note

    Returns:
        str: JSON string containing the created note's data
    """
    keep = get_client()
    note = keep.createNote(title=title, text=text)
    
    # Get or create the keep-mcp label
    label = keep.findLabel('keep-mcp')
    if not label:
        label = keep.createLabel('keep-mcp')
    
    # Add the label to the note
    note.labels.add(label)
    keep.sync()  # Ensure the note is created and labeled on the server
    
    return json.dumps(serialize_note(note))

@mcp.tool()
def update_note(note_id: str, title: str = None, text: str = None) -> str:
    """
    Update an existing note's title and/or text content.

    This tool modifies an existing note that already exists in Google Keep. You must provide the note_id of an existing note.
    Do not use this tool to create new notes - use create_note instead.

    Args:
        note_id (str): The unique ID of the existing note to update (required)
        title (str, optional): New title for the note. If None, title remains unchanged.
        text (str, optional): New text content for the note. If None, text remains unchanged.

    Returns:
        str: JSON string containing the updated note's data

    Raises:
        ValueError: If the note doesn't exist or cannot be modified
    """
    keep = get_client()
    note = keep.get(note_id)
    
    if not note:
        raise ValueError(f"Note with ID {note_id} not found")
    
    if not can_modify_note(note):
        raise ValueError(f"Note with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)")
    
    if title is not None:
        note.title = title
    if text is not None:
        note.text = text
    
    keep.sync()  # Ensure changes are saved to the server
    return json.dumps(serialize_note(note))

@mcp.tool()
def share_note(note_id: str, email: str) -> str:
    """
    Share a note with a collaborator by adding them as a collaborator.

    Args:
        note_id (str): The ID of the note to share
        email (str): Email address of the collaborator to add

    Returns:
        str: JSON string containing the sharing result

    Raises:
        ValueError: If the note doesn't exist or cannot be shared
    """
    try:
        result = share_note(note_id, email)
        return json.dumps(result)
    except ValueError as e:
        raise ValueError(str(e))

@mcp.tool()
def unshare_note(note_id: str, email: str) -> str:
    """
    Remove a collaborator from a note.

    Args:
        note_id (str): The ID of the note
        email (str): Email address of the collaborator to remove

    Returns:
        str: JSON string containing the result

    Raises:
        ValueError: If the note doesn't exist or collaborator cannot be removed
    """
    try:
        result = unshare_note(note_id, email)
        return json.dumps(result)
    except ValueError as e:
        raise ValueError(str(e))

@mcp.tool()
def list_collaborators(note_id: str) -> str:
    """
    List all collaborators for a note.

    Args:
        note_id (str): The ID of the note

    Returns:
        str: JSON string containing the list of collaborators

    Raises:
        ValueError: If the note doesn't exist
    """
    try:
        collaborators = list_collaborators(note_id)
        return json.dumps({
            "note_id": note_id,
            "collaborators": collaborators,
            "count": len(collaborators)
        })
    except ValueError as e:
        raise ValueError(str(e))

@mcp.tool()
def delete_note(note_id: str) -> str:
    """
    Delete a note (mark for deletion).
    
    Args:
        note_id (str): The ID of the note to delete
        
    Returns:
        str: Success message
        
    Raises:
        ValueError: If the note doesn't exist or cannot be modified
    """
    keep = get_client()
    note = keep.get(note_id)
    
    if not note:
        raise ValueError(f"Note with ID {note_id} not found")
    
    if not can_modify_note(note):
        raise ValueError(f"Note with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)")
    
    note.delete()
    keep.sync()  # Ensure deletion is saved to the server
    return json.dumps({"message": f"Note {note_id} marked for deletion"})


@mcp.tool()
def note_add_list_item(note_id: str, text: str, checked: bool = False, parent_item_id: Optional[str] = None) -> str:
    """
    Add an item to an existing list. Supports nested items via parent_item_id.

    Args:
        note_id (str): The ID of the note/list to add the item to
        text (str): The text content of the new list item
        checked (bool, optional): Whether the item should be checked/selected (default: False)
        parent_item_id (Optional[str]): ID of an existing list item to nest this item under.
            Pass None, omit, or any null-like value ("null", "none", "undefined", "") to create a top-level item.
            Pass a valid item ID to create a nested sub-item.

    Returns:
        str: JSON string containing the updated list's data with the new item

    Raises:
        ValueError: If the list doesn't exist, cannot be modified, or parent_item_id is invalid
    """
    keep = get_client()
    list_obj = keep.get(note_id)

    if not list_obj:
        raise ValueError(f"List with ID {note_id} not found")

    if not hasattr(list_obj, 'items'):
        raise ValueError(f"Note with ID {note_id} is not a list")

    if not can_modify_note(list_obj):
        raise ValueError(f"List with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)")

    # Add the item
    new_item = list_obj.add(text, checked)

    # If parent_item_id is specified, indent the item
    if not _is_null_like(parent_item_id):
        parent_item = None
        for item in list_obj.items:
            if item.id == parent_item_id:
                parent_item = item
                break

        if parent_item:
            parent_item.indent(new_item)
            # If adding a checked item to a parent, update parent's checked status
            if checked:
                _update_parent_checked_status_mcp(list_obj.items, new_item)
        else:
            raise ValueError(f"Parent item with ID {parent_item_id} not found")

    keep.sync()  # Ensure changes are saved to the server

    return json.dumps(serialize_note(list_obj))

@mcp.tool()
def note_update_list_item(note_id: str, item_id: str, text: Optional[str] = None, checked: Optional[bool] = None, parent_item_id: Optional[str] = None) -> str:
    """
    Update a specific item in a list. Supports changing nesting via parent_item_id.
    Automatically handles cascading check behavior for nested items.

    Args:
        note_id (str): The ID of the note/list containing the item
        item_id (str): The ID of the specific list item to update
        text (Optional[str]): New text content for the item. Pass None to leave unchanged.
        checked (Optional[bool]): New checked/selected status for the item. Pass None to leave unchanged.
            When checking/unchecking, automatically updates parent and child items according to Google Keep's nesting rules.
        parent_item_id (Optional[str]): New parent item ID for nesting. Pass None or any null-like value
            ("null", "none", "undefined", "") to unindent to top-level. Pass a valid item ID to indent under that parent.
            Pass None or omit to leave nesting unchanged.

    Returns:
        str: JSON string containing the updated list's data

    Raises:
        ValueError: If the list/item doesn't exist, cannot be modified, or parent_item_id is invalid
    """
    keep = get_client()
    list_obj = keep.get(note_id)

    if not list_obj:
        raise ValueError(f"List with ID {note_id} not found")

    if not hasattr(list_obj, 'items'):
        raise ValueError(f"Note with ID {note_id} is not a list")

    if not can_modify_note(list_obj):
        raise ValueError(f"List with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)")

    # Find the item by ID
    target_item = None
    for item in list_obj.items:
        if item.id == item_id:
            target_item = item
            break

        if not target_item:
            raise ValueError(f"Item with ID {item_id} not found in list {note_id}")

        # Update basic properties
    if text is not None:
        target_item.text = text

    # Handle checked status with cascading logic
    if checked is not None:
        _update_item_checked_with_cascade_mcp(list_obj.items, target_item, checked)

    # Handle nesting changes
    if not _is_null_like(parent_item_id):
        # Find the new parent item
        new_parent = None
        for item in list_obj.items:
            if item.id == parent_item_id:
                new_parent = item
                break

        if not new_parent:
            raise ValueError(f"Parent item with ID {parent_item_id} not found")

        # Indent under the new parent
        new_parent.indent(target_item)
    else:
        # Unindent (dedent) the item
        if target_item.parent_item:
            target_item.parent_item.dedent(target_item)

    keep.sync()  # Ensure changes are saved to the server
    return json.dumps(serialize_note(list_obj))

def _update_item_checked_with_cascade_mcp(all_items, target_item, checked):
    """
    Update an item's checked status with cascading behavior for nested items (MCP version).

    Args:
        all_items: List of all items in the list
        target_item: The item being updated
        checked: New checked status
    """
    # Set the target item's checked status
    target_item.checked = checked

    if checked:
        # If checking an item, check all its children recursively
        _check_all_children_mcp(all_items, target_item)
    else:
        # If unchecking an item, uncheck all its children recursively
        _uncheck_all_children_mcp(all_items, target_item)

    # Update parent checked status based on children
    _update_parent_checked_status_mcp(all_items, target_item)

def _check_all_children_mcp(all_items, parent_item):
    """Recursively check all children of a parent item (MCP version)."""
    for item in all_items:
        if item.parent_item and item.parent_item.id == parent_item.id:
            item.checked = True
            _check_all_children_mcp(all_items, item)  # Recurse for grandchildren

def _uncheck_all_children_mcp(all_items, parent_item):
    """Recursively uncheck all children of a parent item (MCP version)."""
    for item in all_items:
        if item.parent_item and item.parent_item.id == parent_item.id:
            item.checked = False
            _uncheck_all_children_mcp(all_items, item)  # Recurse for grandchildren

def _update_parent_checked_status_mcp(all_items, child_item):
    """Update parent item's checked status based on whether all siblings are checked (MCP version)."""
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
        _update_parent_checked_status_mcp(all_items, parent)

def _delete_item_with_children_mcp(all_items, target_item):
    """
    Recursively delete an item and all its children (MCP version).

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
        _delete_item_with_children_mcp(all_items, child)

    # Then delete the target item itself
    target_item.delete()

@mcp.tool()
def note_delete_list_item(note_id: str, item_id: str) -> str:
    """
    Delete a specific item from a list. Updates parent checked status if needed.

    Args:
        note_id (str): The ID of the note/list
        item_id (str): The ID of the item to delete

    Returns:
        str: JSON string containing the updated list's data

    Raises:
        ValueError: If the list or item doesn't exist or cannot be modified
    """
    keep = get_client()
    list_obj = keep.get(note_id)

    if not list_obj:
        raise ValueError(f"List with ID {note_id} not found")

    if not hasattr(list_obj, 'items'):
        raise ValueError(f"Note with ID {note_id} is not a list")

    if not can_modify_note(list_obj):
        raise ValueError(f"List with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)")

    # Find the item to delete
    target_item = None
    for item in list_obj.items:
        if item.id == item_id:
            target_item = item
            break

        if not target_item:
            raise ValueError(f"Item with ID {item_id} not found in list {note_id}")

        # Store parent reference before deletion for status update
    parent_item = target_item.parent_item

    # Recursively delete the item and all its children
    _delete_item_with_children_mcp(list_obj.items, target_item)

    # Update parent's checked status if the deleted item was checked
    if parent_item and target_item.checked:
        _update_parent_checked_status_mcp(list_obj.items, parent_item)

    keep.sync()  # Ensure changes are saved to the server

    return json.dumps(serialize_note(list_obj))

def main():
    mcp.run(transport='stdio')


if __name__ == "__main__":
    main()
    