import unittest
import sqlite3
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any

from sqlite_paper_fastmcp_server import (
    LiteratureIdentifier,
    SQLiteConnection,
    link_paper_to_entity,
    track_reading_progress,
    search_papers_by_entity_patterns,
    track_entity_evolution,
    identify_research_gaps,
    load_memory_entities,
    validate_entity_links,
    sync_entity_links
)

class TestData:
    """Test data for entity integration tests"""
    
    @staticmethod
    def create_test_db() -> Path:
        """Create a temporary test database with sample data"""
        db_path = Path(tempfile.mktemp(suffix='.db'))
        
        with sqlite3.connect(db_path) as conn:
            conn.executescript("""
                -- Create tables
                CREATE TABLE reading_list (
                    literature_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source TEXT DEFAULT 'custom',
                    status TEXT CHECK(status IN ('unread', 'reading', 'completed', 'archived')),
                    importance INTEGER CHECK(importance BETWEEN 1 AND 5),
                    notes TEXT,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
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
                
                -- Add indices
                CREATE INDEX idx_entity_name ON literature_entity_links(entity_name);
                CREATE INDEX idx_context ON literature_entity_links(context);
                CREATE INDEX idx_relation_type ON literature_entity_links(relation_type);
            """)
            
            # Insert sample papers
            papers = [
                ("arxiv:2312.0001", "Attention is All You Need", "arxiv", "completed", 5),
                ("arxiv:2312.0002", "BERT: Pre-training", "arxiv", "completed", 4),
                ("arxiv:2312.0003", "GPT: Generative Pre-Training", "arxiv", "reading", 5),
                ("custom:paper1", "Custom Paper 1", "custom", "unread", 3)
            ]
            
            conn.executemany("""
                INSERT INTO reading_list (literature_id, title, source, status, importance)
                VALUES (?, ?, ?, ?, ?)
            """, papers)
            
            # Insert sample entity links
            entity_links = [
                ("arxiv:2312.0001", "transformer", "introduces", "methods"),
                ("arxiv:2312.0001", "attention", "introduces", "methods"),
                ("arxiv:2312.0002", "transformer", "extends", "methods"),
                ("arxiv:2312.0002", "bert", "introduces", "methods"),
                ("arxiv:2312.0003", "transformer", "extends", "background"),
                ("arxiv:2312.0003", "gpt", "introduces", "methods")
            ]
            
            conn.executemany("""
                INSERT INTO literature_entity_links (literature_id, entity_name, relation_type, context)
                VALUES (?, ?, ?, ?)
            """, entity_links)
            
        return db_path
    
    @staticmethod
    def create_test_memory_graph() -> Path:
        """Create a temporary memory graph JSONL file with test entities"""
        graph_path = Path(tempfile.mktemp(suffix='.jsonl'))
        
        entities = [
            {"type": "entity", "name": "transformer", "entityType": "Architecture"},
            {"type": "entity", "name": "attention", "entityType": "Mechanism"},
            {"type": "entity", "name": "bert", "entityType": "Model"},
            {"type": "entity", "name": "gpt", "entityType": "Model"},
            {"type": "entity", "name": "invalid_entity", "entityType": None}  # For testing
        ]
        
        with open(graph_path, 'w') as f:
            for entity in entities:
                f.write(json.dumps(entity) + '\n')
        
        return graph_path

