from pathlib import Path
import sqlite3
import os
import json
from typing import List, Dict, Any, Optional, Tuple, Set
from fastmcp import FastMCP
from datetime import datetime
import re

class LiteratureIdentifier:
    """Handles flexible paper identifiers for different sources"""
    VALID_SOURCES = {'semanticscholar', 'arxiv', 'doi', 'custom'}
    VALID_STATUSES = {'unread', 'reading', 'completed', 'archived'}
    VALID_ENTITY_RELATIONS = {
        'discusses', 'introduces', 'extends', 'evaluates', 'applies', 'critiques'
    }
    
    def __init__(self, id_str: str):
        self.source, self.id = self._parse_id(id_str)
        
    def _parse_id(self, id_str: str) -> Tuple[str, str]:
        """Parse ID format: "source:id" e.g., "semanticscholar:649def34", "arxiv:2106.15928"
        Default to "custom:id" if no source specified
        """
        if ':' in id_str:
            source, id_part = id_str.split(':', 1)
            source = source.lower()
            if source not in self.VALID_SOURCES:
                raise ValueError(f"Invalid source '{source}'. Valid sources: {', '.join(self.VALID_SOURCES)}")
            return source, id_part
        return 'custom', id_str
        
    @property 
    def full_id(self) -> str:
        """Return the full identifier in source:id format"""
        return f"{self.source}:{self.id}"
    
    @classmethod
    def validate(cls, id_str: str) -> bool:
        """Validate if the given ID string is properly formatted"""
        try:
            cls(id_str)
            return True
        except ValueError:
            return False

# Initialize FastMCP server
mcp = FastMCP("Literature Manager")

# Path to Literature database - must be provided via SQLITE_DB_PATH environment variable
if 'SQLITE_DB_PATH' not in os.environ:
    raise ValueError("SQLITE_DB_PATH environment variable must be set")
DB_PATH = Path(os.environ['SQLITE_DB_PATH'])


class SQLiteConnection:
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

