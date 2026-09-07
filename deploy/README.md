# GitHub Pages and the corpus API

The source repository is [V4ldeSalnikov/scandinavian-dynaword-website](https://github.com/V4ldeSalnikov/scandinavian-dynaword-website).
The intended Pages URL is `https://v4ldesalnikov.github.io/scandinavian-dynaword-website/`.

Pages hosts the static React frontend. It cannot run FastAPI, DuckDB, Tantivy, or the semantic-vector searches. Public deployment therefore needs a separate HTTPS API host with the complete prepared indexes. A frontend without that host would not meet the full-corpus requirement.

## Hugging Face backend

The selected deployment uses a CPU Basic Docker Space for the API and GitHub
Pages for the frontend. See [Hugging Face deployment](huggingface/README.md) for
the pinned artifact repository, image build, hardware limits and update steps.
The following Compose setup remains an alternative for a persistent Linux server.

## Alternative API server

Use a Linux server with persistent SSD storage, Docker Compose, a public hostname, and ports 80/443 available. A practical starting allocation for the current implementation is 4 CPU cores, 16 GB RAM, and at least 50 GB free storage; measure real traffic before choosing a long-term allocation. The complete local cache is approximately 30 GB. This repository does not provision or purchase a server.

1. Clone this repository on the server.
2. Copy the existing `.cache/` contents to a persistent directory, preserving the snapshot as a unit. Alternatively, reproduce it with the preparation commands in the root README. Do not commit corpus files to Git or rebuild 30 GB of indexes in the Pages workflow.
3. Ensure the data files are readable by container user 10001, including the existing `texts/` directory.
4. Copy `deploy/.env.example` to `deploy/.env`, set `API_DOMAIN` and `DYNAWORD_DATA_DIR`, and point the hostname's DNS at the server.
5. Run:

```sh
docker compose --env-file deploy/.env -f deploy/compose.yml up --build -d
```

Caddy obtains HTTPS certificates. Only Caddy publishes ports; the API is internal to the Compose network. The API mounts the prepared corpus read-only. Keep a single API worker so corpus arrays and caches are not duplicated across processes.

Verify the public service, including browser access from Pages:

```sh
VITE_API_BASE_URL=https://your-api-hostname \
PAGES_ORIGIN=https://v4ldesalnikov.github.io \
python3 scripts/check_public_api.py
```

## GitHub Pages

Under **Settings → Pages**, choose **GitHub Actions** as the publishing source.
Under **Settings → Secrets and variables → Actions → Variables**, set the repository variable:

```text
VITE_API_BASE_URL=https://your-api-hostname
```

This value is a public origin, not a secret. Do not put API credentials in Vite variables; they are embedded in the public JavaScript.

Run **Actions → Validate and deploy GitHub Pages → Run workflow**, or push to `main`. The workflow checks the API fixtures, builds the frontend, verifies public corpus/search/topic readiness and CORS, and publishes `web/dist/` using GitHub's Pages actions. Pull requests run the tests and build without deploying. When the API URL is unset, validation runs and deployment is explicitly skipped; the site is not published with a broken connection.

The frontend uses relative asset paths, so it works under the repository subdirectory. Its data requests use the separately configured API origin. The local Vite proxy continues to work when the variable is unset.

## Verification limits

The workflow builds the API container and checks startup against an empty read-only data mount. The complete corpus and HTTPS configuration still need verification on the selected host; this Mac workspace has no Docker daemon. Backend tests and a frontend build do not prove public deployment. Confirm the GitHub deployment succeeded and visit the public URL after API provisioning.
