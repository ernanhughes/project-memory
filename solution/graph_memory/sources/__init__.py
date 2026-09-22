"""Source adapters: raw project material → normalized input documents.

The adapters transform, never interpret. No memory semantics are attached:
no entities, no roles, no claims. Interpretation happens later, inside the
GraphRAG indexing pipeline, where its errors can be inspected as derived
state rather than silently baked into the sources.
"""