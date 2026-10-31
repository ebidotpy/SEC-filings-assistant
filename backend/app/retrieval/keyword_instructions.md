Extract 3–5 search terms from the user's query for Postgres English full-text search over SEC filing chunks.

Rules:

- Prefer concrete filing vocabulary: product and segment names, financial metrics, legal phrases, years, form types, and tickers.
- Omit filler and question words (for example: what, how, tell, compare, describe).
- Return short terms as they appear in filings. Preserve casing for names like iPhone and Data Center.
- When active filters are provided, do not repeat them as keywords. For example, skip the company name when ticker is filtered, skip the form type when form is filtered, and skip the year when fiscal_year is filtered.
- Each term should help match a filing passage. Avoid generic words that appear in almost every chunk.

Return exactly 3 to 5 terms.
