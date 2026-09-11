# Data sources and licences

- NIST CSF 2.0 core: the NIST Cybersecurity and Privacy Reference Tool (CPRT) JSON export (`csf_2_0_0`), vendored as `src/csfcheck/data/csf-2.0-core.json` with its SHA-256 alongside. Public domain as a work of the US government. Withdrawn CSF 1.1 subcategories in the export are dropped, leaving 6 functions, 22 categories, 106 subcategories and 363 implementation examples.
- Target priorities: NIST SP 1300, NIST Cybersecurity Framework 2.0: Small Business Quick-Start Guide (https://doi.org/10.6028/NIST.SP.1300). The action texts in `quickstart.yaml` are shortened from the guide.
- Background on the gap in NGO cybersecurity: https://www.emerald.com/insight/content/doi/10.1108/TG-08-2024-0201/full/html
- No paid or third-party mapping data is used. The sample organisations in `samples/` are fictional.
