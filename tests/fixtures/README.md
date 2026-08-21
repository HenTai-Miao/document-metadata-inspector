# Test Fixtures

## metadata.xls / metadata.xlt

- **Source:** Generated from a synthetic XLSX workbook created by openpyxl.
- **LibreOffice version:** 26.2.5.2 (`/opt/homebrew/bin/soffice`)
- **Conversion commands:**
  ```
  soffice --headless --convert-to xls --outdir /tmp /tmp/synthetic_metadata.xlsx
  soffice --headless --convert-to xlt --outdir /tmp /tmp/synthetic_metadata.xlsx
  ```
- **Source XLSX SHA-256:** `80d467a88904d4f18a4a99a1b0fd4ebbadd93c9ef35d17ec4fce11e61f81ee23`
- **Fixture SHA-256:** `34717f3029c9dde1794a57f5fe5e89b0bc0de6a197d7e2881569ed0b608c0523` (both .xls and .xlt)
- **Content:** All cells contain the word "synthetic". No user data.
- **Metadata fields:** creator=Alice Analyst, lastModifiedBy=Bob Reviewer, created=2024-03-15T09:30:00, modified=2024-06-20T14:45:00, company=Forensic Labs Inc., manager=Carol Manager, application=Synthetic Generator, title=Metadata Test Fixture, subject=TDD Verification, description=Controlled fixture for OLE adapter tests., keywords=test fixture metadata, category=Testing, contentStatus=Final, identifier=FIXTURE-001, language=en-US, revision=3, template=Normal, totalTime=120
- **No real credentials, PII, or business data are embedded.**
