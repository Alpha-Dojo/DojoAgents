from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

from dojo.client.async_client import AsyncDojo

from dojoagents.dashboard.schemas.sector import (
    BilingualText,
    SectorNode,
    SectorPath,
    SectorTaxonomyDocumentResponse,
    SectorTaxonomyL1Item,
    SectorTaxonomyL2Item,
    SectorTaxonomyL3Item,
)
from dojoagents.logging import LOGGER
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway


@dataclass(frozen=True)
class ResolvedSectorPath:
    """L1/L2/L3 sector path resolved from cached API sector tree."""

    level1_id: str
    level2_id: str
    level3_id: str
    level1_zh: str
    level1_en: str
    level2_zh: str
    level2_en: str
    level3_zh: str
    level3_en: str

    @staticmethod
    def from_path(path: SectorPath) -> ResolvedSectorPath:
        l1 = path.sector_level_1
        l2 = path.sector_level_2
        l3 = path.sector_level_3
        return ResolvedSectorPath(
            level1_id=l1.sector_id,
            level2_id=l2.sector_id,
            level3_id=l3.sector_id,
            level1_zh=(l1.name.zh or l1.name.en or "").strip(),
            level1_en=(l1.name.en or l1.name.zh or "").strip(),
            level2_zh=(l2.name.zh or l2.name.en or "").strip(),
            level2_en=(l2.name.en or l2.name.zh or "").strip(),
            level3_zh=(l3.name.zh or l3.name.en or "").strip(),
            level3_en=(l3.name.en or l3.name.zh or "").strip(),
        )


def _parse_node(raw: dict) -> SectorNode:
    parent_id = raw.get("parent_id")
    return SectorNode(
        sector_id=str(raw["id"]),
        name=BilingualText(
            zh=str(raw.get("name_alias") or ""),
            en=str(raw.get("name") or ""),
        ),
        description=BilingualText(
            zh=str(raw.get("description_alias") or ""),
            en=str(raw.get("description") or ""),
        ),
        level=int(raw["level"]),
        parent_sector_id=str(parent_id) if parent_id is not None else "",
    )


def _optional_bilingual(text: BilingualText) -> Optional[BilingualText]:
    if (text.zh or "").strip() or (text.en or "").strip():
        return text
    return None


def _sort_nodes(nodes: List[SectorNode]) -> List[SectorNode]:
    return sorted(nodes, key=lambda node: ((node.name.en or node.name.zh).lower(), node.sector_id))


def parse_sector_tree(raw_tree: List[dict]) -> Tuple[List[SectorNode], List[SectorPath]]:
    """Flatten API sector tree into all nodes and L1/L2/L3 paths."""
    nodes: List[SectorNode] = []
    paths: List[SectorPath] = []

    def walk(raw: dict, l1: Optional[SectorNode], l2: Optional[SectorNode]) -> None:
        node = _parse_node(raw)
        nodes.append(node)

        current_l1 = l1
        current_l2 = l2
        if node.level == 1:
            current_l1 = node
            current_l2 = None
        elif node.level == 2:
            current_l2 = node
        elif node.level == 3 and current_l1 is not None and current_l2 is not None:
            paths.append(
                SectorPath(
                    sector_level_1=current_l1,
                    sector_level_2=current_l2,
                    sector_level_3=node,
                )
            )

        for child in raw.get("children") or []:
            walk(child, current_l1, current_l2)

    for root in raw_tree:
        walk(root, None, None)

    return nodes, paths


