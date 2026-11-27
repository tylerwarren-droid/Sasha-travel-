# Where `agapi/spec/v1` came from

`agapi/spec/v1` is **EU's contract, not Sasha's**. It is vendored byte-identical with EU's own SHA256SUMS, and EU is its single writer. A Sasha ticket copies it and never edits it. Re-hashing a local edit would pass the check and prove nothing.

| | |
|---|---|
| **Vendored from** | `applied-diligence` **`d63b7b7906e46decf12f43c96a6b79239503065c`** (branch `main`) |
| **Source path** | `docs/agapi/v1/` (AgAPI core 1.3) |
| **Checksums** | EU's own `docs/agapi/v1/SHA256SUMS`, committed at that sha. Copied here unchanged; 32 files |
| **Same sha as** | agapi's `spec/v1` (CR 235, PR #192, `spec/VENDORED.md`) |
| **Vendored by** | Sasha 424, 27 Nov 2026 (`git archive` of the commit, never a working tree) |

**Recompute it:**

```sh
git -C <applied-diligence> worktree add /tmp/eu327 d63b7b7906e46decf12f43c96a6b79239503065c
diff -r /tmp/eu327/docs/agapi/v1 backend/agapi/spec/v1        # must be EMPTY
( cd backend/agapi/spec/v1 && shasum -a 256 -c SHA256SUMS )   # 32 files, 0 failures
```

**CI** (`.github/workflows/sasha-ci.yml`) runs that `shasum -c`, and `tests/test_agapi_v1_sasha.py` also requires that every file is listed with its sum and nothing extra is present. Both fail on any mismatch.

**To re-vendor:** take EU's next committed sha only. Replace the whole `v1/` directory from `git archive <sha> docs/agapi/v1`, then update the sha above.
