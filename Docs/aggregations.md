# Claims aggregations

## Facet by provider

Groups all claims by `billingProvider.providerId` and returns one document per provider with count and date range.

### Pipeline (MongoDB shell / Compass)

```javascript
[
  // Optional: uncomment to filter by service date (overlap semantics)
  // { $match: { serviceEndDate: { $gte: ISODate("2002-01-01") }, serviceBeginDate: { $lte: ISODate("2002-12-31") } } },
  { $group: {
      _id: "$billingProvider.providerId",
      count: { $sum: 1 },
      minServiceBeginDate: { $min: "$serviceBeginDate" },
      maxServiceEndDate: { $max: "$serviceEndDate" }
  }},
  { $sort: { count: -1 } },
  { $project: {
      _id: 0,
      providerId: "$_id",
      count: 1,
      minServiceBeginDate: 1,
      maxServiceEndDate: 1
  }}
]
```

### Python

- **Pipeline builder:** `src.aggregations.claims_facet_by_provider_pipeline(service_date_start=None, service_date_end=None, include_sample_claim_ids=False, sample_size=3)`
- **Run:** `src.aggregations.run_claims_facet_by_provider(collection, ...)`
- **Script:** `python -m scripts.run_facet_by_provider [--date-start YYYY-MM-DD] [--date-end YYYY-MM-DD] [--limit N] [--json]`
