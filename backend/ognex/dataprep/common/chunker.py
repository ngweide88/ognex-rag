"""Chunk recombination helpers.

Very short chunks hurt retrieval, so adjacent fragments are merged until every
chunk clears a minimum word count. Rebuilding the list keeps the merge
deterministic.
"""



def _merge_short_chunks(chunks: list[str], threshold: int) -> list[str]:
    merged: list[str] = []
    buffer = ""

    for chunk in chunks:
        buffer = f"{buffer} {chunk}".strip() if buffer else chunk
        if len(buffer.split()) >= threshold:
            merged.append(buffer)
            buffer = ""

    if buffer:
        if merged:
            merged[-1] = f"{merged[-1]} {buffer}"
        else:
            merged.append(buffer)
    return merged


def iterative_chunk_recombination(chunks: list[str], threshold: int) -> list[str]:
    return _merge_short_chunks(chunks, threshold)