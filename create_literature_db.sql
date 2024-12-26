-- Core sources table
CREATE TABLE sources (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT CHECK(type IN ('paper', 'webpage', 'book', 'video')) NOT NULL,
    identifiers JSONB NOT NULL,  -- {type: value} where type is from VALID_TYPES
    status TEXT CHECK(status IN ('unread', 'reading', 'completed', 'archived')) DEFAULT 'unread'
);

-- Notes with titles for better organization
CREATE TABLE source_notes (
    source_id UUID REFERENCES sources(id),
    note_title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, note_title)
);

-- Entity links remain essential for knowledge graph integration
CREATE TABLE source_entity_links (
    source_id UUID REFERENCES sources(id),
    entity_name TEXT,
    relation_type TEXT CHECK(relation_type IN ('discusses', 'introduces', 'extends', 'evaluates', 'applies', 'critiques')),
    notes TEXT,
    PRIMARY KEY (source_id, entity_name)
);