@mcp.tool()
def add_literature(
    id_str: str,
    importance: Optional[int] = 3,
    notes: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source_type: Optional[str] = None,
    source_url: Optional[str] = None
) -> Dict[str, Any]:
    """Add literature to the reading list.
    
    Args:
        id_str: Literature ID in format "source:id" (e.g., "arxiv:2106.15928")
        importance: Literature importance (1-5)
        notes: Initial notes
        tags: List of tags to apply
        source_type: Type of source ('paper', 'webpage', 'blog', 'video', 'book', 'custom')
        source_url: URL or direct link to the source
    
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    # Validate source_type if provided
    valid_source_types = {'paper', 'webpage', 'blog', 'video', 'book', 'custom'}
    if source_type and source_type not in valid_source_types:
        raise ValueError(f"Invalid source_type. Valid types: {', '.join(valid_source_types)}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Add to reading_list with source metadata
            cursor.execute("""
                INSERT INTO reading_list (
                    literature_id, source, source_type, source_url,
                    importance, notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                lit_id.full_id, lit_id.source, source_type, source_url,
                importance, notes
            ])
            
            # Add tags if provided
            if tags:
                cursor.executemany("""
                    INSERT INTO tags (literature_id, tag)
                    VALUES (?, ?)
                """, [(lit_id.full_id, tag) for tag in tags])
            
            conn.commit()
            return {"status": "success", "literature_id": lit_id.full_id}
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def update_literature_status(
    id_str: str,
    status: str,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Update literature reading status and optionally add notes.
    
    Args:
        id_str: Literature ID in format "source:id"
        status: New status ('unread', 'reading', 'completed', 'archived')
        notes: Additional notes to append (if provided)
    
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            updates = ["status = ?", "last_accessed = CURRENT_TIMESTAMP"]
            params = [status]
            
            if notes:
                updates.append("notes = COALESCE(notes || '\n\n', '') || ?")
                params.append(notes)
                
            query = f"""
                UPDATE reading_list 
                SET {', '.join(updates)}
                WHERE literature_id = ?
            """
            params.append(lit_id.full_id)
            
            cursor.execute(query, params)
            if cursor.rowcount == 0:
                raise ValueError(f"Literature {lit_id.full_id} not found in reading list")
                
            conn.commit()
            return {"status": "success", "literature_id": lit_id.full_id, "new_status": status}
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def update_literature_notes(
    id_str: str,
    content: str,
    entities: Optional[List[Dict[str, str]]] = None,
    append: bool = True,
    timestamp: bool = True
) -> Dict[str, Any]:
    """Update literature notes with optional entity linking.
    
    Args:
        id_str: Literature ID in format "source:id"
        content: Note content
        entities: Optional list of entities mentioned in these notes
                 Format: [{"name": "entity_name", 
                          "relation_type": "discusses",
                          "notes": "optional notes"}]
        append: If True, append to existing notes, if False, replace
        timestamp: If True, add timestamp to note
    
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get existing notes
            cursor.execute("SELECT notes FROM reading_list WHERE literature_id = ?", [lit_id.full_id])
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Literature {lit_id.full_id} not found")
                
            existing_notes = result['notes'] or ""
            
            # Format new note
            formatted_note = f"\n\n"
            if timestamp:
                formatted_note += f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}]\n"
            formatted_note += content
            
            # Update notes
            new_notes = existing_notes + formatted_note if append else formatted_note
            
            cursor.execute("""
                UPDATE reading_list 
                SET notes = ?, last_accessed = CURRENT_TIMESTAMP
                WHERE literature_id = ?
            """, [new_notes, lit_id.full_id])
            
            # Add entity links if provided
            if entities:
                for entity in entities:
                    # Validate relation type
                    relation_type = entity.get('relation_type', 'discusses')
                    if relation_type not in LiteratureIdentifier.VALID_ENTITY_RELATIONS:
                        raise ValueError(f"Invalid relation type '{relation_type}'. Valid types: {', '.join(LiteratureIdentifier.VALID_ENTITY_RELATIONS)}")
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO literature_entity_links
                        (literature_id, entity_name, relation_type, notes)
                        VALUES (?, ?, ?, ?)
                    """, [
                        lit_id.full_id,
                        entity['name'],
                        relation_type,
                        entity.get('notes')
                    ])
            
            conn.commit()
            return {
                "status": "success",
                "literature_id": lit_id.full_id,
                "entities_linked": len(entities) if entities else 0
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def link_paper_to_entity(
    id_str: str,
    entity_name: str,
    relation_type: str,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Create a link between a paper and an entity in the knowledge graph.
    
    Args:
        id_str: Literature ID in format "source:id" 
        entity_name: Name of the entity to link to
        relation_type: Type of relationship (discusses, introduces, extends, etc.)
        notes: Optional notes explaining the relationship
        
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    # Validate relation type
    if relation_type not in LiteratureIdentifier.VALID_ENTITY_RELATIONS:
        raise ValueError(f"Invalid relation type. Valid types: {', '.join(LiteratureIdentifier.VALID_ENTITY_RELATIONS)}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO literature_entity_links 
                (literature_id, entity_name, relation_type, notes)
                VALUES (?, ?, ?, ?)
            """, [lit_id.full_id, entity_name, relation_type, notes])
            
            conn.commit()
            return {
                "status": "success",
                "literature_id": lit_id.full_id,
                "entity": entity_name,
                "relation_type": relation_type
            }
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def get_paper_entities(id_str: str) -> Dict[str, Any]:
    """Get all entities linked to a paper.
    
    Args:
        id_str: Literature ID in format "source:id"
        
    Returns:
        Dictionary containing the paper's linked entities and their relationships
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT entity_name, relation_type, notes, created_at
                FROM literature_entity_links
                WHERE literature_id = ?
                ORDER BY created_at DESC
            """, [lit_id.full_id])
            
            return {
                "literature_id": lit_id.full_id,
                "entities": [dict(row) for row in cursor.fetchall()]
            }
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def get_entity_papers(
    entity_name: str,
    status: Optional[str] = None,
    min_importance: Optional[int] = None,
    sort_by: str = 'importance'  # 'importance', 'date', 'status'
) -> Dict[str, Any]:
    """Get all papers linked to an entity with filtering options.
    
    Args:
        entity_name: Name of the entity
        status: Optional filter by paper status
        min_importance: Optional minimum importance level (1-5)
        sort_by: Sort results by ('importance', 'date', 'status')
        
    Returns:
        Dictionary containing the entity's linked papers and their relationships
    """
    # Validate parameters
    if status and status not in LiteratureIdentifier.VALID_STATUSES:
        raise ValueError(f"Invalid status. Valid statuses: {', '.join(LiteratureIdentifier.VALID_STATUSES)}")
    
    if min_importance and not (1 <= min_importance <= 5):
        raise ValueError("min_importance must be between 1 and 5")
    
    if sort_by not in {'importance', 'date', 'status'}:
        raise ValueError("sort_by must be one of: 'importance', 'date', 'status'")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Build query with filters
            query = """
                SELECT l.literature_id, l.relation_type, l.notes,
                       r.status, r.importance, r.source, r.source_type, r.source_url,
                       r.added_date, r.last_accessed
                FROM literature_entity_links l
                JOIN reading_list r ON l.literature_id = r.literature_id
                WHERE l.entity_name = ?
            """
            params = [entity_name]
            
            if status:
                query += " AND r.status = ?"
                params.append(status)
            
            if min_importance:
                query += " AND r.importance >= ?"
                params.append(min_importance)
            
            # Add sorting
            query += {
                'importance': ' ORDER BY r.importance DESC, r.last_accessed DESC',
                'date': ' ORDER BY r.last_accessed DESC, r.importance DESC',
                'status': ' ORDER BY r.status, r.importance DESC'
            }[sort_by]
            
            cursor.execute(query, params)
            papers = [dict(row) for row in cursor.fetchall()]
            
            return {
                "entity": entity_name,
                "total_papers": len(papers),
                "filters_applied": {
                    "status": status,
                    "min_importance": min_importance,
                    "sort_by": sort_by
                },
                "papers": papers
            }
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def update_entity_link(
    id_str: str,
    entity_name: str,
    relation_type: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Update an existing link between a paper and an entity.
    
    Args:
        id_str: Literature ID in format "source:id"
        entity_name: Name of the entity
        relation_type: Optional new relationship type
        notes: Optional new notes
        
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    # Validate relation type if provided
    if relation_type and relation_type not in LiteratureIdentifier.VALID_ENTITY_RELATIONS:
        raise ValueError(f"Invalid relation type. Valid types: {', '.join(LiteratureIdentifier.VALID_ENTITY_RELATIONS)}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Build update query dynamically based on provided fields
            updates = []
            params = []
            
            if relation_type:
                updates.append("relation_type = ?")
                params.append(relation_type)
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)
                
            if not updates:
                raise ValueError("No updates provided")
                
            params.extend([lit_id.full_id, entity_name])
            
            query = f"""
                UPDATE literature_entity_links 
                SET {', '.join(updates)}
                WHERE literature_id = ? AND entity_name = ?
            """
            
            cursor.execute(query, params)
            if cursor.rowcount == 0:
                raise ValueError(f"No link found between {lit_id.full_id} and {entity_name}")
            
            conn.commit()
            return {
                "status": "success",
                "literature_id": lit_id.full_id,
                "entity": entity_name
            }
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def remove_entity_link(
    id_str: str,
    entity_name: str
) -> Dict[str, Any]:
    """Remove a link between a paper and an entity.
    
    Args:
        id_str: Literature ID in format "source:id"
        entity_name: Name of the entity
        
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                DELETE FROM literature_entity_links
                WHERE literature_id = ? AND entity_name = ?
            """, [lit_id.full_id, entity_name])
            
            if cursor.rowcount == 0:
                raise ValueError(f"No link found between {lit_id.full_id} and {entity_name}")
            
            conn.commit()
            return {
                "status": "success",
                "literature_id": lit_id.full_id,
                "entity": entity_name
            }
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

# Include original tools for completeness
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

@mcp.tool()
def backup_database(backup_path: str) -> Dict[str, Any]:
    """Create a backup of the database file.
    
    Args:
        backup_path: Path where to save the backup file
        
    Returns:
        Dictionary containing the backup operation results
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Literature database not found at: {DB_PATH}")
    
    backup_path = Path(backup_path)
    
    try:
        # Create backup directory if it doesn't exist
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        with SQLiteConnection(DB_PATH) as source_conn:
            # Create new database connection for backup
            backup_conn = sqlite3.connect(str(backup_path))
            
            try:
                # Backup database
                source_conn.backup(backup_conn)
                
                # Get size of backup file
                backup_size = os.path.getsize(backup_path)
                
                return {
                    "status": "success",
                    "backup_path": str(backup_path),
                    "backup_size_bytes": backup_size,
                    "timestamp": datetime.now().isoformat()
                }
                
            finally:
                backup_conn.close()
                
    except (sqlite3.Error, OSError) as e:
        raise ValueError(f"Backup error: {str(e)}")

@mcp.tool()
def bulk_link_entities(
    id_str: str,
    entities: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create multiple entity links for a paper in a single transaction.
    
    Args:
        id_str: Literature ID in format "source:id"
        entities: List of entity dictionaries, each containing:
                 {
                     "name": str,
                     "relation_type": str,
                     "notes": Optional[str]
                 }
    
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    if not entities:
        raise ValueError("At least one entity must be provided")
    
    # Validate all entities first
    for i, entity in enumerate(entities):
        if not entity.get('name'):
            raise ValueError(f"Entity {i} missing required 'name' field")
        relation_type = entity.get('relation_type', 'discusses')
        if relation_type not in LiteratureIdentifier.VALID_ENTITY_RELATIONS:
            raise ValueError(f"Invalid relation_type '{relation_type}' for entity '{entity['name']}'")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Prepare batch insert
            cursor.executemany("""
                INSERT OR REPLACE INTO literature_entity_links
                (literature_id, entity_name, relation_type, notes)
                VALUES (?, ?, ?, ?)
            """, [
                (lit_id.full_id, entity['name'], 
                 entity.get('relation_type', 'discusses'),
                 entity.get('notes'))
                for entity in entities
            ])
            
            conn.commit()
            return {
                "status": "success",
                "literature_id": lit_id.full_id,
                "entities_linked": len(entities)
            }
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

if __name__ == "__main__":
    # Start the FastMCP server
    mcp.run()