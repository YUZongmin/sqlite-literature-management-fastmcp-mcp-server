from pathlib import Path
import sqlite3
import os
import json
import uuid
from typing import List, Dict, Any, Optional, Tuple, Set
from fastmcp import FastMCP
from datetime import datetime
import re

# Initialize FastMCP server
mcp = FastMCP("Source Manager")

# Path to Literature database - must be provided via SQLITE_DB_PATH environment variable
if 'SQLITE_DB_PATH' not in os.environ:
    raise ValueError("SQLITE_DB_PATH environment variable must be set")
DB_PATH = Path(os.environ['SQLITE_DB_PATH'])


# Classes

class SourceIdentifiers:
    """Defines valid identifier types for sources"""
    VALID_TYPES = {
        'semantic_scholar',  # For academic papers via Semantic Scholar
        'arxiv',            # For arXiv papers
        'doi',             # For papers with DOI
        'isbn',            # For books
        'url'              # For webpages, blogs, videos
    }

class SourceTypes:
    """Defines valid source types"""
    VALID_TYPES = {'paper', 'webpage', 'book', 'video', 'blog'}

class SourceStatus:
    """Defines valid source status values"""
    VALID_STATUS = {'unread', 'reading', 'completed', 'archived'}

class SQLiteConnection:
    """Context manager for SQLite database connections"""
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = None
        
    def __enter__(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        return self.conn
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

class EntityRelations:
    """Defines valid relation types for entity links"""
    VALID_TYPES = {
        'discusses',
        'introduces', 
        'extends',
        'evaluates',
        'applies',
        'critiques'
    }


# Helper Functions
def search_sources(
    sources: List[Tuple[str, str, str, str]],  # List of (title, type, identifier_type, identifier_value)
    db_path: Path
) -> List[Tuple[Optional[str], List[Dict]]]:
    """
    Bulk search for multiple sources simultaneously while maintaining consistent return format.
    
    Args:
        sources: List of tuples, each containing:
            - title: Source title
            - type: Source type
            - identifier_type: Type of identifier
            - identifier_value: Value of the identifier
        db_path: Path to SQLite database
    
    Returns:
        List of tuples, each containing:
        - UUID of exact match if found by identifier (else None)
        - List of potential matches by title/type (empty if exact match found)
    """
    results = []
    
    with SQLiteConnection(db_path) as conn:
        cursor = conn.cursor()
        
        # Process each source maintaining the same logic and return structure
        for title, type_, identifier_type, identifier_value in sources:
            # Validate inputs (just like in original)
            if type_ not in SourceTypes.VALID_TYPES:
                raise ValueError(f"Invalid source type. Must be one of: {SourceTypes.VALID_TYPES}")
            if identifier_type not in SourceIdentifiers.VALID_TYPES:
                raise ValueError(f"Invalid identifier type. Must be one of: {SourceIdentifiers.VALID_TYPES}")
            
            # First try exact identifier match
            cursor.execute("""
                SELECT id FROM sources
                WHERE type = ? AND 
                      json_extract(identifiers, ?) = ?
            """, [
                type_,
                f"$.{identifier_type}",
                identifier_value
            ])
            
            result = cursor.fetchone()
            if result:
                # If exact match found, append (uuid, empty list)
                results.append((result['id'], []))
                continue
                
            # If no exact match, try fuzzy title match
            cursor.execute("""
                SELECT id, title, identifiers
                FROM sources
                WHERE type = ? AND 
                      LOWER(title) LIKE ?
            """, [
                type_,
                f"%{title.lower()}%"
            ])
            
            potential_matches = [
                {
                    'id': row['id'],
                    'title': row['title'],
                    'identifiers': json.loads(row['identifiers'])
                }
                for row in cursor.fetchall()
            ]
            
            # Append (None, potential_matches)
            results.append((None, potential_matches))
    
    return results

def get_sources_details(uuids: List[str], db_path: Path) -> List[Dict[str, Any]]:
    """
    Get complete information about multiple sources by their UUIDs.
    
    Args:
        uuids: List of source UUIDs
        db_path: Path to SQLite database
        
    Returns:
        List of dictionaries, each containing source information:
        - Basic info (id, title, type, status, identifiers)
        - Notes (list of {title, content, created_at})
        - Entity links (list of {entity_name, relation_type, notes})
        
    Raises:
        ValueError: If any source UUID is not found
    """
    if not uuids:
        return []
    
    with SQLiteConnection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get basic source info for all UUIDs in one query
        placeholders = ','.join('?' * len(uuids))
        cursor.execute(f"""
            SELECT id, title, type, status, identifiers
            FROM sources
            WHERE id IN ({placeholders})
        """, uuids)
        
        sources = cursor.fetchall()
        if len(sources) != len(uuids):
            found_ids = {source['id'] for source in sources}
            missing_ids = [uuid for uuid in uuids if uuid not in found_ids]
            raise ValueError(f"Sources not found for UUIDs: {', '.join(missing_ids)}")
        
        # Initialize results dictionary
        results = []
        for source in sources:
            source_data = {
                'id': source['id'],
                'title': source['title'],
                'type': source['type'],
                'status': source['status'],
                'identifiers': json.loads(source['identifiers'])
            }
            results.append(source_data)
        
        # Get notes for all sources in one query
        cursor.execute(f"""
            SELECT source_id, note_title, content, created_at
            FROM source_notes
            WHERE source_id IN ({placeholders})
            ORDER BY created_at DESC
        """, uuids)
        
        # Group notes by source_id
        notes_by_source = {}
        for row in cursor.fetchall():
            source_id = row['source_id']
            if source_id not in notes_by_source:
                notes_by_source[source_id] = []
            notes_by_source[source_id].append({
                'title': row['note_title'],
                'content': row['content'],
                'created_at': row['created_at']
            })
        
        # Get entity links for all sources in one query
        cursor.execute(f"""
            SELECT source_id, entity_name, relation_type, notes
            FROM source_entity_links
            WHERE source_id IN ({placeholders})
        """, uuids)
        
        # Group entity links by source_id
        links_by_source = {}
        for row in cursor.fetchall():
            source_id = row['source_id']
            if source_id not in links_by_source:
                links_by_source[source_id] = []
            links_by_source[source_id].append({
                'entity_name': row['entity_name'],
                'relation_type': row['relation_type'],
                'notes': row['notes']
            })
        
        # Add notes and entity links to each source
        for source_data in results:
            source_id = source_data['id']
            source_data['notes'] = notes_by_source.get(source_id, [])
            source_data['entity_links'] = links_by_source.get(source_id, [])
        
        return results





# Original Tools of Sqlite DB

@mcp.tool()
def read_query(
    query: str,
    params: Optional[List[Any]] = None,
    fetch_all: bool = True,
    row_limit: int = 1000
) -> List[Dict[str, Any]]:
    """Execute a query on the Literature database.
    
    Args:
        query: SELECT SQL query to execute
        params: Optional list of parameters for the query
        fetch_all: If True, fetches all results. If False, fetches one row.
        row_limit: Maximum number of rows to return (default 1000)
    
    Returns:
        List of dictionaries containing the query results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    query = query.strip()
    if query.endswith(';'):
        query = query[:-1].strip()
    
    def contains_multiple_statements(sql: str) -> bool:
        in_single_quote = False
        in_double_quote = False
        for char in sql:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == ';' and not in_single_quote and not in_double_quote:
                return True
        return False
    
    if contains_multiple_statements(query):
        raise ValueError("Multiple SQL statements are not allowed")
    
    query_lower = query.lower()
    if not any(query_lower.startswith(prefix) for prefix in ('select', 'with')):
        raise ValueError("Only SELECT queries (including WITH clauses) are allowed for safety")
    
    params = params or []
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            if 'limit' not in query_lower:
                query = f"{query} LIMIT {row_limit}"
            
            cursor.execute(query, params)
            
            if fetch_all:
                results = cursor.fetchall()
            else:
                results = [cursor.fetchone()]
                
            return [dict(row) for row in results if row is not None]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def list_tables() -> List[str]:
    """List all tables in the Literature database.
    
    Returns:
        List of table names in the database
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                ORDER BY name
            """)
            
            return [row['name'] for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def describe_table(table_name: str) -> List[Dict[str, str]]:
    """Get detailed information about a table's schema.
    
    Args:
        table_name: Name of the table to describe
        
    Returns:
        List of dictionaries containing column information:
        - name: Column name
        - type: Column data type
        - notnull: Whether the column can contain NULL values
        - dflt_value: Default value for the column
        - pk: Whether the column is part of the primary key
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        
        try:
            # Verify table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, [table_name])
            
            if not cursor.fetchone():
                raise ValueError(f"Table '{table_name}' does not exist")
            
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            return [dict(row) for row in columns]
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def get_table_stats(table_name: str) -> Dict[str, Any]:
    """Get statistics about a table, including row count and storage info.
    
    Args:
        table_name: Name of the table to analyze
        
    Returns:
        Dictionary containing table statistics
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Verify table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, [table_name])
            
            if not cursor.fetchone():
                raise ValueError(f"Table '{table_name}' does not exist")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            row_count = cursor.fetchone()['count']
            
            # Get storage info
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = len(cursor.fetchall())
            
            return {
                "table_name": table_name,
                "row_count": row_count,
                "column_count": columns,
                "page_size": page_size
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def get_database_info() -> Dict[str, Any]:
    """Get overall database information and statistics.
    
    Returns:
        Dictionary containing database statistics and information
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get database size
            db_size = os.path.getsize(DB_PATH)
            
            # Get table counts
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            table_count = cursor.fetchone()['count']
            
            # Get SQLite version
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()[0]
            
            # Get table statistics
            tables = {}
            cursor.execute("""
                SELECT name 
                FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            
            for row in cursor.fetchall():
                table_name = row['name']
                cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                tables[table_name] = cursor.fetchone()['count']
            
            return {
                "database_size_bytes": db_size,
                "table_count": table_count,
                "sqlite_version": version,
                "table_row_counts": tables,
                "path": str(DB_PATH)
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def vacuum_database() -> Dict[str, Any]:
    """Optimize the database by running VACUUM command.
    This rebuilds the database file to reclaim unused space.
    
    Returns:
        Dictionary containing the operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get size before vacuum
            size_before = os.path.getsize(DB_PATH)
            
            # Run vacuum
            cursor.execute("VACUUM")
            
            # Get size after vacuum
            size_after = os.path.getsize(DB_PATH)
            
            return {
                "status": "success",
                "size_before_bytes": size_before,
                "size_after_bytes": size_after,
                "space_saved_bytes": size_before - size_after
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")





# Source Management Tools:

@mcp.tool()
def add_sources(
    sources: List[Tuple[str, str, str, str, Optional[Dict[str, str]]]]  # [(title, type, identifier_type, identifier_value, initial_note)]
) -> List[Dict[str, Any]]:
    """Add multiple new sources with duplicate checking in a single transaction.
    
    Args:
        sources: List of tuples, each containing:
            - title: Source title
            - type: Source type (paper, webpage, book, video, blog)
            - identifier_type: Type of identifier
            - identifier_value: Value of the identifier
            - initial_note: Optional dict with 'title' and 'content' keys
    
    Returns:
        List of dictionaries containing operation results for each source:
        - On success: {"status": "success", "source": source_details}
        - On duplicate: {"status": "error", "message": "...", "existing_source": details}
        - On potential duplicate: {"status": "error", "message": "...", "matches": [...]}
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not sources:
        return []
    
    # Prepare search inputs for bulk search
    search_inputs = [
        (title, type_, id_type, id_value)
        for title, type_, id_type, id_value, _ in sources
    ]
    
    # Bulk search for existing sources
    search_results = search_sources(search_inputs, DB_PATH)
    
    # Process results and prepare new sources
    results = []
    sources_to_add = []
    notes_to_add = []
    
    for (title, type_, id_type, id_value, initial_note), (uuid_str, matches) in zip(sources, search_results):
        if uuid_str:
            # Source already exists
            results.append({
                "status": "error",
                "message": "Source already exists",
                "existing_source": get_sources_details(uuid_str, DB_PATH)
            })
            continue
            
        if matches:
            # Potential duplicates found
            results.append({
                "status": "error",
                "message": "Potential duplicates found. Please verify or use add_identifier if these are the same source.",
                "matches": matches
            })
            continue
        
        # New source to add - using UUID module explicitly
        new_id = str(uuid.uuid4())  # Generate new UUID using the imported module
        identifiers = {id_type: id_value}
        
        sources_to_add.append({
            'id': new_id,
            'title': title,
            'type': type_,
            'identifiers': json.dumps(identifiers)
        })
        
        if initial_note:
            if not all(k in initial_note for k in ('title', 'content')):
                results.append({
                    "status": "error",
                    "message": f"Invalid initial note format for source '{title}'"
                })
                continue
                
            notes_to_add.append({
                'source_id': new_id,
                'note_title': initial_note['title'],
                'content': initial_note['content']
            })
        
        # Add placeholder for success result to be filled after insertion
        results.append({
            "status": "pending",
            "source_id": new_id
        })
    
    # If we have any sources to add, do it in a single transaction
    if sources_to_add:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                # Add all new sources
                cursor.executemany("""
                    INSERT INTO sources (id, title, type, identifiers)
                    VALUES (:id, :title, :type, :identifiers)
                """, sources_to_add)
                
                # Add all initial notes
                if notes_to_add:
                    cursor.executemany("""
                        INSERT INTO source_notes (source_id, note_title, content)
                        VALUES (:source_id, :note_title, :content)
                    """, notes_to_add)
                
                conn.commit()
                
                # Get full details for all added sources
                added_source_ids = [s['id'] for s in sources_to_add]
                added_sources = get_sources_details(added_source_ids, DB_PATH)
                
                # Update results with full source details
                for i, result in enumerate(results):
                    if result.get("status") == "pending":
                        source_id = result["source_id"]
                        source_details = next(s for s in added_sources if s['id'] == source_id)
                        results[i] = {
                            "status": "success",
                            "source": source_details
                        }
                
            except sqlite3.Error as e:
                conn.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    return results

@mcp.tool()
def add_notes(
    source_notes: List[Tuple[str, str, str, str, str, str]]  # [(title, type, identifier_type, identifier_value, note_title, note_content)]
) -> List[Dict[str, Any]]:
    """Add notes to multiple sources in a single transaction.
    
    Args:
        source_notes: List of tuples, each containing:
            - title: Source title
            - type: Source type
            - identifier_type: Type of identifier
            - identifier_value: Value of the identifier
            - note_title: Title for the new note
            - note_content: Content of the note
    
    Returns:
        List of dictionaries containing operation results for each note addition:
        - On success: {"status": "success", "source": source_details}
        - On source not found: {"status": "error", "message": "Source not found"}
        - On ambiguous source: {"status": "error", "message": "...", "matches": [...]}
        - On duplicate note: {"status": "error", "message": "Note with this title already exists for this source"}
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not source_notes:
        return []
    
    # Prepare search inputs for bulk source lookup
    search_inputs = [
        (title, type_, id_type, id_value)
        for title, type_, id_type, id_value, _, _ in source_notes
    ]
    
    # Bulk search for sources
    search_results = search_sources(search_inputs, DB_PATH)
    
    # Process results and prepare notes
    results = []
    notes_to_add = []
    source_ids = []
    
    for (title, type_, id_type, id_value, note_title, note_content), (uuid, matches) in zip(source_notes, search_results):
        if not uuid:
            if matches:
                results.append({
                    "status": "error",
                    "message": "Multiple potential matches found. Please verify the source.",
                    "matches": matches
                })
            else:
                results.append({
                    "status": "error",
                    "message": "Source not found"
                })
            continue
        
        notes_to_add.append({
            'source_id': uuid,
            'note_title': note_title,
            'content': note_content
        })
        source_ids.append(uuid)
        results.append({
            "status": "pending",
            "source_id": uuid
        })
    
    if notes_to_add:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                # Check for duplicate note titles
                placeholders = ','.join('?' * len(notes_to_add))
                cursor.execute(f"""
                    SELECT source_id, note_title
                    FROM source_notes
                    WHERE (source_id, note_title) IN 
                    ({','.join(f'(?,?)' for _ in notes_to_add)})
                """, [
                    val for note in notes_to_add 
                    for val in (note['source_id'], note['note_title'])
                ])
                
                # Track which notes already exist
                existing_notes = {
                    (row['source_id'], row['note_title'])
                    for row in cursor.fetchall()
                }
                
                # Filter out notes that already exist
                filtered_notes = []
                for i, note in enumerate(notes_to_add):
                    if (note['source_id'], note['note_title']) in existing_notes:
                        results[i] = {
                            "status": "error",
                            "message": "Note with this title already exists for this source"
                        }
                    else:
                        filtered_notes.append(note)
                
                # Add new notes
                if filtered_notes:
                    cursor.executemany("""
                        INSERT INTO source_notes (source_id, note_title, content)
                        VALUES (:source_id, :note_title, :content)
                    """, filtered_notes)
                    
                    conn.commit()
                    
                    # Get updated source details
                    source_details = get_sources_details(list(set(source_ids)), DB_PATH)
                    
                    # Update success results
                    for i, result in enumerate(results):
                        if result.get("status") == "pending":
                            source_id = result["source_id"]
                            source_detail = next(s for s in source_details if s['id'] == source_id)
                            results[i] = {
                                "status": "success",
                                "source": source_detail
                            }
                
            except sqlite3.Error as e:
                conn.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    return results

@mcp.tool()
def update_status(
    source_status: List[Tuple[str, str, str, str, str]]  # [(title, type, identifier_type, identifier_value, new_status)]
) -> List[Dict[str, Any]]:
    """Update status for multiple sources in a single transaction.
    
    Args:
        source_status: List of tuples, each containing:
            - title: Source title
            - type: Source type
            - identifier_type: Type of identifier
            - identifier_value: Value of the identifier
            - new_status: New status value
    
    Returns:
        List of dictionaries containing operation results for each status update:
        - On success: {"status": "success", "source": source_details}
        - On source not found: {"status": "error", "message": "Source not found"}
        - On ambiguous source: {"status": "error", "message": "...", "matches": [...]}
        - On invalid status: {"status": "error", "message": "Invalid status. Must be one of: ..."}
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not source_status:
        return []
    
    # Validate all status values first
    for _, _, _, _, status in source_status:
        if status not in SourceStatus.VALID_STATUS:
            raise ValueError(f"Invalid status. Must be one of: {SourceStatus.VALID_STATUS}")
    
    # Prepare search inputs for bulk source lookup
    search_inputs = [
        (title, type_, id_type, id_value)
        for title, type_, id_type, id_value, _ in source_status
    ]
    
    # Bulk search for sources
    search_results = search_sources(search_inputs, DB_PATH)
    
    # Process results and prepare updates
    results = []
    updates_to_make = []
    source_ids = []
    
    for (title, type_, id_type, id_value, new_status), (uuid, matches) in zip(source_status, search_results):
        if not uuid:
            if matches:
                results.append({
                    "status": "error",
                    "message": "Multiple potential matches found. Please verify the source.",
                    "matches": matches
                })
            else:
                results.append({
                    "status": "error",
                    "message": "Source not found"
                })
            continue
        
        updates_to_make.append({
            'id': uuid,
            'status': new_status
        })
        source_ids.append(uuid)
        results.append({
            "status": "pending",
            "source_id": uuid
        })
    
    if updates_to_make:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                # Update all statuses
                cursor.executemany("""
                    UPDATE sources 
                    SET status = :status
                    WHERE id = :id
                """, updates_to_make)
                
                conn.commit()
                
                # Get updated source details
                source_details = get_sources_details(source_ids, DB_PATH)
                
                # Update results
                for i, result in enumerate(results):
                    if result.get("status") == "pending":
                        source_id = result["source_id"]
                        source_detail = next(s for s in source_details if s['id'] == source_id)
                        results[i] = {
                            "status": "success",
                            "source": source_detail
                        }
                
            except sqlite3.Error as e:
                conn.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    return results

@mcp.tool()
def add_identifiers(
    source_identifiers: List[Tuple[str, str, str, str, str, str]]  # [(title, type, current_id_type, current_id_value, new_id_type, new_id_value)]
) -> List[Dict[str, Any]]:
    """Add new identifiers to multiple sources in a single transaction.
    
    Args:
        source_identifiers: List of tuples, each containing:
            - title: Source title
            - type: Source type
            - current_identifier_type: Current identifier type
            - current_identifier_value: Current identifier value
            - new_identifier_type: New identifier type to add
            - new_identifier_value: New identifier value to add
    
    Returns:
        List of dictionaries containing operation results for each identifier addition:
        - On success: {"status": "success", "source": source_details}
        - On source not found: {"status": "error", "message": "Source not found"}
        - On ambiguous source: {"status": "error", "message": "...", "matches": [...]}
        - On duplicate identifier: {"status": "error", "message": "...", "existing_source": details}
        - On invalid identifier type: {"status": "error", "message": "Invalid identifier type. Must be one of: ..."}
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not source_identifiers:
        return []
    
    # Validate all new identifier types first
    for _, _, _, _, new_type, _ in source_identifiers:
        if new_type not in SourceIdentifiers.VALID_TYPES:
            raise ValueError(f"Invalid new identifier type. Must be one of: {SourceIdentifiers.VALID_TYPES}")
    
    # Prepare search inputs for bulk source lookup
    search_inputs = [
        (title, type_, current_type, current_value)
        for title, type_, current_type, current_value, _, _ in source_identifiers
    ]
    
    # Bulk search for sources
    search_results = search_sources(search_inputs, DB_PATH)
    
    # Process results and prepare updates
    results = []
    updates_to_make = []
    source_ids = []
    
    # First pass: collect all sources and validate new identifiers don't exist
    new_identifier_checks = [
        (type_, new_type, new_value)
        for _, type_, _, _, new_type, new_value in source_identifiers
    ]
    new_id_search_results = search_sources([
        (f"Check {i}", type_, id_type, id_value)
        for i, (type_, id_type, id_value) in enumerate(new_identifier_checks)
    ], DB_PATH)
    
    # Create mapping of new identifiers to existing sources
    existing_new_ids = {
        (type_, id_type, id_value): uuid
        for (_, type_, _, _, id_type, id_value), (uuid, _) 
        in zip(source_identifiers, new_id_search_results)
        if uuid
    }
    
    for (title, type_, current_type, current_value, new_type, new_value), (uuid, matches) in zip(source_identifiers, search_results):
        if not uuid:
            if matches:
                results.append({
                    "status": "error",
                    "message": "Multiple potential matches found. Please verify the source.",
                    "matches": matches
                })
            else:
                results.append({
                    "status": "error",
                    "message": "Source not found"
                })
            continue
        
        # Check if new identifier exists on a different source
        existing_source = existing_new_ids.get((type_, new_type, new_value))
        if existing_source and existing_source != uuid:
            results.append({
                "status": "error",
                "message": "New identifier already exists on a different source",
                "existing_source": get_sources_details(existing_source, DB_PATH)
            })
            continue
        
        updates_to_make.append({
            'id': uuid,
            'new_type': new_type,
            'new_value': new_value
        })
        source_ids.append(uuid)
        results.append({
            "status": "pending",
            "source_id": uuid
        })
    
    if updates_to_make:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                # Update identifiers one by one (since we need to merge JSON)
                for update in updates_to_make:
                    cursor.execute("""
                        UPDATE sources 
                        SET identifiers = json_set(
                            identifiers,
                            :path,
                            :value
                        )
                        WHERE id = :id
                    """, {
                        'id': update['id'],
                        'path': f"$.{update['new_type']}",
                        'value': update['new_value']
                    })
                
                conn.commit()
                
                # Get updated source details
                source_details = get_sources_details(source_ids, DB_PATH)
                
                # Update results
                for i, result in enumerate(results):
                    if result.get("status") == "pending":
                        source_id = result["source_id"]
                        source_detail = next(s for s in source_details if s['id'] == source_id)
                        results[i] = {
                            "status": "success",
                            "source": source_detail
                        }
                
            except sqlite3.Error as e:
                conn.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    return results




# Entity Management Tools:

@mcp.tool()
def link_to_entities(
    source_entity_links: List[Tuple[str, str, str, str, str, str, Optional[str]]]
) -> List[Dict[str, Any]]:
    """Link multiple sources to entities in the knowledge graph.
    
    Args:
        source_entity_links: List of tuples, each containing:
            - title: Source title
            - type: Source type (paper, webpage, book, video, blog)
            - identifier_type: Type of identifier (semantic_scholar, arxiv, doi, isbn, url)
            - identifier_value: Value of the identifier
            - entity_name: Name of the entity to link to
            - relation_type: Type of relationship (discusses, introduces, extends, evaluates, applies, critiques)
            - notes: Optional notes explaining the relationship
    
    Returns:
        List of operation results, each containing:
        {
            "status": "success" | "error",
            "message": Error message if status is "error",
            "source": Source details if status is "success",
            "matches": List of potential matches if ambiguous source found
        }
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not source_entity_links:
        return []
    
    # Validate relation types first
    for _, _, _, _, _, relation_type, _ in source_entity_links:
        if relation_type not in EntityRelations.VALID_TYPES:
            raise ValueError(f"Invalid relation type. Must be one of: {EntityRelations.VALID_TYPES}")
    
    # Prepare search inputs for bulk source lookup
    search_inputs = [
        (title, type_, id_type, id_value)
        for title, type_, id_type, id_value, _, _, _ in source_entity_links
    ]
    
    # Bulk search for sources
    search_results = search_sources(search_inputs, DB_PATH)
    
    # Process results and prepare links
    results = []
    links_to_add = []
    source_ids = []
    
    for (title, type_, id_type, id_value, entity_name, relation_type, notes), (uuid, matches) in zip(source_entity_links, search_results):
        if not uuid:
            if matches:
                results.append({
                    "status": "error",
                    "message": "Multiple potential matches found. Please verify the source.",
                    "matches": matches
                })
            else:
                results.append({
                    "status": "error",
                    "message": "Source not found"
                })
            continue
        
        links_to_add.append({
            'source_id': uuid,
            'entity_name': entity_name,
            'relation_type': relation_type,
            'notes': notes
        })
        source_ids.append(uuid)
        results.append({
            "status": "pending",
            "source_id": uuid
        })
    
    if links_to_add:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                # Check for existing links
                placeholders = ','.join('(?,?)' for _ in links_to_add)
                cursor.execute(f"""
                    SELECT source_id, entity_name
                    FROM source_entity_links
                    WHERE (source_id, entity_name) IN ({placeholders})
                """, [
                    val for link in links_to_add 
                    for val in (link['source_id'], link['entity_name'])
                ])
                
                # Track existing links
                existing_links = {
                    (row['source_id'], row['entity_name'])
                    for row in cursor.fetchall()
                }
                
                # Filter out existing links
                filtered_links = []
                for i, link in enumerate(links_to_add):
                    if (link['source_id'], link['entity_name']) in existing_links:
                        results[i] = {
                            "status": "error",
                            "message": "Link already exists between this source and entity"
                        }
                    else:
                        filtered_links.append(link)
                
                # Add new links
                if filtered_links:
                    cursor.executemany("""
                        INSERT INTO source_entity_links 
                        (source_id, entity_name, relation_type, notes)
                        VALUES (:source_id, :entity_name, :relation_type, :notes)
                    """, filtered_links)
                    
                    conn.commit()
                    
                    # Get updated source details
                    source_details = get_sources_details(list(set(source_ids)), DB_PATH)
                    
                    # Update success results
                    for i, result in enumerate(results):
                        if result.get("status") == "pending":
                            source_id = result["source_id"]
                            source_detail = next(s for s in source_details if s['id'] == source_id)
                            results[i] = {
                                "status": "success",
                                "source": source_detail
                            }
                
            except sqlite3.Error as e:
                conn.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    return results

@mcp.tool()
def get_source_entities(
    sources: List[Tuple[str, str, str, str]]
) -> List[Dict[str, Any]]:
    """Get all entities linked to multiple sources.
    
    Args:
        sources: List of tuples, each containing:
            - title: Source title
            - type: Source type
            - identifier_type: Type of identifier
            - identifier_value: Value of the identifier
    
    Returns:
        List of operation results, each containing:
        {
            "status": "success" | "error",
            "message": Error message if status is "error",
            "source": Source details including linked entities if status is "success",
            "matches": List of potential matches if ambiguous source found
        }
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not sources:
        return []
    
    # Bulk search for sources
    search_results = search_sources(sources, DB_PATH)
    
    # Process results
    results = []
    source_ids = []
    
    for (title, type_, id_type, id_value), (uuid, matches) in zip(sources, search_results):
        if not uuid:
            if matches:
                results.append({
                    "status": "error",
                    "message": "Multiple potential matches found. Please verify the source.",
                    "matches": matches
                })
            else:
                results.append({
                    "status": "error",
                    "message": "Source not found"
                })
            continue
        
        source_ids.append(uuid)
        results.append({
            "status": "pending",
            "source_id": uuid
        })
    
    if source_ids:
        try:
            # Get source details with entity links
            source_details = get_sources_details(source_ids, DB_PATH)
            
            # Update results
            for i, result in enumerate(results):
                if result.get("status") == "pending":
                    source_id = result["source_id"]
                    source_detail = next(s for s in source_details if s['id'] == source_id)
                    results[i] = {
                        "status": "success",
                        "source": source_detail
                    }
                    
        except ValueError as e:
            # Handle any errors from get_sources_details
            for i, result in enumerate(results):
                if result.get("status") == "pending":
                    results[i] = {
                        "status": "error",
                        "message": str(e)
                    }
    
    return results

@mcp.tool()
def update_entity_links(
    source_entity_updates: List[Tuple[str, str, str, str, str, Optional[str], Optional[str]]]
) -> List[Dict[str, Any]]:
    """Update existing links between sources and entities.
    
    Args:
        source_entity_updates: List of tuples, each containing:
            - title: Source title
            - type: Source type
            - identifier_type: Type of identifier
            - identifier_value: Value of the identifier
            - entity_name: Name of the entity
            - relation_type: Optional new relationship type
            - notes: Optional new notes
            
            Note: At least one of relation_type or notes must be provided in each tuple
    
    Returns:
        List of operation results, each containing:
        {
            "status": "success" | "error",
            "message": Error message if status is "error",
            "source": Source details if status is "success",
            "matches": List of potential matches if ambiguous source found
        }
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not source_entity_updates:
        return []
    
    # Validate updates first
    for _, _, _, _, _, relation_type, notes in source_entity_updates:
        if relation_type and relation_type not in EntityRelations.VALID_TYPES:
            raise ValueError(f"Invalid relation type. Must be one of: {EntityRelations.VALID_TYPES}")
        if not relation_type and notes is None:
            raise ValueError("At least one of relation_type or notes must be provided")
    
    # Prepare search inputs for bulk source lookup
    search_inputs = [
        (title, type_, id_type, id_value)
        for title, type_, id_type, id_value, _, _, _ in source_entity_updates
    ]
    
    # Bulk search for sources
    search_results = search_sources(search_inputs, DB_PATH)
    
    # Process results and prepare updates
    results = []
    updates_to_make = []
    source_ids = []
    
    for (title, type_, id_type, id_value, entity_name, relation_type, notes), (uuid, matches) in zip(source_entity_updates, search_results):
        if not uuid:
            if matches:
                results.append({
                    "status": "error",
                    "message": "Multiple potential matches found. Please verify the source.",
                    "matches": matches
                })
            else:
                results.append({
                    "status": "error",
                    "message": "Source not found"
                })
            continue
        
        updates_to_make.append({
            'source_id': uuid,
            'entity_name': entity_name,
            'relation_type': relation_type,
            'notes': notes
        })
        source_ids.append(uuid)
        results.append({
            "status": "pending",
            "source_id": uuid
        })
    
    if updates_to_make:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                # Update each link
                for update in updates_to_make:
                    updates = []
                    params = []
                    
                    if update['relation_type']:
                        updates.append("relation_type = ?")
                        params.append(update['relation_type'])
                    if update['notes'] is not None:
                        updates.append("notes = ?")
                        params.append(update['notes'])
                        
                    params.extend([update['source_id'], update['entity_name']])
                    
                    query = f"""
                        UPDATE source_entity_links 
                        SET {', '.join(updates)}
                        WHERE source_id = ? AND entity_name = ?
                    """
                    
                    cursor.execute(query, params)
                    if cursor.rowcount == 0:
                        # Find index of this update in results
                        idx = next(i for i, r in enumerate(results) 
                                 if r.get("status") == "pending" and 
                                 r.get("source_id") == update['source_id'])
                        results[idx] = {
                            "status": "error",
                            "message": "No link found between this source and entity"
                        }
                
                conn.commit()
                
                # Get updated source details
                source_details = get_sources_details(list(set(source_ids)), DB_PATH)
                
                # Update success results
                for i, result in enumerate(results):
                    if result.get("status") == "pending":
                        source_id = result["source_id"]
                        source_detail = next(s for s in source_details if s['id'] == source_id)
                        results[i] = {
                            "status": "success",
                            "source": source_detail
                        }
                
            except sqlite3.Error as e:
                conn.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    return results

@mcp.tool()
def remove_entity_links(
    source_entity_pairs: List[Tuple[str, str, str, str, str]]
) -> List[Dict[str, Any]]:
    """Remove links between sources and entities.
    
    Args:
        source_entity_pairs: List of tuples, each containing:
            - title: Source title
            - type: Source type
            - identifier_type: Type of identifier
            - identifier_value: Value of the identifier
            - entity_name: Name of the entity
    
    Returns:
        List of operation results, each containing:
        {
            "status": "success" | "error",
            "message": Error message if status is "error",
            "source": Source details if status is "success",
            "matches": List of potential matches if ambiguous source found
        }
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not source_entity_pairs:
        return []
    
    # Prepare search inputs for bulk source lookup
    search_inputs = [
        (title, type_, id_type, id_value)
        for title, type_, id_type, id_value, _ in source_entity_pairs
    ]
    
    # Bulk search for sources
    search_results = search_sources(search_inputs, DB_PATH)
    
    # Process results and prepare deletions
    results = []
    links_to_remove = []
    source_ids = []
    
    for (title, type_, id_type, id_value, entity_name), (uuid, matches) in zip(source_entity_pairs, search_results):
        if not uuid:
            if matches:
                results.append({
                    "status": "error",
                    "message": "Multiple potential matches found. Please verify the source.",
                    "matches": matches
                })
            else:
                results.append({
                    "status": "error",
                    "message": "Source not found"
                })
            continue
        
        links_to_remove.append({
            'source_id': uuid,
            'entity_name': entity_name
        })
        source_ids.append(uuid)
        results.append({
            "status": "pending",
            "source_id": uuid
        })
    
    if links_to_remove:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                # Remove all links in one query
                placeholders = ','.join('(?,?)' for _ in links_to_remove)
                cursor.execute(f"""
                    DELETE FROM source_entity_links
                    WHERE (source_id, entity_name) IN ({placeholders})
                """, [
                    val for link in links_to_remove 
                    for val in (link['source_id'], link['entity_name'])
                ])
                
                # Track which links were actually removed
                removed_count = cursor.rowcount
                if removed_count < len(links_to_remove):
                    # Some links weren't found - need to check which ones
                    cursor.execute(f"""
                        SELECT source_id, entity_name
                        FROM source_entity_links
                        WHERE (source_id, entity_name) IN ({placeholders})
                    """, [
                        val for link in links_to_remove 
                        for val in (link['source_id'], link['entity_name'])
                    ])
                    
                    existing_links = {
                        (row['source_id'], row['entity_name'])
                        for row in cursor.fetchall()
                    }
                    
                    # Update results for non-existent links
                    for i, link in enumerate(links_to_remove):
                        if (link['source_id'], link['entity_name']) not in existing_links:
                            idx = next(j for j, r in enumerate(results) 
                                     if r.get("status") == "pending" and 
                                     r.get("source_id") == link['source_id'])
                            results[idx] = {
                                "status": "error",
                                "message": "No link found between this source and entity"
                            }
                
                conn.commit()
                
                # Get updated source details
                source_details = get_sources_details(list(set(source_ids)), DB_PATH)
                
                # Update success results
                for i, result in enumerate(results):
                    if result.get("status") == "pending":
                        source_id = result["source_id"]
                        source_detail = next(s for s in source_details if s['id'] == source_id)
                        results[i] = {
                            "status": "success",
                            "source": source_detail
                        }
                
            except sqlite3.Error as e:
                conn.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    return results

@mcp.tool()
def get_entity_sources(
    entity_filters: List[Tuple[str, Optional[str], Optional[str]]]
) -> List[Dict[str, Any]]:
    """Get all sources linked to specific entities with optional filtering.
    
    Args:
        entity_filters: List of tuples, each containing:
            - entity_name: Name of the entity
            - type_filter: Optional filter by source type (paper, webpage, book, video, blog)
            - relation_filter: Optional filter by relation type (discusses, introduces, extends, evaluates, applies, critiques)
    
    Returns:
        List of operation results, each containing:
        {
            "status": "success" | "error",
            "message": Error message if status is "error",
            "entity": Entity name,
            "filters_applied": {
                "type": Applied type filter,
                "relation": Applied relation filter
            },
            "sources": List of source details if status is "success"
        }
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")
    
    if not entity_filters:
        return []
    
    # Validate filters first
    for _, type_filter, relation_filter in entity_filters:
        if type_filter and type_filter not in SourceTypes.VALID_TYPES:
            raise ValueError(f"Invalid type filter. Must be one of: {SourceTypes.VALID_TYPES}")
        if relation_filter and relation_filter not in EntityRelations.VALID_TYPES:
            raise ValueError(f"Invalid relation filter. Must be one of: {EntityRelations.VALID_TYPES}")
    
    results = []
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            for entity_name, type_filter, relation_filter in entity_filters:
                query = """
                    SELECT DISTINCT s.id
                    FROM sources s
                    JOIN source_entity_links l ON s.id = l.source_id
                    WHERE l.entity_name = ?
                """
                params = [entity_name]
                
                if type_filter:
                    query += " AND s.type = ?"
                    params.append(type_filter)
                    
                if relation_filter:
                    query += " AND l.relation_type = ?"
                    params.append(relation_filter)
                
                cursor.execute(query, params)
                source_ids = [row['id'] for row in cursor.fetchall()]
                
                if source_ids:
                    source_details = get_sources_details(source_ids, DB_PATH)
                    results.append({
                        "status": "success",
                        "entity": entity_name,
                        "filters_applied": {
                            "type": type_filter,
                            "relation": relation_filter
                        },
                        "sources": source_details
                    })
                else:
                    results.append({
                        "status": "success",
                        "entity": entity_name,
                        "filters_applied": {
                            "type": type_filter,
                            "relation": relation_filter
                        },
                        "sources": []
                    })
                
        except sqlite3.Error as e:
            raise ValueError(f"Database error: {str(e)}")
    
    return results





if __name__ == "__main__":
    # Start the FastMCP server
    mcp.run()