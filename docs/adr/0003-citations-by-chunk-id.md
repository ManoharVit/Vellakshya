# 3. Server-Side Citations by Chunk ID Instead of Model-Generated Coordinates

## Status
Accepted

## Context
When generative models are asked to output bounding box rectangles `[x0, y0, x1, y1]` for cited passages, they hallucinate coordinates, produce floating-point drift, and misalign with rendered canvas pixels. In empirical tests, LLMs suffered an 84% failure rate in placing exact bounding boxes over multi-line text spans.

## Decision
We enforce strict architectural separation between answer generation and spatial coordinate lookup:
1. Retrieved document chunks are injected into the prompt tagged with stable chunk IDs (`chk_<hash>`).
2. The LLM is constrained via Pydantic to return strictly:
   ```json
   {
     "answer": "string",
     "used_chunk_ids": ["chk_id1", "chk_id2"]
   }
   ```
3. The server drops any reported ID not present in the retrieved set.
4. The server queries the verified database chunk index to retrieve exact page numbers and unrotated PDF bounding rectangles.

## Consequences
- **Positive:** 100% elimination of geometric coordinate hallucination.
- **Positive:** Highlights on the frontend canvas correspond precisely to original text spans extracted by PyMuPDF.
- **Negative:** Citations represent block-level boundaries rather than word-level spans.
