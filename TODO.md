# Literature Management System - TODO List

## Phase 1: Core System Cleanup

### Schema Simplification

- [ ] Remove `section_progress` table and related functionality
- [ ] Remove `paper_relations` table and related functionality
- [ ] Merge collections into tags system:
  - [ ] Add tag categories/types
  - [ ] Migrate collection data to tags
  - [ ] Update tag-related queries
- [ ] Add source metadata to `reading_list`:
  ```sql
  ALTER TABLE reading_list
  ADD COLUMN source_type TEXT,
  ADD COLUMN source_url TEXT;
  ```
- [ ] Simplify `literature_entity_links`:
  - [ ] Remove redundant fields
  - [ ] Optimize indices
  - [ ] Add validation constraints

### Tool Removal

- [ ] Remove section-based tools:
  - [ ] `track_reading_progress`
  - [ ] `get_reading_progress`
  - [ ] Section-related validation code
- [ ] Remove relationship tools:
  - [ ] `add_literature_relation`
  - [ ] `find_related_papers`
  - [ ] Relationship validation code
- [ ] Remove research analysis tools:
  - [ ] `identify_research_gaps`
  - [ ] `track_entity_evolution`
  - [ ] Analysis-related queries
- [ ] Remove collection tools:
  - [ ] `create_collection`
  - [ ] `add_to_collection`
  - [ ] Collection management code

### Tool Simplification

- [ ] Simplify status tracking:
  ```python
  def update_literature_status(
      id_str: str,
      status: str,
      notes: Optional[str] = None
  ) -> Dict[str, Any]
  ```
- [ ] Redesign entity context handling:
  ```python
  def get_literature_entities(
      id_str: str,
      include_metadata: bool = False
  ) -> Dict[str, Any]
  ```
- [ ] Update statistics tool:
  ```python
  def get_literature_stats(
      id_str: str,
      include_entities: bool = True
  ) -> Dict[str, Any]
  ```
- [ ] Simplify entity validation:
  ```python
  def validate_entity_links(
      entity_names: List[str]
  ) -> Dict[str, Any]
  ```

## Phase 2: Core Functionality Enhancement

### Source Type Support

- [ ] Expand `LiteratureIdentifier`:
  ```python
  VALID_SOURCES = {
      'arxiv', 'doi', 'semanticscholar',
      'github', 'webpage', 'custom'
  }
  ```
- [ ] Add source type validation:
  ```python
  def validate_source(
      source_type: str,
      source_url: Optional[str]
  ) -> bool
  ```
- [ ] Update tools for source handling:
  - [ ] Add source metadata extraction
  - [ ] Handle source-specific validation
  - [ ] Support source URL validation

### Bulk Operations

- [ ] Implement bulk literature addition:
  ```python
  def bulk_add_literature(
      items: List[Dict[str, Any]],
      validate: bool = True
  ) -> Dict[str, Any]
  ```
- [ ] Implement bulk entity linking:
  ```python
  def bulk_link_entities(
      links: List[Dict[str, Any]],
      validate: bool = True
  ) -> Dict[str, Any]
  ```
- [ ] Add validation and error handling:
  - [ ] Batch size limits
  - [ ] Transaction management
  - [ ] Error reporting
  - [ ] Rollback support

### Documentation Updates

- [ ] Update schema documentation:
  - [ ] New table structure
  - [ ] Field descriptions
  - [ ] Constraints and indices
- [ ] Create usage examples:

  ```python
  # Example: Adding literature from different sources
  add_literature(
      "arxiv:2312.12456",
      source_url="https://arxiv.org/abs/2312.12456"
  )

  # Example: Bulk entity linking
  bulk_link_entities([
      {
          "literature_id": "arxiv:2312.12456",
          "entities": [
              {"name": "transformer", "relation": "discusses"},
              {"name": "attention", "relation": "evaluates"}
          ]
      }
  ])
  ```

- [ ] Document memory graph integration:
  - [ ] Entity validation workflow
  - [ ] Synchronization best practices
  - [ ] Error handling
- [ ] Add source-specific examples:
  - [ ] arXiv integration
  - [ ] DOI handling
  - [ ] Semantic Scholar integration
  - [ ] Custom source usage

## Testing Requirements

### Unit Tests

- [ ] Schema validation tests
- [ ] Source type validation tests
- [ ] Bulk operation tests
- [ ] Entity linking tests

### Integration Tests

- [ ] Memory graph integration tests
- [ ] Source type handling tests
- [ ] Bulk operation performance tests
- [ ] Error handling tests

### Performance Tests

- [ ] Bulk operation benchmarks
- [ ] Query optimization tests
- [ ] Memory usage monitoring
- [ ] Response time validation
