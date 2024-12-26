# TODO: Memory Graph Integration for Literature Server

This document outlines the plan to extend the literature server with memory graph integration capabilities, enabling seamless connections between research papers and knowledge entities.

## Phase 1: Foundation - Basic Entity Linking

- [ ] **Schema Enhancement:**

  ```sql
  -- Single table for tracking paper-entity relationships
  CREATE TABLE literature_entity_links (
      literature_id TEXT,
      entity_name TEXT,
      relation_type TEXT,
      context TEXT,              -- Section/part of paper where entity is discussed
      notes TEXT,                -- Explanation of relationship
      PRIMARY KEY (literature_id, entity_name),
      FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE
  );

  -- Index for efficient entity-based lookups
  CREATE INDEX idx_entity_links ON literature_entity_links(entity_name);
  ```

- [ ] **Core Link Management Tools:**
  - [ ] Implement basic entity linking tools:
    ```python
    @mcp.tool()
    def link_paper_to_entity(
        id_str: str,
        entity_name: str,
        relation_type: str,
        context: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]
    ```
  - [ ] Add entity link management:
    ```python
    def update_entity_link(...)  # Update existing links
    def remove_entity_link(...)  # Remove entity links
    def get_paper_entities(...)  # Get entities for a paper
    def get_entity_papers(...)   # Get papers for an entity
    ```

## Phase 2: Reading Integration

- [ ] **Enhance Section Progress:**

  - [ ] Modify `track_reading_progress` schema and function:
    ```python
    def track_reading_progress(
        id_str: str,
        section: str,
        status: str,
        key_points: Optional[List[str]] = None,
        entities: Optional[List[Dict[str, str]]] = None  # New parameter
    )
    ```
  - [ ] Add entity context tracking to section progress
  - [ ] Support bulk entity linking during reading

- [ ] **Note Taking Integration:**
  - [ ] Enhance note taking with entity support:
    ```python
    def update_literature_notes(
        id_str: str,
        note_type: str,
        content: str,
        entities: Optional[List[Dict[str, str]]] = None,  # New parameter
        append: bool = True,
        timestamp: bool = True
    )
    ```
  - [ ] Add entity extraction from notes
  - [ ] Support entity linking in specific note sections

## Phase 3: Query & Analysis

- [ ] **Basic Query Tools:**

  ```python
  @mcp.tool()
  def find_papers_by_entities(
      entity_names: List[str],
      match_type: str = 'any'  # 'any', 'all', 'exact'
  ) -> List[Dict[str, Any]]

  @mcp.tool()
  def get_entity_relationships(
      entity_name: str
  ) -> Dict[str, Any]

  @mcp.tool()
  def find_common_papers(
      entity_names: List[str]
  ) -> List[Dict[str, Any]]
  ```

- [ ] **Analysis Tools:**

  ```python
  @mcp.tool()
  def analyze_entity_coverage() -> Dict[str, Any]

  @mcp.tool()
  def find_related_entities(
      id_str: str
  ) -> List[Dict[str, Any]]

  @mcp.tool()
  def get_entity_paper_stats(
      entity_name: str
  ) -> Dict[str, Any]
  ```

## Phase 4: Integration with Memory Graph

- [ ] **Memory Graph Reading:**

  - [ ] Add configuration for memory graph location:
    ```python
    MEMORY_GRAPH_PATH = os.environ.get('MEMORY_GRAPH_PATH')
    ```
  - [ ] Implement memory graph parsing:

    ```python
    class MemoryGraphReader:
        def __init__(self, path: Path):
            self.path = path

        def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
            pass

        def validate_entity(self, name: str) -> bool:
            pass
    ```

  - [ ] Add entity validation against memory graph

- [ ] **Synchronization Tools:**
  - [ ] Track memory graph updates
  - [ ] Handle entity renames/merges
  - [ ] Clean up orphaned links

## Phase 5: Research Support

- [ ] **Enhanced Search:**

  ```python
  @mcp.tool()
  def search_papers_by_entity_pattern(
      pattern: Dict[str, Any]  # Entity relationship pattern
  ) -> List[Dict[str, Any]]

  @mcp.tool()
  def find_bridging_papers(
      entity_names: List[str]
  ) -> List[Dict[str, Any]]
  ```

- [ ] **Research Insights:**

  ```python
  @mcp.tool()
  def generate_entity_summary(
      entity_name: str
  ) -> Dict[str, Any]

  @mcp.tool()
  def track_entity_evolution(
      entity_name: str
  ) -> List[Dict[str, Any]]
  ```

## Phase 6: Testing & Documentation

- [ ] **Testing:**

  - [ ] Unit tests for all new tools
  - [ ] Integration tests with sample memory graph
  - [ ] Edge case handling
  - [ ] Performance benchmarks

- [ ] **Documentation:**
  - [ ] Update README with memory graph features
  - [ ] Add example workflows for entity linking
  - [ ] Document best practices
  - [ ] API documentation for new tools

## Phase 7: Workflow Optimization

- [ ] **User Experience:**

  - [ ] Implement bulk operations
  - [ ] Add entity suggestions
  - [ ] Create quick lookup tools
  - [ ] Add interactive workflows

- [ ] **Performance:**
  - [ ] Query optimization
  - [ ] Implement caching
  - [ ] Index tuning
  - [ ] Batch operations

## Notes

- All new tools should follow existing error handling patterns
- Maintain backward compatibility where possible
- Consider adding versioning to entity links
- Plan for future extensibility (e.g., more relationship types)
- Keep memory graph synchronization lightweight and efficient
