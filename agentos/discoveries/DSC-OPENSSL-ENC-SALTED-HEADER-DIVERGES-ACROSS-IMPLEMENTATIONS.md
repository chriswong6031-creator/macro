---
key: OPENSSL-ENC-SALTED-HEADER-DIVERGES-ACROSS-IMPLEMENTATIONS
kind: landmine
verified_at: 2026-09-01
verified_by: >
  Adversarial-review probe on the control host (macro DR program, 2026-09-01): identical
  plaintext/pass/flags (`enc -aes-256-ctr -pbkdf2 -iter 600000 -md sha256 -S <hex>`)
  through /usr/bin/openssl (LibreSSL 3.3.6) vs Homebrew OpenSSL 3.0.13/3.2/3.3/3.6.3;
  end-to-end failure reproduced through control_plane/executive_dr.py pre-fix; fix pinned
  by tests/test_executive_dr.py -k cross_implementation (Mastermind 9ed1a2020246)
scope: [mastermind, macro, "ops/**", "control_plane/executive_dr.py"]
confidence: verified
claim: >
  `openssl enc` container framing is NOT portable across implementations even with an
  explicit `-S` salt: LibreSSL 3.3.6 (macOS /usr/bin/openssl) WRITES the 16-byte
  `Salted__<salt>` header and REQUIRES it on decrypt ("bad magic number" without it),
  while OpenSSL 3.x (Linux distros, Homebrew) OMITS the header with `-S` and does not
  strip one on decrypt — it "succeeds" (exit 0) on a LibreSSL-produced file and emits
  16-byte-shifted garbage. PBKDF2 key+IV derivation itself is byte-identical across
  implementations; ONLY the framing diverges. Consequence: a macOS-encrypted artifact is
  silently undecryptable on a Linux replacement host and vice versa — the exact
  disaster-recovery direction (Mac control host → clean Linux restore) fails while every
  same-platform test and same-platform CI drill stays green. Fixed in Executive DR V1 by
  storing ciphertext HEADERLESS (strip-and-verify on encrypt), feature-detecting the
  local binary's family once per process, and prepending the header only for
  header-expecting decrypters.
falsifier: >
  Re-run the probe: encrypt 100000 random bytes with `/usr/bin/openssl enc -aes-256-ctr
  -pbkdf2 -iter 600000 -md sha256 -S 8e5771c8ec4d88c3 -pass pass:x` and decrypt with an
  OpenSSL 3.x binary using identical flags — byte-identical round-trip output would
  falsify this. Also falsified for the codebase if
  `python3 -m pytest tests/test_executive_dr.py -k cross_implementation` (Mastermind)
  passes with the normalization code deleted.
so_what: >
  Never ship `openssl enc` output across hosts without owning the container framing
  yourself, and never accept a same-binary round-trip test (or a same-platform CI job) as
  portability evidence for subprocess-crypto — the test suite must run the two
  implementations against each other, which requires an injection seam for the binary
  path (MASTERMIND_DR_OPENSSL). When a restore fails LOCAL_CORRUPT on a different
  platform from the encryptor, check framing before suspecting disk corruption or
  tampering.
---

Found by the opus adversarial reviewer on the DR V1 vertical (review B1) after the
builder's 31-test suite and the CI drill both passed — both were structurally
same-binary. Full probe transcript in the review packet; fix in Mastermind PR #358.
