# INTEGRITY_CHECKS.md

This document contains repeatable MongoDB validation queries that must be run after every batch apply to ensure referential integrity, uniqueness compliance, and contract alignment.

Run all queries in `mongosh` against the `porsche` database.

---

## 1. Orphan Detection

### 1.1 specSheets referencing missing trims

```js
use porsche

db.specSheets.aggregate([
  { $lookup: { from: "trims", localField: "trimId", foreignField: "_id", as: "t" } },
  { $match: { $expr: { $eq: [{ $size: "$t" }, 0] } } },
  { $project: { _id: 1, trimId: 1, year: 1, market: 1 } }
]).toArray()
```

Expected result: `[]`

---

### 1.2 trimFeatures referencing missing trims

```js
db.trimFeatures.aggregate([
  { $lookup: { from: "trims", localField: "trimId", foreignField: "_id", as: "t" } },
  { $match: { $expr: { $eq: [{ $size: "$t" }, 0] } } },
  { $project: { _id: 1, trimId: 1, year: 1, market: 1 } }
]).toArray()
```

Expected result: `[]`

---

### 1.3 characterScores referencing missing trims

```js
db.characterScores.aggregate([
  { $lookup: { from: "trims", localField: "trimId", foreignField: "_id", as: "t" } },
  { $match: { $expr: { $eq: [{ $size: "$t" }, 0] } } },
  { $project: { _id: 1, trimId: 1, year: 1, market: 1 } }
]).toArray()
```

Expected result: `[]`

---

## 2. Natural-Key Uniqueness Checks

These validate compound uniqueness constraints beyond `_id`.

### 2.1 Duplicate trims by natural key

```js
db.trims.aggregate([
  {
    $group: {
      _id: {
        makeId: "$makeId",
        modelId: "$modelId",
        generationId: "$generationId",
        trimName: "$trimName",
        bodyStyle: "$bodyStyle"
      },
      n: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { n: { $gt: 1 } } }
]).toArray()
```

Expected result: `[]`

---

### 2.2 Duplicate specSheets by (trimId, year, market)

```js
db.specSheets.aggregate([
  {
    $group: {
      _id: { trimId: "$trimId", year: "$year", market: "$market" },
      n: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { n: { $gt: 1 } } }
]).toArray()
```

Expected result: `[]`

---

### 2.3 Duplicate characterScores by (trimId, year, market, modelVersion)

```js
db.characterScores.aggregate([
  {
    $group: {
      _id: {
        trimId: "$trimId",
        year: "$year",
        market: "$market",
        modelVersion: "$modelVersion"
      },
      n: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { n: { $gt: 1 } } }
]).toArray()
```

Expected result: `[]`

---

## 3. Coverage Completeness Checks

These ensure 1:1 coverage between trims and year-level documents.

### 3.1 Missing trimFeatures for existing specSheets

```js
db.specSheets.aggregate([
  {
    $lookup: {
      from: "trimFeatures",
      let: { t: "$trimId", y: "$year", m: "$market" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$trimId", "$$t"] },
                { $eq: ["$year", "$$y"] },
                { $eq: ["$market", "$$m"] }
              ]
            }
          }
        }
      ],
      as: "tf"
    }
  },
  { $match: { $expr: { $eq: [{ $size: "$tf" }, 0] } } },
  { $project: { trimId: 1, year: 1, market: 1 } }
]).toArray()
```

Expected result: `[]`

---

### 3.2 Missing characterScores for existing specSheets

```js
db.specSheets.aggregate([
  {
    $lookup: {
      from: "characterScores",
      let: { t: "$trimId", y: "$year", m: "$market" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$trimId", "$$t"] },
                { $eq: ["$year", "$$y"] },
                { $eq: ["$market", "$$m"] }
              ]
            }
          }
        }
      ],
      as: "cs"
    }
  },
  { $match: { $expr: { $eq: [{ $size: "$cs" }, 0] } } },
  { $project: { trimId: 1, year: 1, market: 1 } }
]).toArray()
```

Expected result: `[]`

---

## 4. Count Parity Check

If operating in single-year-per-trim MVP mode, all collections should match:

```js
db.trims.countDocuments()
db.specSheets.countDocuments()
db.trimFeatures.countDocuments()
db.characterScores.countDocuments()
```

In multi-year mode, specSheets/trimFeatures/characterScores may legitimately exceed trims.

---

## 5. Pre-Insert Safety Rule (Manual Verification)

Before inserting any new trim:

```js
db.trims.find({
  makeId: "mk_porsche",
  modelId: "md_911",
  generationId: "<GEN_ID>",
  trimName: "<TRIM_NAME>",
  bodyStyle: "<BODY_STYLE>"
}).toArray()
```

If this returns a document, reuse that `_id` for downstream documents.

---

End of integrity checklist.

---