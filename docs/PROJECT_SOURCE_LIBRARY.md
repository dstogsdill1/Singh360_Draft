# Project Source Library

Schema-V2 projects store source originals beneath `sources/` and metadata in `source_library.json`. Uploads accept PDF, common browser images, XLSX/XLSM, CSV, text, and common non-executable document formats. File names are normalized, extensions are allowlisted, paths are constrained to the project package, files are limited to 100 MB, and each upload receives a SHA-256 checksum and stable source ID.

Multiple files can be dropped together. Sources can be searched and filtered by type and status, previewed when the browser supports the media, opened, queued for conversion, versioned through supersession links, and archived. V1 does not permanently delete sources.

The Conversion Queue records review work. It does not run OCR or promote extracted information into project truth automatically.
