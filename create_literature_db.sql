-- Create reading_list table
CREATE TABLE IF NOT EXISTS reading_list (
    literature_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'custom',
    status TEXT CHECK(status IN ('unread', 'reading', 'completed', 'archived')) DEFAULT 'unread',
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    importance INTEGER CHECK(importance BETWEEN 1 AND 5) DEFAULT 3
);

-- Create indexes for reading_list
CREATE INDEX IF NOT EXISTS idx_reading_list_source ON reading_list(source);
CREATE INDEX IF NOT EXISTS idx_reading_list_status ON reading_list(status);
CREATE INDEX IF NOT EXISTS idx_reading_list_last_accessed ON reading_list(last_accessed);

-- Create tags table
CREATE TABLE IF NOT EXISTS tags (
    literature_id TEXT,
    tag TEXT,
    PRIMARY KEY (literature_id, tag),
    FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE
);

-- Create collections table
CREATE TABLE IF NOT EXISTS collections (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

-- Create collection_items table
CREATE TABLE IF NOT EXISTS collection_items (
    collection_id INTEGER,
    literature_id TEXT,
    PRIMARY KEY (collection_id, literature_id),
    FOREIGN KEY (collection_id) REFERENCES collections(collection_id) ON DELETE CASCADE,
    FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE
);

-- Create paper_relations table for tracking relationships between papers
CREATE TABLE IF NOT EXISTS paper_relations (
    from_literature_id TEXT,
    to_literature_id TEXT,
    relation_type TEXT CHECK(relation_type IN ('cites', 'extends', 'contradicts', 'similar_to')),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (from_literature_id, to_literature_id),
    FOREIGN KEY (from_literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE,
    FOREIGN KEY (to_literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE
);

-- Create section_progress table for tracking detailed reading progress
CREATE TABLE IF NOT EXISTS section_progress (
    literature_id TEXT,
    section_name TEXT,
    status TEXT CHECK(status IN ('not_started', 'in_progress', 'completed')),
    key_points TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (literature_id, section_name),
    FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE
);