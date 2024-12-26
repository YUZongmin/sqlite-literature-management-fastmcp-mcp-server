Let me help refine this TODO list based on our previous discussion about simplification and focusing on core functionality. Here's a streamlined version:

# Literature Management System - TODO List

## Phase 1: Core System Cleanup

### Schema Simplification

- [ ] Remove `section_progress` table completely
- [ ] Remove `paper_relations` table completely
- [ ] Remove `collections` and `collection_items` tables, using tags instead
- [ ] Add source metadata to `reading_list`:
  ```sql
  ALTER TABLE reading_list
  ADD COLUMN source_type TEXT,
  ADD COLUMN source_url TEXT;
  ```
- [ ] Simplify `literature_entity_links`:
  ```sql
  -- Remove context field
  -- Keep only essential fields:
  -- literature_id, entity_name, relation_type, notes
  ```

### Tool Removal

- [ ] Remove tools:
  - [ ] `track_reading_progress`
  - [ ] `add_literature_relation`
  - [ ] `identify_research_gaps`
  - [ ] `track_entity_evolution`
  - [ ] All collection-related tools
  - [ ] `sync_entity_links` (keep memory graph read-only)

### Tool Simplification

- [ ] Simplify reading status tools:

  ```python
  def update_literature_status(
      id_str: str,
      status: str,  # only: 'unread', 'reading', 'completed', 'archived'
      notes: Optional[str] = None
  ) -> Dict[str, Any]
  ```

- [ ] Simplify entity context handling:
  ```python
  def get_literature_entities(
      id_str: str
  ) -> Dict[str, Any]
  ```

## Phase 2: Core Functionality Enhancement

### Source Type Support

- [ ] Expand `LiteratureIdentifier`:
  ```python
  VALID_SOURCES = {
      'arxiv', 'doi', 'semanticscholar',
      'webpage', 'blog', 'video', 'book', 'custom'
  }
  ```

### Bulk Operations

- [ ] Add bulk literature import:

  ```python
  def bulk_add_literature(
      items: List[Dict[str, Any]]
  ) -> Dict[str, Any]
  ```

- [ ] Add bulk entity linking:
  ```python
  def bulk_link_paper_entities(
      id_str: str,
      entities: List[Dict[str, str]]
  ) -> Dict[str, Any]
  ```

### Documentation Updates

- [ ] Update schema documentation
- [ ] Add examples for different source types
- [ ] Document memory graph integration (read-only)
- [ ] Add bulk operation examples

## Testing Requirements

- [ ] Basic schema validation tests
- [ ] Source type handling tests
- [ ] Bulk operation tests
- [ ] Memory graph read-only integration tests

Key differences from original:

1. Removed complex features like section tracking and research analysis
2. Simplified entity linking by removing context field
3. Removed collections in favor of simple tags
4. Focused on essential bulk operations only
5. Simplified testing requirements to core functionality
6. Removed performance testing as it's not critical for our lightweight system
7. Kept memory graph integration read-only
