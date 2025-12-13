import gkeepapi
import os
from dotenv import load_dotenv

_keep_client = None

def get_client():
    """
    Get or initialize the Google Keep client.
    This ensures we only authenticate once and reuse the client.
    
    Returns:
        gkeepapi.Keep: Authenticated Keep client
    """
    global _keep_client
    
    if _keep_client is not None:
        return _keep_client
    
    # Load environment variables
    load_dotenv()
    
    # Get credentials from environment variables
    email = os.getenv('GOOGLE_EMAIL')
    master_token = os.getenv('GOOGLE_MASTER_TOKEN')
    
    if not email or not master_token:
        raise ValueError("Missing Google Keep credentials. Please set GOOGLE_EMAIL and GOOGLE_MASTER_TOKEN environment variables.")
    
    # Initialize the Keep API
    keep = gkeepapi.Keep()
    
    # Authenticate
    keep.authenticate(email, master_token)
    
    # Store the client for reuse
    _keep_client = keep
    
    return keep

def serialize_note(note):
    """
    Serialize a Google Keep note or list into a dictionary.

    Args:
        note: A Google Keep note or list object

    Returns:
        dict: A dictionary containing the note's/list's data
    """
    # Check if this is a list
    is_list = hasattr(note, 'items') and note.items is not None

    base_data = {
        'id': note.id,
        'title': note.title,
        'text': note.text,
        'pinned': note.pinned,
        'color': note.color.value if note.color else None,
        'labels': [{'id': label.id, 'name': label.name} for label in note.labels.all()],
        'collaborators': list(note.collaborators.all()) if hasattr(note, 'collaborators') else [],
        'type': 'list' if is_list else 'note'
    }

    if is_list:
        # Add list-specific data
        base_data['items'] = [
            {
                'id': item.id,
                'text': item.text,
                'checked': item.checked,
                'sort': item.sort,
                'indented': getattr(item, 'indented', False),
                'parent_item_id': item.parent_item.id if item.parent_item else None
            }
            for item in note.items
        ]

    return base_data

def can_modify_note(note):
    """
    Check if a note can be modified based on label and environment settings.
    
    Args:
        note: A Google Keep note object
        
    Returns:
        bool: True if the note can be modified, False otherwise
    """
    unsafe_mode = os.getenv('UNSAFE_MODE', '').lower() == 'true'
    return unsafe_mode or has_keep_mcp_label(note)

def has_keep_mcp_label(note):
    """
    Check if a note has the keep-mcp label.

    Args:
        note: A Google Keep note object

    Returns:
        bool: True if the note has the keep-mcp label, False otherwise
    """
    return any(label.name == 'keep-mcp' for label in note.labels.all())

def can_manage_collaborators(note):
    """
    Check if a note's collaborators can be managed based on label and environment settings.

    Args:
        note: A Google Keep note object

    Returns:
        bool: True if collaborators can be managed, False otherwise
    """
    unsafe_mode = os.getenv('UNSAFE_MODE', '').lower() == 'true'
    return unsafe_mode or has_keep_mcp_label(note)

def share_note(note_id, email, role=None):
    """
    Share a note with a collaborator.

    Args:
        note_id (str): The ID of the note to share
        email (str): Email address of the collaborator
        role (str, optional): Role/permission level for the collaborator

    Returns:
        dict: Success status and collaborator info

    Raises:
        ValueError: If note not found or cannot be shared
    """
    keep = get_client()
    note = keep.get(note_id)

    if not note:
        raise ValueError(f"Note with ID {note_id} not found")

    if not can_manage_collaborators(note):
        raise ValueError(f"Note with ID {note_id} cannot be shared (missing keep-mcp label and UNSAFE_MODE is not enabled)")

    # Add the collaborator
    note.collaborators.add(email)

    # Sync changes
    keep.sync()

    return {
        "message": f"Note {note_id} shared with {email}",
        "email": email,
        "note_id": note_id
    }

def unshare_note(note_id, email):
    """
    Remove a collaborator from a note.

    Args:
        note_id (str): The ID of the note
        email (str): Email address of the collaborator to remove

    Returns:
        dict: Success status

    Raises:
        ValueError: If note not found or cannot be modified
    """
    keep = get_client()
    note = keep.get(note_id)

    if not note:
        raise ValueError(f"Note with ID {note_id} not found")

    if not can_manage_collaborators(note):
        raise ValueError(f"Note with ID {note_id} cannot be modified (missing keep-mcp label and UNSAFE_MODE is not enabled)")

    # Check if the collaborator exists
    if email not in note.collaborators.all():
        raise ValueError(f"Collaborator {email} not found for note {note_id}")

    # Remove the collaborator
    note.collaborators.remove(email)

    # Sync changes
    keep.sync()

    return {
        "message": f"Removed {email} from note {note_id}",
        "email": email,
        "note_id": note_id
    }

def list_collaborators(note_id):
    """
    Get all collaborators for a note.

    Args:
        note_id (str): The ID of the note

    Returns:
        list: List of collaborator emails

    Raises:
        ValueError: If note not found
    """
    keep = get_client()
    note = keep.get(note_id)

    if not note:
        raise ValueError(f"Note with ID {note_id} not found")

    collaborators = note.collaborators.all()
    return list(collaborators) 