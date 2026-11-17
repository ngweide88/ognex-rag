"""Knowledge-base metadata used by the admin view."""

from __future__ import annotations

import glob
import os
import time

from ognex.config import settings
from ognex.helper import save_to_pickle


def generate_metadata(knowledge_base_name: str) -> dict:
    metadata_path = os.path.join(settings.pickle_dir, f"{knowledge_base_name}_metadata.pkl.gz")

    total_size_in_bytes = 0
    for filepath in glob.glob(os.path.join(str(settings.pickle_dir), f"{knowledge_base_name}*")):
        total_size_in_bytes += os.stat(filepath).st_size

    metadata = {
        "timestamp": int(time.time()),
        "bytes": total_size_in_bytes,
        "chunk_sizes": settings.chunk_sizes,
    }
    save_to_pickle(metadata_path, metadata)
    return metadata