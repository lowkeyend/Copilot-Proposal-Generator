"""Local-first persistence for proposals, versions, and templates.

Everything is stored as JSON on disk under STORAGE_DIR. The interface is
deliberately small and backend-agnostic so a Supabase-backed implementation
can be dropped in later without touching the API/agents.

Layout:
    storage/
      proposals/<proposal_id>.json     # ProposalRecord (with version history)
      templates.json                   # list[ProposalTemplate]
      pattern_registry.json            # discovered patterns (see pattern_service)
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.models.schemas import (
    ProposalRecord,
    ProposalTemplate,
    ProposalVersion,
    SectionResult,
)

_lock = threading.Lock()


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.settings.ensure_dirs()

    # ---- paths ----
    @property
    def proposals_dir(self) -> Path:
        return self.settings.storage_path / "proposals"

    @property
    def templates_file(self) -> Path:
        return self.settings.storage_path / "templates.json"

    def _proposal_path(self, proposal_id: str) -> Path:
        return self.proposals_dir / f"{proposal_id}.json"

    # ---- proposals ----
    def save_proposal(self, record: ProposalRecord) -> ProposalRecord:
        with _lock:
            self.proposals_dir.mkdir(parents=True, exist_ok=True)
            self._proposal_path(record.proposal_id).write_text(
                record.model_dump_json(indent=2), encoding="utf-8"
            )
        return record

    def get_proposal(self, proposal_id: str) -> Optional[ProposalRecord]:
        path = self._proposal_path(proposal_id)
        if not path.exists():
            return None
        return ProposalRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_proposals(self) -> list[ProposalRecord]:
        records: list[ProposalRecord] = []
        if not self.proposals_dir.exists():
            return records
        for f in sorted(self.proposals_dir.glob("*.json")):
            try:
                records.append(
                    ProposalRecord.model_validate_json(f.read_text(encoding="utf-8"))
                )
            except Exception:
                continue
        records.sort(key=lambda r: r.updated_at, reverse=True)
        return records

    def add_version(
        self,
        proposal_id: str,
        sections: list[SectionResult],
        label: str = "",
    ) -> Optional[ProposalVersion]:
        record = self.get_proposal(proposal_id)
        if record is None:
            return None
        version = ProposalVersion(
            label=label or f"Version {len(record.versions) + 1}",
            sections=sections,
        )
        record.versions.append(version)
        record.updated_at = version.created_at
        self.save_proposal(record)
        return version

    def restore_version(
        self, proposal_id: str, version_id: str
    ) -> Optional[ProposalVersion]:
        """Return a deep copy of a stored version (frontend swaps it in)."""
        record = self.get_proposal(proposal_id)
        if record is None:
            return None
        for v in record.versions:
            if v.version_id == version_id:
                return v
        return None

    def duplicate_version(
        self, proposal_id: str, version_id: str
    ) -> Optional[ProposalVersion]:
        record = self.get_proposal(proposal_id)
        if record is None:
            return None
        src = next((v for v in record.versions if v.version_id == version_id), None)
        if src is None:
            return None
        clone = ProposalVersion(
            label=f"{src.label} (copy)",
            sections=[SectionResult(**s.model_dump()) for s in src.sections],
        )
        record.versions.append(clone)
        record.updated_at = clone.created_at
        self.save_proposal(record)
        return clone

    # ---- templates ----
    def load_templates(self) -> list[ProposalTemplate]:
        if not self.templates_file.exists():
            return []
        try:
            raw = json.loads(self.templates_file.read_text(encoding="utf-8"))
            return [ProposalTemplate.model_validate(t) for t in raw]
        except Exception:
            return []

    def save_templates(self, templates: list[ProposalTemplate]) -> None:
        with _lock:
            self.templates_file.write_text(
                json.dumps([t.model_dump() for t in templates], indent=2),
                encoding="utf-8",
            )

    def upsert_template(self, template: ProposalTemplate) -> ProposalTemplate:
        templates = self.load_templates()
        for i, t in enumerate(templates):
            if t.id == template.id:
                templates[i] = template
                self.save_templates(templates)
                return template
        templates.append(template)
        self.save_templates(templates)
        return template

    def delete_template(self, template_id: str) -> bool:
        templates = self.load_templates()
        new = [t for t in templates if t.id != template_id]
        if len(new) == len(templates):
            return False
        self.save_templates(new)
        return True


_storage_singleton: Optional[StorageService] = None


def get_storage() -> StorageService:
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = StorageService()
    return _storage_singleton
