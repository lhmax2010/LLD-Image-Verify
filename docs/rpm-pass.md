# Published RPM coverage

This pass covers runtime RPMs outside the archived ARM image package lists for each release, all published x86_64 runtime RPMs, and their available debuginfo repositories. It uses the Base and Unified snapshots from both rounds. Identical archive checksums share a payload receipt. Repository entries retain their own snapshot, architecture, NEVRA, URL and recorded checksum. [Inventory](../data/rpm-inventory.csv.gz) · [Coverage by snapshot and architecture](../data/rpm-coverage.csv)

<!-- rpm-coverage-begin -->
This published pass inspected **32,626 / 32,628** repository RPM records.
The table records 0 pending entries and 2 acquisition or parsing errors.
Pending and error rows carry the incomplete verdict.

| Architecture | Runtime RPMs scanned | Debuginfo RPMs scanned |
| --- | ---: | ---: |
| aarch64 | 7,296 / 7,296 | 3,576 / 3,576 |
| armv7l | 7,164 / 7,164 | 3,564 / 3,564 |
| x86_64 | 6,994 / 6,994 | 3,544 / 3,544 |
| noarch | 488 / 490 | — |

| Runtime verdict | Per inspected runtime RPMs |
| --- | ---: |
| all-LLD | 9,410 / 21,942 |
| mixed | 8 / 21,942 |
| non-LLD | 12 / 21,942 |
| open | 2,384 / 21,942 |
| no native files | 10,128 / 21,942 |
<!-- rpm-coverage-end -->

All 32,628 repository entries map to checksum-verified archives. The two incomplete entries are the Base `golang-tests-0:1.25.3-1.1.noarch` RPMs. Both contain `test-badbase.zip` and `test-baddirsz.zip` under Go's archive/zip test data. The first fails ZIP file-header parsing and the second fails central-directory parsing. The RPM verdict table retains both file-level errors and the archive checksums. [RPM verdicts and parse errors](../data/rpm-pass.csv.gz)

| Data | Coverage |
| --- | --- |
| [RPM verdicts](../data/rpm-pass.csv.gz) | One row per repository RPM entry. Runtime verdicts distinguish confirmed LLD, mixed and confirmed other evidence, open linker identity, and zero observed native payload files. Debuginfo RPM rows report inspection as debug evidence. |
| [Runtime ELF evidence](../data/rpm-elf-evidence.csv.gz) | Native payloads with file SHA256, Build ID, direct linker evidence and the matched debug member where available. |
| [Debuginfo ELF evidence](../data/debuginfo-evidence.csv.gz) | Parsed debug member identities, comments, GNU Gold section presence and CRC32. |

The payload pass checks the archive digest against repository metadata. It reads regular RPM payload files and native members of the same ZIP-family containers used by the image scan. This scope treats a rootstrap or other bundled tarball as a package payload file. It counts payload entries carrying the native bytes when a cpio hardlink group shares one body. Only explicit linker markers in an ELF or matched debuginfo can confirm the linker in this pass. A missing marker stays open. The `no native files` verdict describes the successfully inspected payload under this scope.

```bash
mkdir -p results/rpm-replay/cache
python3 scripts/sweep-rpms.py \
  --output results/rpm-replay --cache results/rpm-replay/cache \
  --inventory data/image-rpm-membership.csv --retry-errors
python3 scripts/summarize-rpm-pass.py \
  --scan results/rpm-replay --output results/rpm-replay/rpm-coverage.csv
```

One full pass lists about 79 GB before checksum deduplication. The scanner retains the completed receipts and resumes interrupted archive fetches within its cache.
