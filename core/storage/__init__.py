"""
core.storage package
---------------------
Storage Analyzer feature: recursive directory scanning and size
calculation, kept separate from the live system monitors (core.monitors)
since this is on-demand (user-triggered), not continuously polled.
"""