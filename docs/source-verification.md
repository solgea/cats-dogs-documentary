# Source verification

## Standard

A package is source-checked only when the research record can be audited without
trusting the narration. This means separating:

- **Evidence:** what the cited source actually reports.
- **Interpretation:** what the package concludes from that evidence.
- **Hypothesis:** a possible mechanism that was not directly measured.
- **Anecdote:** a popular story, owner report, or illustrative example.
- **Unknown:** a question the source does not answer.

Every package in this repository records `verification.method`,
`verification.source_access`, `verification.myth_or_anecdote`,
`verification.uncertainties`, a separate evidence summary for each source, and a
verdict for every claim.

## Allowed sources

`config/sources.json` is authoritative. The default hierarchy is:

| Tier | Meaning | Examples of acceptable source type |
| --- | --- | --- |
| 1 | Peer-reviewed primary research or scholarly review | Journal article with DOI and/or PMID |
| 2 | University, veterinary school, museum, or government research body | Cornell Vet, NCBI, Smithsonian research pages |
| 3 | Reputable animal welfare or professional veterinary organization | AVMA, ASPCA, RSPCA, iCatCare, AAHA |
| 4 | Credible edited journalism or historical reference, context only | BBC, Guardian, NYT, National Geographic |

Tier 1 sources must include a DOI or PMID. A DOI URL is accepted only when the
DOI is also recorded in the source record. All source URLs must be HTTPS, use an
allowed domain, and have an accessed date no later than today.

The following are never evidence, even if they link to a real paper: Wikipedia,
Reddit, Quora, Pinterest, social posts, Medium/Substack essays, content farms,
and YouTube videos. The full banned-domain list is in `config/sources.json`.

## Verification workflow

1. Search for the primary paper or an official institutional summary. Use the
   publisher record, PubMed, or PMC to confirm title, authors, year, journal,
   volume, issue, pages, DOI, and PMID.
2. Read enough of the method and results to state the sample, manipulation, and
   measured outcome accurately. Do not rely only on a press release.
3. Write `evidence` as a factual summary with numbers only when confirmed. Write
   `limitations` separately; do not hide uncertainty in the narration.
4. Convert each narration assertion into a claim in `package.json`. Give it an
   evidence level and a limit.
5. Add one `claim_checks` entry per claim with a verdict of `supported`,
   `partially_supported`, or `interpretation`, plus notes explaining the match.
6. Run QA. Source-domain, DOI/PMID, citation, claim coverage, and metadata checks
   are fail-closed.

## Example distinction

For the 2009 guilty-look study:

- **Supported:** fourteen dogs were tested; owners were sometimes given incorrect
  information about whether the dog had eaten; the guilty look increased with
  scolding rather than actual consumption.
- **Interpretation:** the look is not reliable evidence of guilt.
- **Not supported:** dogs never feel guilt.
- **Unknown:** whether any dog in the study experienced guilt.

The narration must preserve that boundary. A stronger, tidier sentence can be a
false sentence.

## Citation format

Generated citations use author-year-title-journal details and the source URL.
Example:

> Horowitz, A. (2009). Disambiguating the 'guilty look': salient prompts to a
> familiar dog behaviour. Behavioural Processes 81(3), 447-452.
> https://doi.org/10.1016/j.beproc.2009.03.014

The generated `metadata.json` also carries the source list. Descriptions use a
`Sources:` heading so a viewer can find the evidence. Do not add a citation that
is not present in `research.json`.

## No invented evidence

Do not invent a statistic, quotation, study, author, journal, page number, DOI,
PMID, sample size, or finding. Do not "repair" a citation from memory. If a
detail cannot be verified, remove the detail or state the uncertainty. An
uncited plausible sentence is still unsupported.

## Reviewing a failed source check

Common failures and the correct response:

| Failure | Response |
| --- | --- |
| Domain not allowed | Find the primary/institutional source; do not whitelist a content farm casually |
| Tier 1 lacks DOI/PMID | Add a verified identifier or reclassify/remove the source |
| Claim has no source | Add a source that actually supports it, or soften/remove the claim |
| Source unused by any claim | Remove it or connect it to a real claim |
| Citation mismatch | Re-check the publisher/PubMed record; correct all fields |
| Unsupported certainty phrase | Rewrite the sentence to match the evidence |

Never edit a QA report to turn a failure into a pass. Fix the source or the copy,
then rebuild.
