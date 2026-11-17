"""Knowledge-base ingestion pipeline.

    PDF -> page text (+ provenance tags) -> parent chunks
        -> child chunks at 3 granularities -> embeddings -> ChromaDB
        -> metadata

Progress is written to the task table so the admin UI can poll it.
"""

from __future__ import annotations

import uuid

from ognex.config import settings
from ognex.database.tasks import TASK_STATUS_PENDING, update_task
from ognex.dataprep.steps.child_chunks import split_children
from ognex.dataprep.steps.metadata import generate_metadata
from ognex.dataprep.steps.parent_chunks import build_parent_chunks
from ognex.dataprep.steps.read_pdf import combine_pages, extract_pages
from ognex.dataprep.steps.vector_store import create_vector_database

DEFAULT_SUFFIXES = ["", "medium", "small"]
PROGRESS_STEPS = ["10% extracted", "40% child chunks", "70% embedded", "100% done"]


def create_knowledge_base(
    knowledge_base_name: str,
    pdf_path: str,
    extra_info: dict | None = None,
) -> None:
    task_id = (extra_info or {}).get("task_id")

    def progress(message: str) -> None:
        if task_id:
            update_task(task_id, TASK_STATUS_PENDING, message)

    progress(PROGRESS_STEPS[0])
    pages = extract_pages(pdf_path)
    combined_text = combine_pages(pages)
    if not combined_text.strip():
        raise ValueError("The uploaded PDF contains no extractable text")

    parent_chunks = build_parent_chunks(combined_text, knowledge_base_name)
    if not parent_chunks:
        raise ValueError("No text chunks could be produced from the PDF")

    doc_ids = [str(uuid.uuid4()) for _ in parent_chunks]

    sizes = settings.chunk_sizes[: len(DEFAULT_SUFFIXES)]
    suffixes = DEFAULT_SUFFIXES[: len(sizes)]

    for index, (size, suffix) in enumerate(zip(sizes, suffixes)):
        children = split_children(parent_chunks, size)
        create_vector_database(
            parent_chunks,
            doc_ids,
            children,
            knowledge_base_name,
            suffix=suffix,
            replace=True,
        )
        progress(PROGRESS_STEPS[min(index + 1, len(PROGRESS_STEPS) - 1)])

    generate_metadata(knowledge_base_name)
    progress(PROGRESS_STEPS[-1])