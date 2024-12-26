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
    VALID_RELATIONS = {'cites', 'extends', 'contradicts', 'similar_to'}
    VALID_STATUSES = {'unread', 'reading', 'completed', 'archived'}
    VALID_SECTION_STATUSES = {'not_started', 'in_progress', 'completed'}
    VALID_SECTIONS = {
        'abstract', 'introduction', 'background', 'methods', 
        'results', 'discussion', 'conclusion', 'appendix'
    }
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
    collections: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Add literature to the reading list.
    
    Args:
        id_str: Literature ID in format "source:id" (e.g., "arxiv:2106.15928")
        importance: Literature importance (1-5)
        notes: Initial notes
        tags: List of tags to apply
        collections: List of collection names to add the literature to
    
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Add to reading_list
            cursor.execute("""
                INSERT INTO reading_list (literature_id, source, importance, notes)
                VALUES (?, ?, ?, ?)
            """, [lit_id.full_id, lit_id.source, importance, notes])
            
            # Add tags if provided
            if tags:
                cursor.executemany("""
                    INSERT INTO tags (literature_id, tag)
                    VALUES (?, ?)
                """, [(lit_id.full_id, tag) for tag in tags])
            
            # Add to collections if provided
            if collections:
                # First ensure collections exist
                for collection_name in collections:
                    cursor.execute("""
                        INSERT OR IGNORE INTO collections (name)
                        VALUES (?)
                    """, [collection_name])
                    
                    # Get collection_id and add literature
                    cursor.execute("""
                        INSERT INTO collection_items (collection_id, literature_id)
                        SELECT collection_id, ?
                        FROM collections
                        WHERE name = ?
                    """, [lit_id.full_id, collection_name])
            
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
    note_type: str,  # 'summary', 'critique', 'implementation', 'future_work'
    content: str,
    entities: Optional[List[Dict[str, str]]] = None,  # New parameter
    append: bool = True,  # if True, append to existing notes, if False, replace
    timestamp: bool = True  # if True, add timestamp to note
) -> Dict[str, Any]:
    """Update structured notes for literature with entity linking.
    
    Args:
        id_str: Literature ID in format "source:id"
        note_type: Type of note ('summary', 'critique', 'implementation', 'future_work')
        content: Note content
        entities: Optional list of entities mentioned in these notes
                 Format: [{"name": "entity_name", 
                          "relation_type": "discusses",
                          "notes": "from [note_type] notes: [context]"}]
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
            formatted_note = f"\n\n### {note_type.upper()}"
            if timestamp:
                formatted_note += f" ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
            formatted_note += f"\n{content}"
            
            if append:
                new_notes = existing_notes + formatted_note
            else:
                # Replace existing notes of same type if any
                pattern = f"\n\n### {note_type.upper()}.*?(?=\n\n### |$)"
                new_notes = re.sub(pattern, "", existing_notes, flags=re.DOTALL)
                new_notes += formatted_note
            
            # Update notes
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
                    
                    # Create context from note type
                    context = f"{note_type.lower()}_notes"
                    notes = entity.get('notes') or f"Mentioned in {note_type.lower()} notes"
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO literature_entity_links
                        (literature_id, entity_name, relation_type, context, notes)
                        VALUES (?, ?, ?, ?, ?)
                    """, [
                        lit_id.full_id,
                        entity['name'],
                        relation_type,
                        context,
                        notes
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
def add_literature_relation(
    from_id_str: str,
    to_id_str: str,
    relation_type: str,  # 'cites', 'extends', 'contradicts', 'similar_to'
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Track relationships between literature.
    
    Args:
        from_id_str: Source literature ID in format "source:id"
        to_id_str: Target literature ID in format "source:id"
        relation_type: Type of relationship
        notes: Optional notes about the relationship
        
    Returns:
        Dictionary containing the operation results
    """
    from_lit = LiteratureIdentifier(from_id_str)
    to_lit = LiteratureIdentifier(to_id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO paper_relations 
                (from_literature_id, to_literature_id, relation_type, notes)
                VALUES (?, ?, ?, ?)
            """, [from_lit.full_id, to_lit.full_id, relation_type, notes])
            
            conn.commit()
            return {"status": "success", "relation": {
                "from": from_lit.full_id,
                "to": to_lit.full_id,
                "type": relation_type
            }}
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def track_reading_progress(
    id_str: str,
    section: str,
    status: str,
    key_points: Optional[List[str]] = None,
    entities: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """Track detailed reading progress by section.
    
    Args:
        id_str: Literature ID in format "source:id"
        section: Section name
        status: Reading status for the section
        key_points: Optional list of key points from the section
        entities: Optional list of entities discussed in this section
                 Format: [{"name": "entity_name", 
                          "relation_type": "discusses",
                          "notes": "optional notes"}]
        
    Returns:
        Dictionary containing the operation results
    """
    lit_id = LiteratureIdentifier(id_str)
    
    # Validate section and status
    if section.lower() not in LiteratureIdentifier.VALID_SECTIONS:
        raise ValueError(f"Invalid section. Valid sections: {', '.join(LiteratureIdentifier.VALID_SECTIONS)}")
    if status not in LiteratureIdentifier.VALID_SECTION_STATUSES:
        raise ValueError(f"Invalid status. Valid statuses: {', '.join(LiteratureIdentifier.VALID_SECTION_STATUSES)}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # First track the reading progress as before
            cursor.execute("""
                INSERT OR REPLACE INTO section_progress
                (literature_id, section_name, status, key_points, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, [lit_id.full_id, section.lower(), status, 
                 '\n- '.join(key_points) if key_points else None])
            
            # Then link entities if provided
            if entities:
                for entity in entities:
                    # Validate relation type
                    relation_type = entity.get('relation_type', 'discusses')
                    if relation_type not in LiteratureIdentifier.VALID_ENTITY_RELATIONS:
                        raise ValueError(f"Invalid relation type '{relation_type}'. Valid types: {', '.join(LiteratureIdentifier.VALID_ENTITY_RELATIONS)}")
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO literature_entity_links
                        (literature_id, entity_name, relation_type, context, notes)
                        VALUES (?, ?, ?, ?, ?)
                    """, [
                        lit_id.full_id,
                        entity['name'],
                        relation_type,
                        section.lower(),  # Use section as context
                        entity.get('notes')
                    ])
            
            conn.commit()
            return {
                "status": "success",
                "literature_id": lit_id.full_id,
                "section": section,
                "entities_linked": len(entities) if entities else 0
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def get_reading_progress(
    id_str: str,
) -> Dict[str, Any]:
    """Get reading progress for all sections of a literature.
    
    Args:
        id_str: Literature ID in format "source:id"
        
    Returns:
        Dictionary containing section progress
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT section_name, status, key_points, last_updated
                FROM section_progress
                WHERE literature_id = ?
                ORDER BY last_updated DESC
            """, [lit_id.full_id])
            
            return {
                "literature_id": lit_id.full_id,
                "sections": [dict(row) for row in cursor.fetchall()]
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def get_literature_stats(
    id_str: str,
) -> Dict[str, Any]:
    """Get comprehensive statistics for a piece of literature.
    
    Args:
        id_str: Literature ID in format "source:id"
        
    Returns:
        Dictionary containing statistics including:
        - Basic info (status, importance)
        - Reading progress
        - Related papers count
        - Tags and collections
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get basic info
            cursor.execute("""
                SELECT status, importance, added_date, last_accessed
                FROM reading_list
                WHERE literature_id = ?
            """, [lit_id.full_id])
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Literature {lit_id.full_id} not found")
            basic_info = dict(result)
            
            # Get tags
            cursor.execute("""
                SELECT GROUP_CONCAT(tag) as tags
                FROM tags
                WHERE literature_id = ?
                GROUP BY literature_id
            """, [lit_id.full_id])
            result = cursor.fetchone()
            tags = result['tags'] if result else None
            
            # Get collections
            cursor.execute("""
                SELECT GROUP_CONCAT(c.name) as collections
                FROM collection_items ci
                JOIN collections c ON ci.collection_id = c.collection_id
                WHERE ci.literature_id = ?
                GROUP BY ci.literature_id
            """, [lit_id.full_id])
            result = cursor.fetchone()
            collections = result['collections'] if result else None
            
            # Get relations count
            cursor.execute("""
                SELECT COUNT(*) as relation_count
                FROM paper_relations
                WHERE from_literature_id = ? OR to_literature_id = ?
            """, [lit_id.full_id, lit_id.full_id])
            relations = cursor.fetchone()['relation_count']
            
            # Get reading progress
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_sections,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_sections
                FROM section_progress
                WHERE literature_id = ?
            """, [lit_id.full_id])
            progress = dict(cursor.fetchone())
            
            return {
                "literature_id": lit_id.full_id,
                "basic_info": basic_info,
                "tags": tags.split(',') if tags else [],
                "collections": collections.split(',') if collections else [],
                "relation_count": relations,
                "reading_progress": {
                    "total_sections": progress['total_sections'],
                    "completed_sections": progress['completed_sections'],
                    "completion_percentage": (
                        (progress['completed_sections'] / progress['total_sections'] * 100)
                        if progress['total_sections'] > 0 else 0
                    )
                }
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def find_related_literature(
    id_str: str,
    relation_depth: int = 1,  # How many levels of relationships to traverse
    include_notes: bool = True
) -> List[Dict[str, Any]]:
    """Find literature related to the given one through tracked relationships.
    
    Args:
        id_str: Literature ID in format "source:id"
        relation_depth: How many levels of relationships to traverse
        include_notes: Whether to include notes in results
        
    Returns:
        List of dictionaries containing related literature and their relationships
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Recursive CTE to get related literature
            query = f"""
            WITH RECURSIVE related_literature AS (
                -- Base case: direct relationships
                SELECT 
                    CASE 
                        WHEN from_literature_id = ? THEN to_literature_id 
                        ELSE from_literature_id 
                    END as related_id,
                    relation_type,
                    1 as depth
                FROM paper_relations
                WHERE from_literature_id = ? OR to_literature_id = ?
                
                UNION ALL
                
                -- Recursive case
                SELECT 
                    CASE 
                        WHEN pr.from_literature_id = rl.related_id THEN pr.to_literature_id
                        ELSE pr.from_literature_id
                    END,
                    pr.relation_type,
                    rl.depth + 1
                FROM paper_relations pr
                JOIN related_literature rl ON 
                    pr.from_literature_id = rl.related_id OR 
                    pr.to_literature_id = rl.related_id
                WHERE rl.depth < ?
            )
            SELECT DISTINCT 
                r.literature_id,
                r.source,
                r.status,
                rl.relation_type,
                rl.depth
                {', r.notes' if include_notes else ''}
            FROM related_literature rl
            JOIN reading_list r ON r.literature_id = rl.related_id
            ORDER BY rl.depth, r.literature_id
            """
            
            cursor.execute(query, [lit_id.full_id, lit_id.full_id, lit_id.full_id, relation_depth])
            return [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
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


# ... (previous code) ...

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
def link_paper_to_entity(
    id_str: str,
    entity_name: str,
    relation_type: str,
    context: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Create a link between a paper and an entity in the knowledge graph.
    
    Args:
        id_str: Literature ID in format "source:id" 
        entity_name: Name of the entity to link to
        relation_type: Type of relationship (discusses, introduces, extends, etc.)
        context: Optional section/part of paper where entity is discussed
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
                (literature_id, entity_name, relation_type, context, notes)
                VALUES (?, ?, ?, ?, ?)
            """, [lit_id.full_id, entity_name, relation_type, context, notes])
            
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
                SELECT entity_name, relation_type, context, notes, created_at
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
def get_entity_papers(entity_name: str) -> Dict[str, Any]:
    """Get all papers linked to an entity.
    
    Args:
        entity_name: Name of the entity
        
    Returns:
        Dictionary containing the entity's linked papers and their relationships
    """
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT l.literature_id, l.relation_type, l.context, l.notes,
                       r.status, r.importance, r.source,
                       l.created_at
                FROM literature_entity_links l
                JOIN reading_list r ON l.literature_id = r.literature_id
                WHERE l.entity_name = ?
                ORDER BY r.importance DESC, r.last_accessed DESC
            """, [entity_name])
            
            return {
                "entity": entity_name,
                "papers": [dict(row) for row in cursor.fetchall()]
            }
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def update_entity_link(
    id_str: str,
    entity_name: str,
    relation_type: Optional[str] = None,
    context: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Update an existing link between a paper and an entity.
    
    Args:
        id_str: Literature ID in format "source:id"
        entity_name: Name of the entity
        relation_type: Optional new relationship type
        context: Optional new context
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
            if context is not None:
                updates.append("context = ?")
                params.append(context)
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

@mcp.tool()
def get_entities_by_context(
    id_str: str,
    context_type: Optional[str] = None  # 'section_name' or 'note_type'
) -> Dict[str, Any]:
    """Get entities linked to a paper, organized by context.
    
    Args:
        id_str: Literature ID in format "source:id"
        context_type: Optional filter for specific context type
                     'section_name' for section-based entities
                     'note_type' for note-based entities
        
    Returns:
        Dictionary containing entities grouped by context
    """
    lit_id = LiteratureIdentifier(id_str)
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            query = """
                SELECT context, entity_name, relation_type, notes, created_at
                FROM literature_entity_links
                WHERE literature_id = ?
            """
            params = [lit_id.full_id]
            
            if context_type:
                if context_type == 'section_name':
                    query += " AND context IN ({})".format(
                        ','.join('?' * len(LiteratureIdentifier.VALID_SECTIONS))
                    )
                    params.extend(LiteratureIdentifier.VALID_SECTIONS)
                elif context_type == 'note_type':
                    query += " AND context LIKE '%_notes'"
                else:
                    raise ValueError("Invalid context_type. Use 'section_name' or 'note_type'")
            
            query += " ORDER BY context, created_at DESC"
            
            cursor.execute(query, params)
            
            # Group results by context
            results = {}
            for row in cursor.fetchall():
                context = row['context']
                if context not in results:
                    results[context] = []
                results[context].append({
                    'entity': row['entity_name'],
                    'relation_type': row['relation_type'],
                    'notes': row['notes'],
                    'created_at': row['created_at']
                })
            
            return {
                "literature_id": lit_id.full_id,
                "contexts": results
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def find_papers_by_entities(
    entity_names: List[str],
    match_type: str = 'any',  # 'any', 'all', 'exact'
    relation_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Find papers that are linked to specified entities.
    
    Args:
        entity_names: List of entity names to search for
        match_type: How to match entities:
                   'any' - papers linked to any of the entities
                   'all' - papers linked to all entities
                   'exact' - papers linked to exactly these entities
        relation_types: Optional list of relation types to filter by
        
    Returns:
        Dictionary containing matching papers and statistics
    """
    # Validate match_type
    if match_type not in {'any', 'all', 'exact'}:
        raise ValueError("match_type must be one of: 'any', 'all', 'exact'")
    
    # Validate relation_types if provided
    if relation_types:
        invalid_types = set(relation_types) - LiteratureIdentifier.VALID_ENTITY_RELATIONS
        if invalid_types:
            raise ValueError(f"Invalid relation types: {', '.join(invalid_types)}")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            if match_type == 'any':
                query = """
                    SELECT DISTINCT 
                        r.*,
                        COUNT(l.entity_name) as match_count,
                        GROUP_CONCAT(DISTINCT l.entity_name) as matched_entities
                    FROM reading_list r
                    JOIN literature_entity_links l ON r.literature_id = l.literature_id
                    WHERE l.entity_name IN ({})
                    {}
                    GROUP BY r.literature_id
                    ORDER BY match_count DESC, r.importance DESC
                """.format(
                    ','.join(['?'] * len(entity_names)),
                    "AND l.relation_type IN ({})".format(
                        ','.join(['?'] * len(relation_types))
                    ) if relation_types else ""
                )
                params = entity_names + (relation_types or [])
                
            elif match_type == 'all':
                query = """
                    SELECT 
                        r.*,
                        COUNT(DISTINCT l.entity_name) as match_count,
                        GROUP_CONCAT(DISTINCT l.entity_name) as matched_entities
                    FROM reading_list r
                    JOIN literature_entity_links l ON r.literature_id = l.literature_id
                    WHERE l.entity_name IN ({})
                    {}
                    GROUP BY r.literature_id
                    HAVING match_count = ?
                    ORDER BY r.importance DESC
                """.format(
                    ','.join(['?'] * len(entity_names)),
                    "AND l.relation_type IN ({})".format(
                        ','.join(['?'] * len(relation_types))
                    ) if relation_types else ""
                )
                params = entity_names + (relation_types or []) + [len(entity_names)]
            
            else:  # exact
                query = """
                    WITH PaperEntityCounts AS (
                        SELECT 
                            r.literature_id,
                            COUNT(DISTINCT l.entity_name) as total_entities
                        FROM reading_list r
                        JOIN literature_entity_links l ON r.literature_id = l.literature_id
                        GROUP BY r.literature_id
                    )
                    SELECT 
                        r.*,
                        COUNT(DISTINCT l.entity_name) as match_count,
                        GROUP_CONCAT(DISTINCT l.entity_name) as matched_entities
                    FROM reading_list r
                    JOIN literature_entity_links l ON r.literature_id = l.literature_id
                    JOIN PaperEntityCounts pec ON r.literature_id = pec.literature_id
                    WHERE l.entity_name IN ({})
                    {}
                    GROUP BY r.literature_id
                    HAVING match_count = ? AND pec.total_entities = ?
                    ORDER BY r.importance DESC
                """.format(
                    ','.join(['?'] * len(entity_names)),
                    "AND l.relation_type IN ({})".format(
                        ','.join(['?'] * len(relation_types))
                    ) if relation_types else ""
                )
                params = entity_names + (relation_types or []) + [len(entity_names), len(entity_names)]
            
            cursor.execute(query, params)
            papers = [dict(row) for row in cursor.fetchall()]
            
            return {
                "match_type": match_type,
                "entity_count": len(entity_names),
                "papers_found": len(papers),
                "papers": papers
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def analyze_entity_coverage() -> Dict[str, Any]:
    """Analyze how entities are covered across the literature database.
    Returns statistics about entity coverage and potential gaps.
    
    Returns:
        Dictionary containing entity coverage statistics and analysis
    """
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get entity statistics
            cursor.execute("""
                WITH EntityStats AS (
                    SELECT 
                        entity_name,
                        COUNT(DISTINCT literature_id) as paper_count,
                        GROUP_CONCAT(DISTINCT relation_type) as relation_types,
                        COUNT(DISTINCT context) as context_count,
                        GROUP_CONCAT(DISTINCT context) as contexts
                    FROM literature_entity_links
                    GROUP BY entity_name
                )
                SELECT 
                    entity_name,
                    paper_count,
                    relation_types,
                    context_count,
                    contexts,
                    CASE 
                        WHEN paper_count < 2 THEN 'low_coverage'
                        WHEN paper_count < 5 THEN 'medium_coverage'
                        ELSE 'well_covered'
                    END as coverage_level
                FROM EntityStats
                ORDER BY paper_count DESC, entity_name
            """)
            
            entity_stats = [dict(row) for row in cursor.fetchall()]
            
            # Get overview statistics
            overview = {
                "total_entities": len(entity_stats),
                "coverage_distribution": {
                    "low_coverage": len([e for e in entity_stats if e['coverage_level'] == 'low_coverage']),
                    "medium_coverage": len([e for e in entity_stats if e['coverage_level'] == 'medium_coverage']),
                    "well_covered": len([e for e in entity_stats if e['coverage_level'] == 'well_covered'])
                },
                "context_stats": {
                    "avg_contexts_per_entity": sum(e['context_count'] for e in entity_stats) / len(entity_stats) if entity_stats else 0,
                    "single_context_entities": len([e for e in entity_stats if e['context_count'] == 1])
                }
            }
            
            return {
                "overview": overview,
                "entity_stats": entity_stats
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def find_related_entities(
    literature_id: Optional[str] = None,
    entity_name: Optional[str] = None,
    min_co_occurrences: int = 1
) -> Dict[str, Any]:
    """Find entities that frequently appear together.
    Can search based on either a paper or another entity.
    
    Args:
        literature_id: Optional paper ID to find related entities
        entity_name: Optional entity name to find related entities
        min_co_occurrences: Minimum number of co-occurrences required
        
    Returns:
        Dictionary containing related entities and their relationships
    """
    if not (literature_id or entity_name):
        raise ValueError("Must provide either literature_id or entity_name")
    
    if literature_id and entity_name:
        raise ValueError("Cannot provide both literature_id and entity_name")
        
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            if literature_id:
                lit_id = LiteratureIdentifier(literature_id)
                # Find entities related through the same paper
                query = """
                    SELECT 
                        l2.entity_name,
                        l2.relation_type,
                        l2.context,
                        l2.notes,
                        COUNT(*) as co_occurrence_count
                    FROM literature_entity_links l1
                    JOIN literature_entity_links l2 
                        ON l1.literature_id = l2.literature_id
                        AND l1.entity_name != l2.entity_name
                    WHERE l1.literature_id = ?
                    GROUP BY l2.entity_name, l2.relation_type, l2.context
                    HAVING co_occurrence_count >= ?
                    ORDER BY co_occurrence_count DESC, l2.entity_name
                """
                params = [lit_id.full_id, min_co_occurrences]
            else:
                # Find entities that frequently appear with the given entity
                query = """
                    SELECT 
                        l2.entity_name,
                        GROUP_CONCAT(DISTINCT l2.relation_type) as relation_types,
                        COUNT(DISTINCT l1.literature_id) as shared_papers,
                        GROUP_CONCAT(DISTINCT l2.context) as contexts,
                        GROUP_CONCAT(DISTINCT l2.notes) as notes
                    FROM literature_entity_links l1
                    JOIN literature_entity_links l2 
                        ON l1.literature_id = l2.literature_id
                        AND l1.entity_name != l2.entity_name
                    WHERE l1.entity_name = ?
                    GROUP BY l2.entity_name
                    HAVING shared_papers >= ?
                    ORDER BY shared_papers DESC, l2.entity_name
                """
                params = [entity_name, min_co_occurrences]
            
            cursor.execute(query, params)
            related_entities = [dict(row) for row in cursor.fetchall()]
            
            return {
                "source_type": "paper" if literature_id else "entity",
                "source": literature_id or entity_name,
                "min_co_occurrences": min_co_occurrences,
                "related_count": len(related_entities),
                "related_entities": related_entities
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def load_memory_entities(jsonl_path: str) -> Dict[str, Any]:
    """Load and validate entities from the memory graph JSONL file.
    
    Args:
        jsonl_path: Path to the memory graph JSONL file
    
    Returns:
        Dict containing valid entities and statistics
    """
    try:
        entities = set()
        entity_types = {}
        invalid_entries = []
        
        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('type') == 'entity':
                        name = entry.get('name')
                        if name:
                            entities.add(name)
                            entity_types[name] = entry.get('entityType')
                        else:
                            invalid_entries.append(entry)
                except json.JSONDecodeError:
                    invalid_entries.append(line.strip())
        
        return {
            "status": "success",
            "entity_count": len(entities),
            "entity_types": entity_types,
            "invalid_count": len(invalid_entries),
            "entities": sorted(list(entities))
        }
    except IOError as e:
        raise ValueError(f"Error reading memory graph file: {str(e)}")
    except Exception as e:
        raise ValueError(f"Unexpected error processing memory graph: {str(e)}")

@mcp.tool()
def validate_entity_links(jsonl_path: str) -> Dict[str, Any]:
    """Validate existing entity links against the memory graph.
    
    Args:
        jsonl_path: Path to the memory graph JSONL file
        
    Returns:
        Dictionary containing validation results and any invalid links found
    """
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Get all unique entities from our links
            cursor.execute("""
                SELECT DISTINCT entity_name,
                       COUNT(DISTINCT literature_id) as usage_count
                FROM literature_entity_links
                GROUP BY entity_name
            """)
            linked_entities = {row['entity_name']: row['usage_count'] for row in cursor.fetchall()}
            
            # Load memory graph entities
            memory_data = load_memory_entities(jsonl_path)
            memory_entities = set(memory_data['entities'])
            
            # Find discrepancies
            invalid_entities = set(linked_entities.keys()) - memory_entities
            
            # Get affected papers for invalid entities
            invalid_links = []
            if invalid_entities:
                placeholders = ','.join(['?' for _ in invalid_entities])
                cursor.execute(f"""
                    SELECT l.entity_name,
                           GROUP_CONCAT(DISTINCT l.literature_id) as papers,
                           GROUP_CONCAT(DISTINCT l.relation_type) as relation_types,
                           COUNT(DISTINCT l.literature_id) as paper_count
                    FROM literature_entity_links l
                    WHERE l.entity_name IN ({placeholders})
                    GROUP BY l.entity_name
                """, list(invalid_entities))
                invalid_links = [dict(row) for row in cursor.fetchall()]
            
            return {
                "total_linked_entities": len(linked_entities),
                "valid_entities": len(linked_entities) - len(invalid_entities),
                "invalid_entities": len(invalid_entities),
                "entity_usage": {
                    "total_links": sum(linked_entities.values()),
                    "avg_usage": sum(linked_entities.values()) / len(linked_entities) if linked_entities else 0
                },
                "invalid_links": invalid_links,
                "memory_graph_stats": {
                    "total_entities": memory_data['entity_count'],
                    "entity_types": len(set(memory_data['entity_types'].values()))
                }
            }
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def sync_entity_links(
    jsonl_path: str,
    auto_remove: bool = False,
    dry_run: bool = True
) -> Dict[str, Any]:
    """Synchronize entity links with the memory graph.
    Can optionally remove invalid links automatically.
    
    Args:
        jsonl_path: Path to the memory graph JSONL file
        auto_remove: If True, automatically remove invalid links
        dry_run: If True, only simulate the changes without applying them
        
    Returns:
        Dictionary containing synchronization results and any changes made
    """
    validation = validate_entity_links(jsonl_path)
    
    if not validation['invalid_entities']:
        return {
            "status": "success",
            "message": "No synchronization needed",
            "changes": 0
        }
    
    if auto_remove and not dry_run:
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            try:
                # Get details before removal for reporting
                placeholders = ','.join(['?' for _ in validation['invalid_links']])
                cursor.execute(f"""
                    SELECT l.entity_name,
                           l.literature_id,
                           l.relation_type,
                           l.context
                    FROM literature_entity_links l
                    WHERE l.entity_name IN ({placeholders})
                    ORDER BY l.entity_name, l.literature_id
                """, [link['entity_name'] for link in validation['invalid_links']])
                
                removed_links = [dict(row) for row in cursor.fetchall()]
                
                # Remove invalid links
                cursor.execute(f"""
                    DELETE FROM literature_entity_links
                    WHERE entity_name IN ({placeholders})
                """, [link['entity_name'] for link in validation['invalid_links']])
                
                changes = cursor.rowcount
                conn.commit()
                
                return {
                    "status": "success",
                    "message": f"Removed {changes} invalid links",
                    "changes": changes,
                    "removed_links": removed_links,
                    "affected_papers": len(set(link['literature_id'] for link in removed_links))
                }
            except sqlite3.Error as e:
                conn.rollback()
                raise ValueError(f"SQLite error: {str(e)}")
    else:
        action = "Would remove" if dry_run else "Manual review needed for"
        return {
            "status": "review_needed" if not dry_run else "dry_run",
            "message": f"{action} {validation['invalid_entities']} invalid entities with {sum(link['paper_count'] for link in validation['invalid_links'])} total links",
            "invalid_links": validation['invalid_links'],
            "dry_run": dry_run
        }

@mcp.tool()
def get_memory_entity_info(
    jsonl_path: str,
    entity_name: str
) -> Dict[str, Any]:
    """Get detailed information about an entity from the memory graph.
    
    Args:
        jsonl_path: Path to the memory graph JSONL file
        entity_name: Name of the entity to look up
        
    Returns:
        Dictionary containing entity information and its literature connections
    """
    try:
        # Find entity in memory graph
        entity_info = None
        with open(jsonl_path, 'r') as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get('type') == 'entity' and entry.get('name') == entity_name:
                    entity_info = entry
                    break
        
        if not entity_info:
            raise ValueError(f"Entity '{entity_name}' not found in memory graph")
        
        # Get literature connections
        with SQLiteConnection(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.literature_id,
                       l.relation_type,
                       l.context,
                       l.notes,
                       r.status,
                       r.importance
                FROM literature_entity_links l
                JOIN reading_list r ON l.literature_id = r.literature_id
                WHERE l.entity_name = ?
                ORDER BY r.importance DESC, r.last_accessed DESC
            """, [entity_name])
            
            literature_links = [dict(row) for row in cursor.fetchall()]
            
            return {
                "entity": {
                    "name": entity_info['name'],
                    "type": entity_info.get('entityType'),
                    "attributes": {k: v for k, v in entity_info.items() 
                                 if k not in ['type', 'name', 'entityType']}
                },
                "literature_connections": {
                    "total_papers": len(literature_links),
                    "relation_types": list(set(link['relation_type'] for link in literature_links)),
                    "links": literature_links
                }
            }
            
    except (IOError, json.JSONDecodeError) as e:
        raise ValueError(f"Error reading memory graph: {str(e)}")
    except sqlite3.Error as e:
        raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def search_papers_by_entity_patterns(
    patterns: List[Dict[str, Any]],
    match_mode: str = 'all'  # 'all', 'any'
) -> Dict[str, Any]:
    """Search papers by complex entity relationship patterns.
    
    Args:
        patterns: List of pattern dictionaries, each containing:
                 {
                     "entity": str,
                     "relation_type": Optional[str],
                     "context": Optional[str],
                     "importance": Optional[int]  # minimum paper importance
                 }
        match_mode: How to match patterns ('all' or 'any')
        
    Returns:
        Dictionary containing search results and matching papers
    """
    if not patterns:
        raise ValueError("At least one pattern must be provided")
    
    if match_mode not in {'all', 'any'}:
        raise ValueError("match_mode must be 'all' or 'any'")
    
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Build dynamic query based on patterns
            conditions = []
            params = []
            
            for i, pattern in enumerate(patterns):
                if 'entity' not in pattern:
                    raise ValueError(f"Pattern {i} missing required 'entity' field")
                    
                table_alias = f'l{i}'
                cond = f"""
                    EXISTS (
                        SELECT 1 
                        FROM literature_entity_links {table_alias}
                        WHERE {table_alias}.literature_id = r.literature_id
                        AND {table_alias}.entity_name = ?
                """
                params.append(pattern['entity'])
                
                if pattern.get('relation_type'):
                    if pattern['relation_type'] not in LiteratureIdentifier.VALID_ENTITY_RELATIONS:
                        raise ValueError(f"Invalid relation_type in pattern {i}")
                    cond += f" AND {table_alias}.relation_type = ?"
                    params.append(pattern['relation_type'])
                    
                if pattern.get('context'):
                    cond += f" AND {table_alias}.context LIKE ?"
                    params.append(f"%{pattern['context']}%")
                
                if pattern.get('importance'):
                    cond += f" AND r.importance >= ?"
                    params.append(pattern['importance'])
                
                cond += ")"
                conditions.append(cond)
            
            query = f"""
                SELECT r.*, 
                       GROUP_CONCAT(DISTINCT l.entity_name) as matched_entities,
                       COUNT(DISTINCT l.entity_name) as entity_match_count,
                       GROUP_CONCAT(DISTINCT l.relation_type) as relation_types,
                       GROUP_CONCAT(DISTINCT l.context) as contexts
                FROM reading_list r
                JOIN literature_entity_links l ON r.literature_id = l.literature_id
                WHERE {' OR ' if match_mode == 'any' else ' AND '.join(conditions)}
                GROUP BY r.literature_id
                HAVING entity_match_count >= ?
                ORDER BY r.importance DESC, entity_match_count DESC
            """
            params.append(1 if match_mode == 'any' else len(patterns))
            
            cursor.execute(query, params)
            papers = [dict(row) for row in cursor.fetchall()]
            
            return {
                "patterns": patterns,
                "match_mode": match_mode,
                "total_matches": len(papers),
                "match_distribution": {
                    "by_importance": {str(i): len([p for p in papers if p['importance'] == i]) 
                                    for i in range(1, 6)},
                    "by_entity_count": {str(c): len([p for p in papers if p['entity_match_count'] == c]) 
                                      for c in range(1, max([p['entity_match_count'] for p in papers] + [1]) + 1)}
                },
                "papers": papers
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def track_entity_evolution(
    entity_name: str,
    time_window: Optional[str] = None,  # e.g., "2020-2024"
    include_details: bool = False
) -> Dict[str, Any]:
    """Track how an entity has evolved through papers over time.
    
    Args:
        entity_name: Name of the entity to track
        time_window: Optional time range in format "YYYY-YYYY"
        include_details: If True, include detailed paper information
        
    Returns:
        Dictionary containing evolution analysis and timeline
    """
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            params = [entity_name]
            time_condition = ""
            
            if time_window:
                try:
                    start_year, end_year = map(int, time_window.split('-'))
                    time_condition = "AND CAST(strftime('%Y', r.added_date) as INTEGER) BETWEEN ? AND ?"
                    params.extend([start_year, end_year])
                except ValueError:
                    raise ValueError("time_window must be in format 'YYYY-YYYY'")
            
            # Get timeline data
            query = f"""
                WITH PaperTimeline AS (
                    SELECT 
                        l.literature_id,
                        l.relation_type,
                        l.context,
                        l.notes,
                        r.added_date,
                        r.importance,
                        r.title,
                        r.status
                    FROM literature_entity_links l
                    JOIN reading_list r ON l.literature_id = r.literature_id
                    WHERE l.entity_name = ?
                    {time_condition}
                    ORDER BY r.added_date
                )
                SELECT 
                    strftime('%Y', added_date) as year,
                    COUNT(*) as paper_count,
                    GROUP_CONCAT(DISTINCT relation_type) as relation_types,
                    GROUP_CONCAT(DISTINCT context) as contexts,
                    AVG(importance) as avg_importance,
                    GROUP_CONCAT(DISTINCT status) as statuses
                FROM PaperTimeline
                GROUP BY year
                ORDER BY year
            """
            
            cursor.execute(query, params)
            timeline = [dict(row) for row in cursor.fetchall()]
            
            # Get relationship transitions
            cursor.execute("""
                WITH OrderedPapers AS (
                    SELECT 
                        literature_id,
                        relation_type,
                        LAG(relation_type) OVER (ORDER BY added_date) as prev_relation,
                        added_date
                    FROM PaperTimeline
                )
                SELECT 
                    prev_relation || ' -> ' || relation_type as transition,
                    COUNT(*) as count,
                    MIN(added_date) as first_occurrence,
                    MAX(added_date) as last_occurrence
                FROM OrderedPapers
                WHERE prev_relation IS NOT NULL
                GROUP BY transition
                ORDER BY count DESC
            """)
            transitions = [dict(row) for row in cursor.fetchall()]
            
            # Get detailed paper information if requested
            details = None
            if include_details:
                cursor.execute(f"""
                    SELECT 
                        r.literature_id,
                        r.title,
                        r.status,
                        r.importance,
                        r.added_date,
                        l.relation_type,
                        l.context,
                        l.notes
                    FROM reading_list r
                    JOIN literature_entity_links l ON r.literature_id = l.literature_id
                    WHERE l.entity_name = ?
                    {time_condition}
                    ORDER BY r.added_date
                """, params)
                details = [dict(row) for row in cursor.fetchall()]
            
            return {
                "entity": entity_name,
                "time_window": time_window,
                "timeline": timeline,
                "transitions": transitions,
                "total_papers": sum(t['paper_count'] for t in timeline),
                "evolution_stats": {
                    "relation_diversity": len(set(t['relation_types'].split(',') for t in timeline)),
                    "context_diversity": len(set(t['contexts'].split(',') for t in timeline)),
                    "avg_importance_trend": [float(t['avg_importance']) for t in timeline],
                    "status_distribution": {status: sum(1 for t in timeline if status in t['statuses'].split(','))
                                         for status in LiteratureIdentifier.VALID_STATUSES}
                },
                "paper_details": details if include_details else None
            }
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

@mcp.tool()
def identify_research_gaps(
    min_importance: int = 3,
    min_papers: int = 2,
    include_suggestions: bool = True
) -> Dict[str, Any]:
    """Identify potential research gaps and opportunities.
    
    Args:
        min_importance: Minimum importance level for analysis
        min_papers: Minimum number of papers for reliable analysis
        include_suggestions: If True, include research suggestions
        
    Returns:
        Dictionary containing gap analysis and suggestions
    """
    if min_importance < 1 or min_importance > 5:
        raise ValueError("min_importance must be between 1 and 5")
        
    with SQLiteConnection(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            # Find isolated entities (limited context coverage)
            cursor.execute("""
                WITH EntityContexts AS (
                    SELECT 
                        entity_name,
                        COUNT(DISTINCT context) as context_count,
                        COUNT(DISTINCT literature_id) as paper_count,
                        GROUP_CONCAT(DISTINCT relation_type) as relation_types,
                        GROUP_CONCAT(DISTINCT context) as contexts,
                        AVG(r.importance) as avg_importance
                    FROM literature_entity_links l
                    JOIN reading_list r ON l.literature_id = r.literature_id
                    WHERE r.importance >= ?
                    GROUP BY entity_name
                    HAVING paper_count >= ?
                )
                SELECT *
                FROM EntityContexts
                WHERE context_count = 1
                ORDER BY paper_count DESC, avg_importance DESC
            """, [min_importance, min_papers])
            
            isolated_entities = [dict(row) for row in cursor.fetchall()]
            
            # Find weak connections between entities
            cursor.execute("""
                WITH EntityPairs AS (
                    SELECT 
                        l1.entity_name as entity1,
                        l2.entity_name as entity2,
                        COUNT(DISTINCT l1.literature_id) as shared_papers,
                        GROUP_CONCAT(DISTINCT l1.relation_type || '/' || l2.relation_type) as relation_pairs,
                        AVG(r.importance) as avg_importance
                    FROM literature_entity_links l1
                    JOIN literature_entity_links l2 
                        ON l1.literature_id = l2.literature_id
                        AND l1.entity_name < l2.entity_name
                    JOIN reading_list r ON l1.literature_id = r.literature_id
                    WHERE r.importance >= ?
                    GROUP BY l1.entity_name, l2.entity_name
                    HAVING shared_papers >= ?
                )
                SELECT *
                FROM EntityPairs
                WHERE shared_papers <= 2
                ORDER BY avg_importance DESC, shared_papers
            """, [min_importance, min_papers])
            
            weak_connections = [dict(row) for row in cursor.fetchall()]
            
            # Find unexplored sections
            cursor.execute("""
                WITH PaperSections AS (
                    SELECT 
                        l.entity_name,
                        l.context,
                        COUNT(DISTINCT l.literature_id) as papers_in_section
                    FROM literature_entity_links l
                    JOIN reading_list r ON l.literature_id = r.literature_id
                    WHERE r.importance >= ?
                    AND l.context IN (
                        'abstract', 'introduction', 'background', 'methods',
                        'results', 'discussion', 'conclusion'
                    )
                    GROUP BY l.entity_name, l.context
                )
                SELECT 
                    entity_name,
                    GROUP_CONCAT(context) as covered_sections,
                    COUNT(DISTINCT context) as section_coverage
                FROM PaperSections
                GROUP BY entity_name
                HAVING section_coverage < 4
                ORDER BY section_coverage
            """, [min_importance])
            
            section_gaps = [dict(row) for row in cursor.fetchall()]
            
            result = {
                "isolated_entities": isolated_entities,
                "weak_connections": weak_connections,
                "section_gaps": section_gaps,
                "analysis_params": {
                    "min_importance": min_importance,
                    "min_papers": min_papers
                },
                "statistics": {
                    "total_gaps": len(isolated_entities) + len(weak_connections) + len(section_gaps),
                    "by_type": {
                        "isolated_entities": len(isolated_entities),
                        "weak_connections": len(weak_connections),
                        "section_gaps": len(section_gaps)
                    }
                }
            }
            
            if include_suggestions:
                result["research_suggestions"] = [
                    {
                        "type": "context_expansion",
                        "entities": [e['entity_name'] for e in isolated_entities[:5]],
                        "suggestion": "Consider exploring these entities in different contexts"
                    },
                    {
                        "type": "relationship_investigation",
                        "entity_pairs": [(w['entity1'], w['entity2']) for w in weak_connections[:5]],
                        "suggestion": "Investigate potential relationships between these entity pairs"
                    },
                    {
                        "type": "section_coverage",
                        "entities": [s['entity_name'] for s in section_gaps[:5]],
                        "suggestion": "Expand coverage of these entities across different paper sections"
                    }
                ]
            
            return result
            
        except sqlite3.Error as e:
            raise ValueError(f"SQLite error: {str(e)}")

if __name__ == "__main__":
    # Start the FastMCP server
    mcp.run()