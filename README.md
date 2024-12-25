# literateMCP

A FastMCP server for managing academic literature with structured note-taking and organization, designed for seamless interaction with Claude. Built with SQLite for simplicity and portability.

## Features

- Source-agnostic literature tracking (arXiv, DOI, Semantic Scholar, custom)
- Structured note-taking system with categorized notes (summary, critique, implementation, future work)
- Section-by-section reading progress tracking
- Collections and tags for flexible organization
- Literature relationship mapping (cites, extends, contradicts, similar_to)
- Comprehensive statistics and progress tracking
- SQLite-based for simplicity and portability

## Setup

1. Requirements:

   - Python 3.8+
   - FastMCP
   - SQLite3

2. Installation:

   ```bash
   # Clone repository
   git clone https://github.com/yourusername/literateMCP
   cd literateMCP

   # Install dependencies
   pip install fastmcp sqlite3

   # Create database
   sqlite3 literature.db < schema.sql

   # Set database path
   export SQLITE_DB_PATH=/path/to/literature.db
   ```

## Usage with Claude

### Literature Management

```python
# Add new literature
add_literature("arxiv:2312.12456", importance=4, tags=["ml", "transformers"])

# Add structured notes
update_literature_notes(
    "arxiv:2312.12456",
    note_type="summary",
    content="Novel approach to attention mechanisms..."
)

# Track reading progress
track_reading_progress(
    "arxiv:2312.12456",
    section="methods",
    status="completed",
    key_points=["Innovative architecture", "Strong empirical results"]
)

# Add relationships
add_literature_relation(
    "arxiv:2312.12456",
    "arxiv:2310.54321",
    relation_type="extends"
)
```

### Workflow Examples

1. Adding New Literature:

```
Human: "I found an interesting paper on arxiv:2312.12456"
Claude: Let me help you add that to your database.
       I'll add it with default importance and you can tell me any specific tags or collections to include.
       Would you like to start taking notes or tracking your reading progress?
```

2. Taking Notes:

```
Human: "Let me tell you the key points from the methodology section"
Claude: I'll help structure your notes.
       I'll format them as a METHODS section note with timestamp and store them in a way that's easy to reference later.
       Would you like me to also update the section's reading progress?
```

3. Tracking Progress:

```
Human: "I've finished reading the introduction"
Claude: Great! I'll mark the introduction section as completed.
       Current progress: 2/8 sections completed (25%)
       Would you like to add any key points from the introduction?
```

4. Finding Related Papers:

```
Human: "What papers in my database are related to this?"
Claude: I'll search for related papers:
       - 3 papers directly cite this one
       - 2 papers extend its methodology
       Here's a summary of each relationship...
```

## FastMCP Tools

### Core Management

- `add_literature(id_str, importance, notes, tags, collections)`: Add new literature
- `update_literature_status(id_str, status, notes)`: Update reading status
- `update_literature_notes(id_str, note_type, content, append, timestamp)`: Add/update notes

### Progress Tracking

- `track_reading_progress(id_str, section, status, key_points)`: Track section progress
- `get_reading_progress(id_str)`: Get progress for all sections
- `get_literature_stats(id_str)`: Get comprehensive statistics

### Organization

- `add_literature_relation(from_id_str, to_id_str, relation_type, notes)`: Track relationships
- `find_related_literature(id_str, relation_depth, include_notes)`: Find related works

## Database Schema

### Core Tables

- `reading_list`: Main literature tracking
  - `literature_id` (PK), `source`, `status`, `importance`, `notes`
- `tags`: Literature tags
- `collections`: Named collections of literature
- `section_progress`: Section-by-section reading progress
- `paper_relations`: Literature relationships

### Valid Values

- Sources: `semanticscholar`, `arxiv`, `doi`, `custom`
- Sections: `abstract`, `introduction`, `background`, `methods`, `results`, `discussion`, `conclusion`, `appendix`
- Statuses: `unread`, `reading`, `completed`, `archived`
- Relations: `cites`, `extends`, `contradicts`, `similar_to`

## Best Practices

1. Literature ID Format

   - Always use `source:id` format (e.g., `arxiv:2312.12456`)
   - Use `custom:id` for non-standard sources
   - Be consistent with ID formatting within sources

2. Note Organization

   - Use structured note types for different aspects
   - Include timestamps for tracking reading progress
   - Link related concepts across notes
   - Use key points for quick reference

3. Progress Tracking

   - Track progress section by section
   - Add key points while reading
   - Keep status up to date
   - Use importance ratings consistently

4. Relationships
   - Document why papers are related
   - Use appropriate relationship types
   - Add notes to explain relationships
   - Build a connected knowledge graph
