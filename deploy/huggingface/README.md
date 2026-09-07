# Hugging Face API and GitHub Pages frontend

The website runs on GitHub Pages. An API-only Docker Space serves the prepared
Danish corpus; there is no Space iframe or Gradio frontend in the website.

- Space: https://huggingface.co/spaces/V4ldeLund/danish-dynaword-api
- API origin: `https://v4ldelund-danish-dynaword-api.hf.space`
- Artifact repository: https://huggingface.co/datasets/V4ldeLund/danish-dynaword-explorer-index
- Website: https://v4ldesalnikov.github.io/scandinavian-dynaword-website/

## Hardware and storage

Use **CPU Basic**: 2 vCPU, 16 GB RAM, 50 GB ephemeral disk, no hourly compute
charge. The account already has PRO. This deployment does not request an
upgraded CPU, GPU, paid bucket or persistent disk. PRO does not prevent CPU
Basic sleeping after inactivity; the website retries its initial connection
automatically. Full-corpus semantic searches scan every usable document vector
and are more expensive than text search.

The serving snapshot is approximately 30 GB (decimal), including original
texts, metadata, full-text/vector indexes and topic assignments. It is stored
in a public Hub dataset repository. The image build downloads the pinned
snapshot and verifies every file's SHA-256 and size. Data lives in one image
layer; waking a container does not rerun the download script. Pulling the
image to a fresh machine can still delay a cold start. Never retrain topics or
rebuild the corpus during API startup.

HF references: [hardware](https://huggingface.co/docs/hub/spaces-gpus),
[Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker),
[storage](https://huggingface.co/docs/hub/spaces-storage).

## Reproduce or update

1. Prepare all local indexes using the root README. Keep the dataset revision,
   metadata database, text index, vectors and topics together.
2. Run `python3 scripts/package_runtime.py`. This stages only runtime files at
   `.cache/hf-runtime`, using hard links and checksums. Do not modify source
   indexes while uploading. Training caches and credentials are excluded.
3. Upload the generated `.gitattributes` **first**, in a separate commit. The
   custom Tantivy extensions must use Hub large-file storage even when small;
   otherwise the Hub may reject them as binary Git content. Then upload the
   directory using `huggingface_hub` `HfApi.upload_folder` or the Hub CLI.
   Authenticate through a local login or
   an interactive hidden prompt; never put a token in a shell argument,
   tracked file, Docker build argument or Vite variable.
4. Once every file has uploaded, set `runtime-source.json` here to the artifact
   repository and its immutable 40-character commit SHA. Partial uploads must
   not become the serving revision.
5. Run `python3 scripts/stage_hf_space.py`. Upload `.cache/hf-space` to a public
   Docker Space on CPU Basic. `SPACE.md` becomes its root `README.md`. The
   image build downloads and validates all files before starting one Uvicorn
   worker on port 8000. Changes limited to server code reuse the data layer.
6. Wait for the Space to report Running, then verify:

   ```sh
   VITE_API_BASE_URL=https://v4ldelund-danish-dynaword-api.hf.space \
   PAGES_ORIGIN=https://v4ldesalnikov.github.io \
   python3 scripts/check_public_api.py
   ```

7. Set the GitHub repository Actions variable `VITE_API_BASE_URL` to the API
   origin above and run the Pages workflow. Verify browsing, search, the map
   and the reader on the public site.

The running service downloads no private resources and needs no Hugging Face
token. Rotating a deployment token does not break the site. The public artifact
card and original source cards document licenses and attribution. Updating the
GitHub repository alone does not update Space code; repeat staging and uploading
when changing the backend. Frontend changes deploy through GitHub Actions.
