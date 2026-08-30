# Diagrams

| File | Contents | Status |
|---|---|---|
| `erd.mmd` | Entity relationship diagram, Mermaid source | committed |
| `erd.md` | Same diagram, renders on GitHub without tooling | committed |
| `erd.png` | Export for the stage report | generate on demand |

Sources are committed rather than only images so the diagrams stay editable and
reviewable in diffs. Regenerate PNGs before submitting the report:

```bash
npx -y @mermaid-js/mermaid-cli -i erd.mmd -o erd.png -t dark -b "#0A0B0E" -w 2400
```

Diagrams still to produce (roadmaps/23 §23.4): system architecture, ingestion
sequence, provider normalisation, intelligence pipeline, RAG flow, policy decision
tree, queue topology, confusion matrix, calibration curve.
