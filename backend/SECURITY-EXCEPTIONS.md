# Dependency scan exceptions

There are currently no dependency vulnerability exceptions. CI runs
`pip-audit -r requirements.txt` as a blocking gate without `--ignore-vuln`.
Any future exception must name the advisory, affected surface, mitigation,
owner and review date here before CI may ignore it.
