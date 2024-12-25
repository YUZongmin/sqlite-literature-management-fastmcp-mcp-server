# TODO: Implement Concept-Paper Linking

Source: @modelcontextprotocol/server-memory

This document outlines the tasks required to connect concepts in the memory knowledge graph with source papers in the literature database.

## Goal

Enable Claude to associate research papers with relevant concepts and to retrieve source papers for concepts discussed in the chat.

## Phases

### Phase 1: Database and Tool Enhancements (Literature Server)

-   [ ] **Schema Update:**
    -   [ ] Add `concepts` table to `schema.sql`:

        ```sql
        CREATE TABLE concepts (
            concept_id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_name TEXT UNIQUE NOT NULL
        );
        ```

    -   [ ] Add `literature_concepts` table to `schema.sql`:

        ```sql
        CREATE TABLE literature_concepts (
            literature_id TEXT,
            concept_id INTEGER,
            PRIMARY KEY (literature_id, concept_id),
            FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE,
            FOREIGN KEY (concept_id) REFERENCES concepts(concept_id) ON DELETE CASCADE
        );
        ```
    -   [ ] Add `literature_entity_links` table to `schema.sql`:
        ```sql
        CREATE TABLE literature_entity_links (
            literature_id TEXT,
            entity_name TEXT,
            PRIMARY KEY (literature_id, entity_name),
            FOREIGN KEY (literature_id) REFERENCES reading_list(literature_id) ON DELETE CASCADE
        );
        ```
    -   [ ] Update database initialization logic to create new tables.

-   [ ] **New Tools:**
    -   [ ] Implement `add_concept(concept_name: str) -> int`
        -   Inserts a new concept into `concepts` (or ignores if it exists).
        -   Returns the `concept_id`.
    -   [ ] Implement `link_concept_to_literature(id_str: str, concept_name: str)`
        -   Adds an entry to `literature_concepts`, linking literature to the concept.
        -   Calls `add_concept` to ensure the concept exists.
    -   [ ] Implement `get_concepts_for_literature(id_str: str) -> List[str]`
        -   Retrieves a list of concept names associated with a literature ID.
    -   [ ] Implement `find_literature_by_concepts(concept_names: List[str]) -> List[str]`
        -   Retrieves a list of literature IDs associated with the given concepts.

-   [ ] **Tool Modifications:**
    -   [ ] Modify `add_literature` to accept an optional `concepts: Optional[List[str]]` parameter.
        -   If `concepts` is provided, call `add_concept` and `link_concept_to_literature` for each concept after adding the literature.

-   [ ] **Code Review:**
    -   [ ] Review existing literature server code (`.py` file).
    -   [ ] Identify areas needing adaptation for the new schema and tools.
    -   [ ] Ensure proper error handling and database connection management.

### Phase 2: Integration with Memory Server

-   [ ] **Memory Server Tool (New):**
    -   [ ] Implement `search_memory_entities(query: str) -> List[str]` (or similar)
        -   Searches for entities in the memory server based on a query string.

-   [ ] **Literature Server Tools (New):**
    -   [ ] Implement `link_literature_to_memory_entity(id_str: str, entity_name: str)`
        -   Calls `search_memory_entities` to verify entity existence in memory server.
        -   Adds an entry to `literature_entity_links` table.
        -   Potentially adds an observation to the entity in the memory server using a hypothetical `add_observation_to_entity` tool.
    -   [ ] Implement `get_linked_entities(id_str: str) -> List[str]`
        -   Retrieves entities from the memory graph that are linked to a specific piece of literature.
    -   [ ] Implement `get_linked_literature(entity_name: str) -> List[str]`
        -   Retrieves literature linked to a specific entity in the memory graph.

-   [ ] **Inter-Server Communication:**
    -   [ ] Choose and implement a communication method between servers (e.g., direct API calls, message queue).

-   [ ] **Claude Prompt Engineering:**
    -   [ ] Update Claude's system prompt:
        -   Instruct it to identify relevant concepts.
        -   Instruct it to use the new tools for tagging literature and linking to memory entities.
        -   Instruct it to use the new tools for retrieving source papers.

### Phase 3: Testing and Refinement

-   [ ] **Thorough Testing:**
    -   [ ] Test each new and modified tool individually.
    -   [ ] Test the integration between the two servers.
    -   [ ] Create realistic scenarios for Claude to use the new functionalities.

-   [ ] **Performance Optimization:**
    -   [ ] Add indexes to new tables if needed for performance.
    -   [ ] Profile code to identify bottlenecks.

-   [ ] **Error Handling and Robustness:**
    -   [ ] Ensure graceful handling of errors (database, network, missing entities).

## Notes

- This TODO list assumes the use of a dedicated `concepts` table (recommended approach).
- Adjust the tasks as needed based on your specific implementation choices.
- Consider adding more detailed documentation to the code as you implement these features.