class SectorStore:
    def __init__(self, client: AsyncDojo) -> None:
        self.client = client
        gateway_method = getattr(type(client), "sector_taxonomy", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self.nodes: List[SectorNode] = []
        self.paths: List[SectorPath] = []
        self.nodes_by_id: Dict[str, SectorNode] = {}
        self._resolved_paths: List[ResolvedSectorPath] = []
        self._path_by_ids: Dict[tuple[str, str, str], ResolvedSectorPath] = {}
        self._paths_by_level3_label: Dict[tuple[str, str], List[ResolvedSectorPath]] = {}
        self.loaded: bool = False
        self._tree_data = None

    async def load(self) -> None:
        try:
            response = await self.gateway.sector_taxonomy(tree=True)
            raw_tree = response.data
            if not raw_tree:
                raise RuntimeError("sector preload failed: empty response")

            self._tree_data = raw_tree
            nodes, paths = parse_sector_tree(raw_tree)
            self.nodes = nodes
            self.paths = paths
            self.nodes_by_id = {node.sector_id: node for node in nodes}
            self._resolved_paths = [ResolvedSectorPath.from_path(path) for path in paths]
            self._path_by_ids = {(path.level1_id, path.level2_id, path.level3_id): path for path in self._resolved_paths}
            self._paths_by_level3_label = {}
            for path in self._resolved_paths:
                key = (path.level3_zh.strip().lower(), path.level3_en.strip().lower())
                self._paths_by_level3_label.setdefault(key, []).append(path)
            self.loaded = True
            LOGGER.info("[SectorStore] Successfully loaded sector tree data via dojosdk.")
        except Exception as e:
            LOGGER.exception(f"[SectorStore] Failed to load sector tree: {e}")
            raise

    def get_taxonomy(self) -> Optional[dict]:
        return self._tree_data

    def get_node(self, sector_id: str) -> Optional[SectorNode]:
        return self.nodes_by_id.get(sector_id)

    def iter_resolved_paths(self) -> Iterator[ResolvedSectorPath]:
        yield from self._resolved_paths

    def find_resolved_path(
        self,
        level1_id: str,
        level2_id: str,
        level3_id: str,
    ) -> Optional[ResolvedSectorPath]:
        return self._path_by_ids.get((level1_id, level2_id, level3_id))

    @staticmethod
    def _label_matches(
        label_zh: str,
        label_en: str,
        path_zh: str,
        path_en: str,
    ) -> bool:
        zh = label_zh.strip().lower()
        en = label_en.strip().lower()
        path_zh_norm = path_zh.strip().lower()
        path_en_norm = path_en.strip().lower()
        return (zh and zh == path_zh_norm) or (en and en == path_en_norm)

    def find_resolved_path_by_labels(
        self,
        *,
        level_1_zh: str = "",
        level_1_en: str = "",
        level_2_zh: str = "",
        level_2_en: str = "",
        level_3_zh: str = "",
        level_3_en: str = "",
    ) -> Optional[ResolvedSectorPath]:
        """Match stock sector labels to cached taxonomy paths."""
        level3_key = (level_3_zh.strip().lower(), level_3_en.strip().lower())
        candidates = self._paths_by_level3_label.get(level3_key) or list(self.iter_resolved_paths())
        if not candidates:
            return None

        for path in candidates:
            if not self._label_matches(level_3_zh, level_3_en, path.level3_zh, path.level3_en):
                continue
            if level_2_zh or level_2_en:
                if not self._label_matches(level_2_zh, level_2_en, path.level2_zh, path.level2_en):
                    continue
            if level_1_zh or level_1_en:
                if not self._label_matches(level_1_zh, level_1_en, path.level1_zh, path.level1_en):
                    continue
            return path

        for path in candidates:
            if self._label_matches(level_3_zh, level_3_en, path.level3_zh, path.level3_en):
                return path
        return None

    def to_taxonomy_document(self) -> SectorTaxonomyDocumentResponse:
        """Build frontend-compatible L1/L2/L3 taxonomy from cached sector paths."""
        l1_index: dict[str, dict[str, object]] = {}

        for path in self.paths:
            l1 = path.sector_level_1
            l2 = path.sector_level_2
            l3 = path.sector_level_3

            l1_entry = l1_index.setdefault(
                l1.sector_id,
                {"node": l1, "l2": {}},
            )
            l2_map = l1_entry["l2"]
            assert isinstance(l2_map, dict)
            l2_entry = l2_map.setdefault(
                l2.sector_id,
                {"node": l2, "l3": {}},
            )
            l3_map = l2_entry["l3"]
            assert isinstance(l3_map, dict)
            l3_map[l3.sector_id] = l3

        level_1: List[SectorTaxonomyL1Item] = []
        for l1_id in sorted(
            l1_index.keys(),
            key=lambda sid: (
                (
                    l1_index[sid]["node"].name.en  # type: ignore[union-attr]
                    or l1_index[sid]["node"].name.zh  # type: ignore[union-attr]
                ).lower(),
                sid,
            ),
        ):
            l1_entry = l1_index[l1_id]
            l1_node: SectorNode = l1_entry["node"]  # type: ignore[assignment]
            l2_map = l1_entry["l2"]
            assert isinstance(l2_map, dict)

            level_2: List[SectorTaxonomyL2Item] = []
            for l2_id in sorted(
                l2_map.keys(),
                key=lambda sid: (
                    (l2_map[sid]["node"].name.en or l2_map[sid]["node"].name.zh).lower(),  # type: ignore[index]
                    sid,
                ),
            ):
                l2_entry = l2_map[l2_id]
                l2_node: SectorNode = l2_entry["node"]  # type: ignore[assignment]
                l3_map = l2_entry["l3"]
                assert isinstance(l3_map, dict)

                level_3 = [
                    SectorTaxonomyL3Item(
                        id=l3_node.sector_id,
                        name=l3_node.name,
                        definition=_optional_bilingual(l3_node.description),
                    )
                    for l3_node in _sort_nodes(list(l3_map.values()))
                ]
                level_2.append(
                    SectorTaxonomyL2Item(
                        id=l2_node.sector_id,
                        name=l2_node.name,
                        description=_optional_bilingual(l2_node.description),
                        level_3=level_3,
                    )
                )

            level_1.append(
                SectorTaxonomyL1Item(
                    id=l1_node.sector_id,
                    name=l1_node.name,
                    description=_optional_bilingual(l1_node.description),
                    level_2=level_2,
                )
            )

        return SectorTaxonomyDocumentResponse(level_1=level_1)

    def list_by_level(self, level: int) -> List[SectorNode]:
        return [node for node in self.nodes if node.level == level]

    @property
    def level_1(self) -> List[SectorNode]:
        return self.list_by_level(1)

    @property
    def level_2(self) -> List[SectorNode]:
        return self.list_by_level(2)

    @property
    def level_3(self) -> List[SectorNode]:
        return self.list_by_level(3)

    def stats(self) -> Dict[str, Any]:
        return {
            "loaded": self.loaded,
            "total_nodes": len(self.nodes),
            "level_1": len(self.level_1),
            "level_2": len(self.level_2),
            "level_3": len(self.level_3),
            "paths": len(self.paths),
        }
