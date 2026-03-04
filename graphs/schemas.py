from pydantic import BaseModel, Field


# === Stage 1: Per-article extraction ===

class ExtractedEntity(BaseModel):
    name: str = Field(description="Canonical full name, e.g. 'Xi Jinping', 'United States Department of Defense'")
    type: str = Field(description="One of: Person, Organization, Country, Location, Event, Policy, Technology, Economic_Indicator, Military_Asset, Resource")
    aliases: list[str] = Field(default_factory=list, description="Known aliases, acronyms, or short forms, e.g. ['PRC', 'China'] for 'People's Republic of China'")
    confidence: float = Field(default=1.0, description="NER model confidence score (0.0–1.0). Used to decide if LLM should verify the entity type.")


class ExtractedRelation(BaseModel):
    source: str = Field(description="Canonical name of the source entity")
    target: str = Field(description="Canonical name of the target entity")
    relation: str = Field(description="Verb-phrase label, e.g. 'built_infrastructure_in', 'sanctions', 'supplies_chips_to'")
    confidence: float = Field(default=1.0, description="0.0 to 1.0 confidence")
    temporal: str | None = Field(default=None, description="Temporal marker if present: a date like '2024-03', or 'ongoing', 'announced', 'concluded'")
    causal: bool = Field(default=False, description="True if this is a cause-effect relationship")


class ExtractedEvent(BaseModel):
    name: str = Field(description="Short event name, e.g. 'Chinese base construction on Mischief Reef'")
    date: str = Field(description="Date or period: '2024-03', '2025-Q1', 'ongoing'")
    status: str = Field(description="One of: ongoing, concluded, announced, rumored")
    entities: list[str] = Field(description="Names of entities involved in this event")


class ArticleExtraction(BaseModel):
    entities: list[ExtractedEntity] = Field(description="Entities mentioned in this article, max 15")
    relations: list[ExtractedRelation] = Field(description="Typed directional relationships, max 20")
    events: list[ExtractedEvent] = Field(default_factory=list, description="Named events with temporal markers, max 5")


# === Stage 1b: LLM enrichment (post-GLiNER2) ===

class RelationEnrichment(BaseModel):
    source: str = Field(description="Source entity name — must match exactly from the pre-extracted relations")
    target: str = Field(description="Target entity name — must match exactly from the pre-extracted relations")
    relation: str = Field(description="Relation type — must match exactly from the pre-extracted relations")
    causal: bool = Field(default=False, description="True if this is a cause-effect relationship")
    temporal: str | None = Field(default=None, description="Temporal marker: '2024-03', 'ongoing', 'announced', 'concluded', or null")


class LLMEnrichment(BaseModel):
    relation_enrichments: list[RelationEnrichment] = Field(
        default_factory=list,
        description="Causal and temporal enrichments for the pre-extracted relations",
    )
    events: list[ExtractedEvent] = Field(
        default_factory=list,
        description="Named events with temporal markers, max 5",
    )


# === Stage 1c: LLM entity canonicalization ===

class CanonicalizedEntity(BaseModel):
    original: str = Field(description="The original entity name as extracted (exact match)")
    canonical: str = Field(description="The canonical full name, e.g. 'Xi Jinping', 'United States', 'People's Liberation Army'")
    corrected_type: str | None = Field(default=None, description="Corrected entity type if the original was wrong. One of: Person, Organization, Country, Location, Policy, Technology, Economic_Indicator, Military_Asset, Resource. Null if type is already correct.")
    aliases: list[str] = Field(default_factory=list, description="Known aliases, acronyms, or short forms, e.g. ['PRC', 'China'] for 'People's Republic of China'")


class CanonicalizationResult(BaseModel):
    entities: list[CanonicalizedEntity] = Field(description="Canonicalized entities with aliases")


# === Stage 2: Entity Resolution ===

class MergeDecision(BaseModel):
    canonical: str = Field(description="The canonical name to keep")
    merge_into: str = Field(description="The name to merge into canonical")
    confidence: float = Field(default=1.0)


class ResolutionBatch(BaseModel):
    merges: list[MergeDecision] = Field(description="List of entity pairs that refer to the same real-world entity")


# === Stage 3: Temporal (future) ===

class StateChange(BaseModel):
    entity: str = Field(description="Entity name")
    attribute: str = Field(description="What changed, e.g. 'oil_price_trend', 'diplomatic_status'")
    old_value: str | None = Field(default=None)
    new_value: str = Field(description="New state value")
    date: str = Field(description="When the change occurred")
