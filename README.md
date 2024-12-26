# Universal Source Management System

A flexible system for managing various types of sources (papers, books, webpages, etc.) and integrating them with knowledge graphs.

## Features

### Core Features

- Universal source identification with internal UUID system
- Support for multiple source types (papers, webpages, books, videos, blogs)
- Multiple identifier support per source (arxiv, DOI, semantic scholar, ISBN, URL)
- Structured note-taking with titles and content
- Status tracking (unread, reading, completed, archived)

### Entity Integration

- Link sources to knowledge graph entities
- Track relationships between sources and entities
- Flexible relation types (discusses, introduces, extends, etc.)
- Integration with memory graph

## Prerequisites

This system integrates with the [MCP Memory Server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) for persistent knowledge graph storage.

## Quick Start

1. Create a new SQLite database with our schema:

```bash
# Create a new database
sqlite3 sources.db < create_sources_db.sql
```

2. Install the source management server:

```bash
# Install for Claude Desktop with your database path
fastmcp install source-manager-server.py --name "Source Manager" -e SQLITE_DB_PATH=/path/to/sources.db
```

## Schema

### Core Tables

```sql
-- Sources table
CREATE TABLE sources (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT CHECK(type IN ('paper', 'webpage', 'book', 'video', 'blog')) NOT NULL,
    identifiers JSONB NOT NULL,
    status TEXT CHECK(status IN ('unread', 'reading', 'completed', 'archived')) DEFAULT 'unread'
);

-- Source notes
CREATE TABLE source_notes (
    source_id UUID REFERENCES sources(id),
    note_title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, note_title)
);

-- Entity links
CREATE TABLE source_entity_links (
    source_id UUID REFERENCES sources(id),
    entity_name TEXT,
    relation_type TEXT CHECK(relation_type IN ('discusses', 'introduces', 'extends', 'evaluates', 'applies', 'critiques')),
    notes TEXT,
    PRIMARY KEY (source_id, entity_name)
);
```

## Usage Examples

### 1. Managing Sources

Add a paper with multiple identifiers:

```python
add_source(
    title="Attention Is All You Need",
    type="paper",
    identifier_type="arxiv",
    identifier_value="1706.03762",
    initial_note={
        "title": "Initial thoughts",
        "content": "Groundbreaking paper introducing transformers..."
    }
)

# Add another identifier to the same paper
add_identifier(
    title="Attention Is All You Need",
    type="paper",
    current_identifier_type="arxiv",
    current_identifier_value="1706.03762",
    new_identifier_type="semantic_scholar",
    new_identifier_value="204e3073870fae3d05bcbc2f6a8e263d9b72e776"
)
```

Add a webpage:

```python
add_source(
    title="Understanding Transformers",
    type="webpage",
    identifier_type="url",
    identifier_value="https://example.com/transformers",
)
```

### 2. Note Taking

Add notes to a source:

```python
add_note(
    title="Attention Is All You Need",
    type="paper",
    identifier_type="arxiv",
    identifier_value="1706.03762",
    note_title="Implementation details",
    note_content="The paper describes the architecture..."
)
```

### 3. Entity Linking

Link source to entities:

```python
link_to_entity(
    title="Attention Is All You Need",
    type="paper",
    identifier_type="arxiv",
    identifier_value="1706.03762",
    entity_name="transformer",
    relation_type="introduces",
    notes="First paper to introduce the transformer architecture"
)
```

Query sources by entity:

```python
get_entity_sources(
    entity_name="transformer",
    type_filter="paper",
    relation_filter="discusses"
)
```

## Best Practices

1. Source Management

   - Use consistent titles across references
   - Provide as many identifiers as available
   - Keep notes structured with clear titles
   - Use appropriate source types

2. Entity Linking
   - Be specific with relation types
   - Add contextual notes to relationships
   - Verify entity names against memory graph
   - Keep entity relationships focused

## Technical Details

1. Source Identification

   - Internal UUID system for consistent referencing
   - Multiple external identifiers per source
   - Flexible identifier types (arxiv, doi, url, etc.)
   - Title and type based fuzzy matching

2. Data Organization
   - Structured notes with titles
   - Clear source type categorization
   - Entity relationship tracking
   - Status management

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request