class TestEntityIntegration(unittest.TestCase):
    """Test suite for entity-memory integration features"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database and memory graph"""
        cls.db_path = TestData.create_test_db()
        cls.memory_graph_path = TestData.create_test_memory_graph()
        
        # Set up global DB path for the server
        os.environ['LITERATURE_DB_PATH'] = str(cls.db_path)
    
    def setUp(self):
        """Set up test case"""
        self.conn = SQLiteConnection(self.db_path)
    
    def tearDown(self):
        """Clean up after test"""
        self.conn.close()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test files"""
        os.unlink(cls.db_path)
        os.unlink(cls.memory_graph_path)
    
    def test_entity_linking(self):
        """Test basic entity linking functionality"""
        # Test linking a new entity
        result = link_paper_to_entity(
            "custom:paper1",
            "transformer",
            "discusses",
            "introduction",
            "Discusses transformer architecture"
        )
        
        self.assertEqual(result["status"], "success")
        
        # Verify the link was created
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM literature_entity_links
                WHERE literature_id = ? AND entity_name = ?
            """, ["custom:paper1", "transformer"])
            
            link = cursor.fetchone()
            self.assertIsNotNone(link)
            self.assertEqual(link["relation_type"], "discusses")
    
    def test_reading_progress_with_entities(self):
        """Test tracking reading progress with entity linking"""
        result = track_reading_progress(
            "custom:paper1",
            "methods",
            "completed",
            key_points=["Key point 1", "Key point 2"],
            entities=[
                {"name": "transformer", "relation_type": "discusses"},
                {"name": "attention", "relation_type": "evaluates"}
            ]
        )
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["entities_linked"], 2)
        
        # Verify entities were linked
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM literature_entity_links
                WHERE literature_id = ? AND context = ?
            """, ["custom:paper1", "methods"])
            
            count = cursor.fetchone()["count"]
            self.assertEqual(count, 2)
    
    def test_entity_pattern_search(self):
        """Test searching papers by entity patterns"""
        patterns = [
            {"entity": "transformer", "relation_type": "introduces"},
            {"entity": "attention", "context": "methods"}
        ]
        
        result = search_papers_by_entity_patterns(patterns, match_mode="all")
        
        self.assertGreater(result["total_matches"], 0)
        self.assertIn("match_distribution", result)
        
        # Test invalid pattern
        with self.assertRaises(ValueError):
            search_papers_by_entity_patterns([
                {"entity": "transformer", "relation_type": "invalid_type"}
            ])
    
    def test_entity_evolution(self):
        """Test tracking entity evolution over time"""
        # Add papers with different dates for testing
        with self.conn as conn:
            cursor = conn.cursor()
            # Update dates for existing papers
            dates = [
                ("2020-01-01", "arxiv:2312.0001"),
                ("2021-01-01", "arxiv:2312.0002"),
                ("2022-01-01", "arxiv:2312.0003")
            ]
            
            for date, paper_id in dates:
                cursor.execute("""
                    UPDATE reading_list
                    SET added_date = ?
                    WHERE literature_id = ?
                """, [date, paper_id])
        
        result = track_entity_evolution(
            "transformer",
            time_window="2020-2022",
            include_details=True
        )
        
        self.assertEqual(len(result["timeline"]), 3)
        self.assertIn("transitions", result)
        self.assertIn("evolution_stats", result)
    
    def test_research_gaps(self):
        """Test identifying research gaps"""
        result = identify_research_gaps(
            min_importance=3,
            min_papers=1,
            include_suggestions=True
        )
        
        self.assertIn("isolated_entities", result)
        self.assertIn("weak_connections", result)
        self.assertIn("section_gaps", result)
        self.assertIn("research_suggestions", result)
    
    def test_memory_graph_integration(self):
        """Test memory graph integration features"""
        # Test loading entities
        entities = load_memory_entities(self.memory_graph_path)
        self.assertEqual(entities["status"], "success")
        self.assertGreater(entities["entity_count"], 0)
        
        # Test validation
        validation = validate_entity_links(self.memory_graph_path)
        self.assertGreater(validation["total_linked_entities"], 0)
        
        # Test sync with dry run
        sync_result = sync_entity_links(
            self.memory_graph_path,
            auto_remove=False,
            dry_run=True
        )
        self.assertEqual(sync_result["status"], "dry_run")
    
    def test_edge_cases(self):
        """Test various edge cases"""
        # Test invalid entity name
        with self.assertRaises(ValueError):
            link_paper_to_entity(
                "custom:paper1",
                "nonexistent_entity",
                "discusses"
            )
        
        # Test invalid time window
        with self.assertRaises(ValueError):
            track_entity_evolution("transformer", time_window="invalid")
        
        # Test empty pattern list
        with self.assertRaises(ValueError):
            search_papers_by_entity_patterns([])
        
        # Test invalid importance value
        with self.assertRaises(ValueError):
            identify_research_gaps(min_importance=6)
    
    def test_performance(self):
        """Test performance with larger datasets"""
        # Add more test data
        with self.conn as conn:
            cursor = conn.cursor()
            
            # Add 100 papers with random entities
            for i in range(100):
                paper_id = f"test:paper{i}"
                cursor.execute("""
                    INSERT INTO reading_list (literature_id, title, importance)
                    VALUES (?, ?, ?)
                """, [paper_id, f"Test Paper {i}", i % 5 + 1])
                
                # Link to random entities
                entities = ["transformer", "attention", "bert", "gpt"]
                for entity in entities[:2]:  # Link each paper to 2 entities
                    cursor.execute("""
                        INSERT INTO literature_entity_links
                        (literature_id, entity_name, relation_type, context)
                        VALUES (?, ?, ?, ?)
                    """, [paper_id, entity, "discusses", "methods"])
        
        # Test search performance
        start_time = datetime.now()
        result = search_papers_by_entity_patterns([
            {"entity": "transformer"},
            {"entity": "attention"}
        ])
        duration = datetime.now() - start_time
        
        self.assertLess(duration.total_seconds(), 1.0)  # Should complete within 1 second
        self.assertGreater(result["total_matches"], 0)

if __name__ == '__main__':
    unittest.main() 