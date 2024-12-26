# Literature Management System

A powerful system for managing research papers and integrating with knowledge graphs.

## Features

### Core Features

- Flexible paper identifier system supporting multiple sources
- Structured note-taking and progress tracking
- Tag and collection management
- Customizable importance ratings

### Entity-Memory Integration

- Link papers to knowledge graph entities
- Track entity evolution through literature
- Identify research gaps and opportunities
- Memory graph synchronization

### Research Support

- Complex entity pattern search
- Timeline analysis
- Research gap identification
- Entity relationship tracking

## Prerequisites

This system integrates with the [MCP Memory Server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) for persistent knowledge graph storage. You'll need to install and configure it first.

## Quick Start

1. Create a new SQLite database with our schema:

```bash
# Create a new database
sqlite3 literature.db < create_literature_db.sql
```

2. Install the literature management server:

```bash
# Install for Claude Desktop with your database path
fastmcp install sqlite-paper-fastmcp-server.py --name "Literature Manager" -e LITERATURE_DB_PATH=/path/to/literature.db

# Optional: Configure memory graph path
fastmcp config set MEMORY_GRAPH_PATH=/path/to/memory.jsonl
```

The server integrates with both your literature database and the memory graph, providing a seamless experience for managing research papers and knowledge entities.

## Entity Linking Workflows

### 1. Basic Paper-Entity Linking

Link entities while reading a paper:

```python
track_reading_progress(
    "arxiv:2312.12456",
    section="methods",
    status="completed",
    entities=[
        {"name": "transformer", "relation_type": "introduces"},
        {"name": "attention", "relation_type": "discusses"}
    ]
)
```

Add notes with entity links:

```python
update_literature_notes(
    "arxiv:2312.12456",
    note_type="critique",
    content="The paper introduces a novel approach...",
    entities=[
        {
            "name": "transformer",
            "relation_type": "evaluates",
            "notes": "Novel architecture variant"
        }
    ]
)
```

### 2. Research Analysis

Track entity evolution:

```python
track_entity_evolution(
    "transformer",
    time_window="2017-2024",
    include_details=True
)
```

Search papers by entity patterns:

```python
search_papers_by_entity_patterns([
    {
        "entity": "transformer",
        "relation_type": "introduces"
    },
    {
        "entity": "attention",
        "context": "methods"
    }
], match_mode="all")
```

Identify research gaps:

```python
identify_research_gaps(
    min_importance=3,
    include_suggestions=True
)
```

### 3. Memory Graph Integration

Load and validate entities:

```python
# Load entities from memory graph
entities = load_memory_entities("memory_graph.jsonl")

# Validate existing links
validation = validate_entity_links("memory_graph.jsonl")

# Sync with memory graph
sync_entity_links(
    "memory_graph.jsonl",
    auto_remove=False,
    dry_run=True
)
```

## Schema Documentation

### Literature Entity Links

The `literature_entity_links` table tracks relationships between papers and entities:

```sql
CREATE TABLE literature_entity_links (
    literature_id TEXT,
    entity_name TEXT,
    relation_type TEXT,
    context TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (literature_id, entity_name),
    FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id)
);
```

#### Relation Types

- `introduces`: Paper introduces or defines the entity
- `discusses`: Paper discusses or uses the entity
- `extends`: Paper extends or modifies the entity
- `evaluates`: Paper evaluates or analyzes the entity
- `applies`: Paper applies the entity to a problem
- `critiques`: Paper critiques or identifies issues with the entity

#### Indices

- `idx_entity_name`: Optimize entity-based queries
- `idx_context`: Optimize context-based filtering
- `idx_relation_type`: Optimize relation type filtering

## Best Practices

1. Entity Linking

   - Link entities as you read each section
   - Use specific relation types
   - Add context and notes for clarity
   - Validate against memory graph regularly

2. Research Analysis

   - Start with high-importance papers
   - Use multiple entity patterns for precision
   - Consider time windows for evolution analysis
   - Review research gaps periodically

3. Memory Graph Integration
   - Keep memory graph up to date
   - Run validation checks regularly
   - Review sync changes before applying
   - Document entity relationships

## Performance Considerations

1. Query Optimization

   - Use appropriate indices
   - Filter by importance when possible
   - Limit result sets for large queries
   - Use pattern search efficiently

2. Memory Usage
   - Batch large operations
   - Use pagination for large result sets
   - Clean up temporary resources
   - Monitor memory consumption

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request
