# Labelling answers for judge calibration (MVP 1e)

`labels_<date>.csv` has one row per answer: the question, the reference answer from the golden set, the assistant's
answer (its claims, each with the quote it cites, or a refusal), and links to the cited PDF pages. Fill in the two
`owner_` columns, and `owner_note` if you want. The judge gets exactly the same rubric. Don't open
`judge_verdicts_*.jsonl` (it appears here only after you finish) until your labels are saved.

## owner_supported: yes / no / n/a

Is every claim backed by its own quote?

- **yes**: every claim says only what its quote says. The citation next to the quote (ticker, fiscal year, page)
  counts as part of the quote, so "BBCA's NIM in 2025 was 5.7%" with quote "NIM 5,7%" (BBCA FY2025 p.16) is yes.
  Rewording, translating between English and Bahasa, and number formats (5,7% = 5.7%) are fine.
- **no**: at least one claim adds a fact, number, period, unit or comparison its quote and citation don't state, or
  says something different (for example a figure the quote gives for another year).
- **n/a**: the answer is a refusal or an error, with no claims.

Judge each claim against its own quote only: not against the reference, the PDF, or what you know. The PDF links are
there for `owner_correct`. (A quote may continue on the page after the linked one.)

## owner_correct: yes / no

Does the answer get the question right, compared with the reference?

- **yes**: it states the key fact the question asks for (the reference's main figure, name or point) and contradicts
  nothing in the reference. Missing secondary details is still yes.
- **no**: the key fact is missing, wrong, or for the wrong company, year or scope; or it refuses (or shows an error)
  although the reference gives an answer.
- When the reference says the report doesn't contain the answer: **yes** if the assistant refused or said it couldn't
  find it, **no** if it answered anyway.

Numbers are equal if they differ only in format or in rounding the reference also uses.

## Saving

Save as CSV in Excel (any CSV option; comma or semicolon both work). Values other than yes / no / n/a are reported
back by row so you can fix them.
