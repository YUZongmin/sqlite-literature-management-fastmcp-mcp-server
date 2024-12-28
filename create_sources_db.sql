-- Core sources table
CREATE TABLE sources (
    id TEXT PRIMARY KEY,  -- Using TEXT for UUID storage
    title TEXT NOT NULL,
    type TEXT CHECK(type IN ('paper', 'webpage', 'book', 'video', 'blog')) NOT NULL,
    identifiers TEXT NOT NULL,  -- JSON string storing {type: value} pairs
    status TEXT CHECK(status IN ('unread', 'reading', 'completed', 'archived')) DEFAULT 'unread'
);

-- Notes with titles for better organization
CREATE TABLE source_notes (
    source_id TEXT REFERENCES sources(id),
    note_title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, note_title)
);

-- Entity links remain essential for knowledge graph integration
CREATE TABLE source_entity_links (
    source_id TEXT REFERENCES sources(id),
    entity_name TEXT,
    relation_type TEXT CHECK(relation_type IN ('discusses', 'introduces', 'extends', 'evaluates', 'applies', 'critiques')),
    notes TEXT,
    PRIMARY KEY (source_id, entity_name)
);

-- Create indexes for better performance
CREATE INDEX idx_sources_type ON sources(type);
CREATE INDEX idx_sources_status ON sources(status);
CREATE INDEX idx_source_notes_created ON source_notes(created_at);
CREATE INDEX idx_entity_links_name ON source_entity_links(entity_name);