-- Core reading list table with expanded source information
CREATE TABLE IF NOT EXISTS reading_list (
    literature_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'custom',
    source_type TEXT CHECK(source_type IN ('paper', 'webpage', 'blog', 'video', 'book', 'custom')),
    source_url TEXT,
    status TEXT CHECK(status IN ('unread', 'reading', 'completed', 'archived')) DEFAULT 'unread',
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    importance INTEGER CHECK(importance BETWEEN 1 AND 5) DEFAULT 3
);

-- Core indexes for reading_list
CREATE INDEX IF NOT EXISTS idx_reading_list_source ON reading_list(source);
CREATE INDEX IF NOT EXISTS idx_reading_list_source_type ON reading_list(source_type);
CREATE INDEX IF NOT EXISTS idx_reading_list_status ON reading_list(status);
CREATE INDEX IF NOT EXISTS idx_reading_list_last_accessed ON reading_list(last_accessed);

-- Tags table remains simple and efficient
CREATE TABLE IF NOT EXISTS tags (
    literature_id TEXT,
    tag TEXT,
    PRIMARY KEY (literature_id, tag),
    FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE
);

-- Simplified entity links table
CREATE TABLE IF NOT EXISTS literature_entity_links (
    literature_id TEXT,
    entity_name TEXT,
    relation_type TEXT CHECK(relation_type IN ('discusses', 'introduces', 'extends', 'evaluates', 'applies', 'critiques')),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (literature_id, entity_name),
    FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE
);

-- Index for entity lookups
CREATE INDEX IF NOT EXISTS idx_entity_links ON literature_entity_links(entity_name);