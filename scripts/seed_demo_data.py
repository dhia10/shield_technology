"""
Shield Technology Synthetic Demo Data Seeder.
Generates realistic, anonymized commercial equipment sheets & SLA service packages.
Enables instant local execution and automated testing without external dependencies.
"""

import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Optional, Dict, Any
from app.schemas.enums import EquipmentCategory
from app.search.engine import search_service, SearchService
from app.search.catalog import CATALOG_ITEMS


def seed_database(target_search_service: Optional[SearchService] = None) -> int:
    """Populates vector store with catalog security equipment records."""
    svc = target_search_service or search_service
    count = svc.index_batch(CATALOG_ITEMS)
    print(f"[SUCCESS] Indexed {count} enterprise hardware entities into vector store.")
    return count


if __name__ == "__main__":
    print("--- Seeding Shield Technology Hardware Catalog ---")
    indexed = seed_database()
    print(f"Total items currently indexed in memory vector store: {search_service.count_indexed()}")
