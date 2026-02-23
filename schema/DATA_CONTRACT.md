# DATA_CONTRACT.md
# revmatch — DATA CONTRACT (v1, US-only)

This document defines the canonical MongoDB data model and rules for **revmatch**.
All writes performed by Cursor/agents via MongoDB Atlas MCP tools must follow this contract exactly.

## Scope
- **Market:** US only (for now)
- **Database:** `porsche`
- **Goal:** deterministic, queryable vehicle trim/spec dataset suitable for comparisons, scoring, and filtering.
- **Non-goal:** storing raw review text or scraped copyrighted content.

---

## Database + Collections

**Database:** `porsche`

**Collections:**
- `makes`
- `models`
- `generations`
- `trims`
- `specSheets`
- `featureCatalog`
- `trimFeatures`
- `characterScores`
- `sourceRefs`

---

## Global Rules (MUST)

1. **US-only:** every `specSheets`, `trimFeatures`, `characterScores` document MUST include:
   - `market: "US"`
2. **Numeric typing:** all numeric fields MUST be stored as JSON numbers (not strings).
   - ✅ `394`
   - ❌ `"394"`
   - ❌ `"394 hp"`
3. **Deterministic IDs:** `_id` values MUST follow the ID conventions below.
4. **No duplicates:** do not violate unique index constraints.
5. **No empty placeholders in production data:** fields should be omitted if unknown (preferred) rather than `"TBD"` strings.
6. **Provenance required:** `specSheets.sourceRefIds` MUST include at least one valid `sourceRefs._id`.
7. **No copyrighted text:** do not store long excerpts from reviews/articles. Short internal notes are okay.

8. **Year validity:** for any `specSheets` / `trimFeatures` / `characterScores` document, the `year` MUST be within the parent trim's year range:
   - `trims.years.start <= year <= trims.years.end`
9. **Controlled vocabularies:** the following fields MUST use the enumerations defined in this contract (no ad-hoc variants):
   - `engine.aspiration`, `engine.configuration`, `drivetrain.drivenWheels`, `drivetrain.transmissions[].type`, `chassis.steering`

11. **Natural-key trim reuse (MANDATORY before insert):** before inserting any document into `trims`, agents MUST first check for an existing trim using the natural key `(makeId, modelId, generationId, trimName, bodyStyle)`. If a trim already exists with that natural key, agents MUST reuse the existing `_id` for all downstream documents (`specSheets`, `trimFeatures`, `characterScores`) and MUST NOT create a new trim with a different `_id`. This prevents uniqueness conflicts and downstream orphan documents.

---

## ID Conventions

All IDs are lowercase and snake_case.

### Make
- `_id`: `mk_<make>`
- Example: `mk_porsche`

### Model
- `_id`: `md_<make>_<model>`
- Example: `md_porsche_911`, `md_porsche_718_cayman`

### Generation
- `_id`: `gen_<make>_<code>`
- Example: `gen_porsche_982`, `gen_porsche_991_2`, `gen_porsche_992_1`, `gen_porsche_997_2`

### Trim
- `_id`: `tr_<make>_<model>_<gen>_<trim_key>`
- Examples:
  - `tr_porsche_718_cayman_982_gts_4_0`
  - `tr_porsche_911_991_2_carrera_s`
  - `tr_porsche_911_992_1_targa_4`

### Feature
- `_id`: `ft_<feature_key>`
- Examples:
  - `ft_pasm`
  - `ft_sport_chrono`
  - `ft_pse`
  - `ft_quattro` (future, for Audi)

### Source Reference
- `_id`: `src_<publisher>_<topic>_<year>_<hash_short>`
- Example: `src_porsche_718_2024_a1b2c3`

### Spec Sheet (year/market specific)
- `_id`: `sp_<trimId>_<year>_us`
- Example: `sp_tr_porsche_718_cayman_982_gts_4_0_2024_us`

### Trim Features (year/market specific)
- `_id`: `tf_<trimId>_<year>_us`

### Character Scores (versioned, year/market specific)
- `_id`: `cs_<trimId>_<year>_us_<modelVersion>`
- Example: `cs_tr_porsche_911_992_1_carrera_s_2024_us_v1_0_0`

## Required Index Constraints

MongoDB collections MUST enforce the following uniqueness constraints (via unique indexes). Cursor/agents MUST check these constraints before writing.

- `models`: unique on `(makeId, name)`
- `generations`: unique on `(makeId, modelId, code)`
- `trims`: unique on `(makeId, modelId, generationId, trimName, bodyStyle)`
- `specSheets`: unique on `(trimId, year, market)`
- `trimFeatures`: unique on `(trimId, year, market)`
- `characterScores`: unique on `(trimId, year, market, modelVersion)`
- `featureCatalog`: unique on `(name, family)`
- `sourceRefs`: unique on `(type, publisher, title)`

---

## Canonical Documents

## Controlled Vocabularies (Enums)

To prevent schema drift, the following fields MUST use these canonical values.

### `engine.aspiration`
- `NA`
- `Turbo`
- `Supercharged`

### `engine.configuration`
- `F4`
- `F6`
- `I3`
- `I4`
- `I5`
- `I6`
- `V6`
- `V8`
- `V10`
- `V12`
- `Electric`

### `drivetrain.drivenWheels`
- `RWD`
- `AWD`
- `FWD`

### `drivetrain.transmissions[].type`
- `Manual`
- `PDK`
- `DCT`
- `Automatic`

### `chassis.steering`
- `Hydraulic`
- `EPS`

### `makes`
Required fields:
- `_id` (string)
- `name` (string)
Optional:
- `country` (string)
- `aliases` (string[])

Example:
```json
{
  "_id": "mk_porsche",
  "name": "Porsche",
  "country": "DE",
  "aliases": ["Porsche AG"]
}
```

---

## specSheets

### drivetrain (object)
- `drivenWheels` (string): `"RWD"`, `"AWD"`, or `"FWD"`
- `transmissions` (array of objects)

Each transmission:
- `type` (string): `"Manual"`, `"PDK"`, `"DCT"`, `"Automatic"`
- `gears` (number)

---

## chassis (object)
- `steering` (string): `"Hydraulic"` or `"EPS"` (use only these values)