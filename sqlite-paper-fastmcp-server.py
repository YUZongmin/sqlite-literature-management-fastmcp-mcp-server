from pathlib import Path
import sqlite3
import os
from typing import List, Dict, Any, Optional, Tuple
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
    append: bool = True,  # if True, append to existing notes, if False, replace
    timestamp: bool = True  # if True, add timestamp to note
) -> Dict[str, Any]:
    """Update structured notes for literature.
    
    Args:
        id_str: Literature ID in format "source:id"
        note_type: Type of note ('summary', 'critique', 'implementation', 'future_work')
        content: Note content
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
            
            cursor.execute("""
                UPDATE reading_list 
                SET notes = ?, last_accessed = CURRENT_TIMESTAMP
                WHERE literature_id = ?
            """, [new_notes, lit_id.full_id])
            
            conn.commit()
            return {"status": "success", "literature_id": lit_id.full_id}
            
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
    section: str,  # e.g., 'introduction', 'methods', 'results', 'discussion'
    status: str,  # 'not_started', 'in_progress', 'completed'
    key_points: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Track detailed reading progress by section.
    
    Args:
        id_str: Literature ID in format "source:id"
        section: Section name
        status: Reading status for the section
        key_points: Optional list of key points from the section
        
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
            cursor.execute("""
                INSERT OR REPLACE INTO section_progress
                (literature_id, section_name, status, key_points, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, [lit_id.full_id, section.lower(), status, 
                 '\n- '.join(key_points) if key_points else None])
            
            conn.commit()
            return {"status": "success", "literature_id": lit_id.full_id, "section": section}
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

if __name__ == "__main__":
    # Start the FastMCP server
    mcp.run()