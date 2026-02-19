Context: Sales Engineer for MongoDB looking to build a customer-facing demonstration that shows off MongoDB's ability to quickly query and return large volumes of documents.  The scenario is an integration services between a healthcare provider and a pharmacy benefits manager; in this specific use case, we are storing claims as individual documents but the query request is based on the provider (an attribute of the claims document) with an optional date rate.  The success of this project is based on performance and price, so it is important to think through implementation options to be as fast as possible without unnecessarily adding more hardware.

Requirements:
- Use Python as a development language
- Use MongoDB as the operational data store
- Generate sample data based on the docs/sample.json; this currently has all the fields as null, but please infer each fields intention and generate meaningful data
    - Data should have intentional overlap of providers and dates as the intention is to do performance testing on larger document bases
    - Ensure that claims records are generated so that certain providers meet key threshold volumes of claims to allow for testing; there should be at least 1 provider for each of the following volume counts: 1000 claims per provider, 5000 claims per provider, 10000 claims per provider, 50000 claims per provider, 100000 claims per provider, 500000 claims per provider, and 1000000 claims per provider
    - Goal is to have ~3000000 total claims distributed as per above bullet point
- Performance testing should focus on querying data by provider at large, and over a specific date range
    - It is important to be as optimal as possible, so please take that into account when designing indexes
    - Each query will also need to return the total count of documents associated with the query; please determine if this will be more performant via a count_documents() query or by faceting the response and using the facet metadata to get the total count
    - Pagination is a key component for this customer, so please enable keyset based pagination using searchBefore and searchAfter
- Leverage configuration files where possible; avoid having credentials and URI's scattered throughout the codebase
