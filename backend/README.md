# Evac-AI (Hackathon MVP)

Location-based Evac-AI that:

- Fetches **live alerts** (USA: NWS)
- Fetches **live weather** (Open-Meteo)
- Finds **nearby help** (Mapbox POI when `MAPBOX_ACCESS_TOKEN` is set; otherwise OSM Overpass)
- Generates an **AI crisis action plan** with **IBM watsonx.ai** (`POST /api/plan`)
- Optionally archives plans to **IBM Cloud Object Storage** (COS)
- Provides a single, mobile-friendly UI for demo

## Data sources (real-world)

### Live alerts
- USA: National Weather Service API: `https://www.weather.gov/documentation/services-web-api`
- Canada (optional add-on): ECCC RSS feeds: `https://weather.gc.ca/rss/`

### Nearby resources (places)
- OpenStreetMap Overpass API (via Overpass Turbo): `https://overpass-turbo.eu/`
- Overpass API docs: `https://wiki.openstreetmap.org/wiki/Overpass_API`
- Geocoding (postal/city → lat/lon): Nominatim: `https://nominatim.org/release-docs/latest/api/Overview/`

### Google Maps (recommended for “works anywhere”)
If you set `GOOGLE_MAPS_API_KEY`, the app will use:
- Google Geocoding API for `/api/geocode`
- Google Places Nearby Search for `/api/resources`

Export your key (don’t commit it):

```bash
export GOOGLE_MAPS_API_KEY="YOUR_KEY_HERE"
```

### Mapbox (recommended if avoiding paid Google billing)
If you set `MAPBOX_ACCESS_TOKEN`, the app will use:
- Mapbox Geocoding for `/api/geocode`
- **Mapbox Search Box API** (`/category`, `/forward`) for `/api/resources`, with Geocoding POI as a thin-result fallback (token must allow Search Box + Geocoding on `api.mapbox.com`)

```bash
export MAPBOX_ACCESS_TOKEN="YOUR_TOKEN_HERE"
```

### IBM (hackathon judging: “Use of IBM Technologies”)

Copy `.env.example` to `.env` and fill in values (never commit `.env`).

**watsonx.ai (text generation)** — used by `POST /api/plan` and the “AI action plan” panel in the UI.

- `IBM_CLOUD_API_KEY` — IBM Cloud API key (IAM). You can use `WATSONX_API_KEY` instead; the code treats them the same.
- `WATSONX_PROJECT_ID` — **Project GUID from a watsonx project that is associated with a Watson Machine Learning / watsonx runtime service instance** in your IBM Cloud account. A standalone or wrong project ID often returns IBM error `no_associated_service_instance_error`. Browse services in the [IBM Cloud catalog (search “watsonx”)](https://cloud.ibm.com/catalog?search=watsonx) and ensure your project is created in that linked environment.
- `WATSONX_URL` — regional ML endpoint, e.g. `https://us-south.ml.cloud.ibm.com` (must match your region).
- `WATSONX_MODEL_ID` — foundation model your project can run (default: `ibm/granite-3-8b-instruct`). Change if your project uses another entitled model.

If watsonx is missing, misconfigured, or returns an API error, `POST /api/plan` still returns **HTTP 200** with `source: "demo"` and `demo_fallback: true`: the same structured plan fields filled from your request (scenario, summaries). The UI shows a short banner so you know it is not live watsonx output.

**Check configuration (no secrets exposed):** `GET /api/ibm/status`

**IBM Cloud Object Storage (optional)** — check “Archive to IBM COS” in the UI or pass `"archive_to_cos": true` in `POST /api/plan`. COS is **not** required for watsonx text generation.

- `IBM_COS_ENDPOINT` — S3 API endpoint for your bucket region
- `IBM_COS_BUCKET` — bucket name
- `IBM_COS_RESOURCE_INSTANCE_ID` — COS **service instance** id (from service credentials)
- `IBM_COS_API_KEY` — optional; defaults to `IBM_CLOUD_API_KEY` if unset

Requires dependency: `ibm-cos-sdk` (see `requirements.txt`).

### Deploy on IBM Cloud (optional story for judges)

See **[Deploy (IBM Cloud Code Engine)](#deploy-ibm-cloud-code-engine)** below for building a container and running it on Code Engine (**IBM Cloud runtime + watsonx.ai + optional COS**).

### Official guidance sources (for RAG + citations)
Curate 10–30 official pages depending on scenarios (heat, smoke, flood):
- CDC extreme heat (US): `https://www.cdc.gov/extreme-heat/index.html`
- Red Cross preparedness: `https://www.redcross.org/get-help/how-to-prepare-for-emergencies.html`
- Health Canada heat: `https://www.canada.ca/en/health-canada/services/environmental-workplace-health/heat.html`

## Run locally

```bash
cd "/Users/milipatel/Desktop/Crisis Companion"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then open `http://127.0.0.1:8000/`.

## Deploy on Render (free tier)

Use the repo root [`render.yaml`](render.yaml) Blueprint (Docker + root `Dockerfile`) or create a Web Service manually with the same settings.

1. **Push this repository to GitHub** (or GitLab/Bitbucket supported by Render) so Render can clone it.

2. **Create the service on Render**
   - **Blueprint:** In the [Render Dashboard](https://dashboard.render.com), choose **New** → **Blueprint**, connect the repo, and select the branch that contains `render.yaml`. Render will prompt for each `sync: false` environment variable during setup.
   - **Web Service (manual):** **New** → **Web Service**, connect the same repo. Set **Environment** to **Docker**, and confirm the **Dockerfile path** is the root `Dockerfile` (default).

3. **Configure environment variables** in the service **Environment** tab to match **`.env.example`** (paste secrets in the dashboard; do not commit them). At minimum for live watsonx and Mapbox-backed geocoding/resources, set:
   - `MAPBOX_ACCESS_TOKEN`
   - `IBM_CLOUD_API_KEY` (or `WATSONX_API_KEY` as an alias; the app treats them the same)
   - `WATSONX_PROJECT_ID`
   - `WATSONX_URL` (e.g. `https://us-south.ml.cloud.ibm.com`)
   - `WATSONX_MODEL_ID` (e.g. `ibm/granite-3-8b-instruct`)
   - Optional IBM COS (archive-to-COS): `IBM_COS_ENDPOINT`, `IBM_COS_BUCKET`, `IBM_COS_RESOURCE_INSTANCE_ID`, `IBM_COS_API_KEY`

   Render injects **`PORT`** for web services; the root `Dockerfile` runs Gunicorn on `0.0.0.0:${PORT:-8080}`, so no extra port configuration is required.

   **Troubleshooting:** For **Internal Server Error**, check the service **Logs** on Render for the traceback and confirm **environment variables** are set. For **“No results” on address / ZIP search**, add **`MAPBOX_ACCESS_TOKEN`** in **Render → your service → Environment** (not only in a local `.env` file: `.env` is listed in **`.dockerignore`**, so it is **not** copied into the container and Render does not load it from the repo).

4. **Free tier behavior:** Free web instances **spin down after idle periods**; the **first request after idle can take tens of seconds** while the instance starts. This is expected on Render’s free tier.

5. **Custom domain (optional):** In the service settings, add a **Custom Domain** and follow Render’s DNS instructions if you want a hostname other than `*.onrender.com`.

**Blueprint note:** [`render.yaml`](render.yaml) sets `plan: free`, which Render’s [Blueprint spec](https://render.com/docs/blueprint-spec) allows for `type: web` services (including Docker). If your workspace or the creation flow rejects that value for Docker, create or edit the service in the dashboard and choose **Free** (or **Starter** if Free is unavailable), keeping the same `Dockerfile` and environment variables as above.

## Deploy (IBM Cloud Code Engine)

These steps assume you use a **Linux/amd64** container image (build on Intel/AMD Linux, macOS with Docker Desktop, or `docker build --platform linux/amd64` from Apple Silicon if your Code Engine region requires it).

1. **Install the IBM Cloud CLI and Code Engine plug-in** — follow IBM’s docs: [Install the IBM Cloud CLI](https://cloud.ibm.com/docs/cli?topic=cli-install-ibmcloud-cli) and [Setting up the Code Engine CLI](https://cloud.ibm.com/docs/codeengine?topic=codeengine-cli-install) (install the `code-engine`/`ce` plugin as described there).

2. **Log in and target your account context** — run `ibmcloud login` (or `ibmcloud login --sso`), then set your target resource group, for example:  
   `ibmcloud target -g Default`  
   (Replace `Default` with your resource group name.)

3. **Provision IBM Container Registry (ICR) namespace** (once per account/region) if you do not already have one — see [Getting started with IBM Cloud Container Registry](https://cloud.ibm.com/docs/Registry?topic=Registry-getting-started). Note your registry hostname (e.g. `us.icr.io`) and namespace.

4. **Build and push the image** from the project root (replace `REGION`, `NAMESPACE`, and `IMAGE_NAME` with yours):

   ```bash
   cd "/path/to/Crisis Companion"
   docker build -t REGION.icr.io/NAMESPACE/IMAGE_NAME:latest .
   ibmcloud cr region-set REGION
   ibmcloud cr login
   docker push REGION.icr.io/NAMESPACE/IMAGE_NAME:latest
   ```

5. **Create a Code Engine project and application** from that image — for example:

   ```bash
   ibmcloud ce project create --name evac-ai
   ibmcloud ce project select --name evac-ai
   ibmcloud ce application create \
     --name evac-ai-api \
     --image REGION.icr.io/NAMESPACE/IMAGE_NAME:latest \
     --registry-secret YOUR_ICR_PULL_SECRET \
     --port 8080
   ```

   Use `ibmcloud ce application create --help` for flags to attach registry credentials if you use a private ICR image. You can also start from **source build** in Code Engine (`--build-source`) if you prefer not to push from your laptop; the runtime command in this repo’s `Dockerfile` still applies.

6. **Set environment variables** to match **`.env.example`** (paste values in the console or CLI; do not commit secrets). At minimum for live watsonx and Mapbox-backed geocoding/resources, configure the variables listed there, e.g. `IBM_CLOUD_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`, `WATSONX_MODEL_ID`, and `MAPBOX_ACCESS_TOKEN`. Optional IBM COS variables from `.env.example` apply if you use archive-to-COS. Prefer **Code Engine secrets** for API keys and reference them as env vars on the application where possible.

7. **`PORT`** — Code Engine (and similar platforms) inject **`PORT`** for the HTTP port your process must listen on. The provided `Dockerfile` binds Gunicorn to `0.0.0.0:${PORT:-8080}` so you do not need to hard-code a port; keep **`--port 8080`** (or the same default you use in the image) aligned with your app’s default when `PORT` is unset locally.

8. **watsonx / Mapbox keys** — treat `IBM_CLOUD_API_KEY` (and any `WATSONX_*` IDs/URLs) and `MAPBOX_ACCESS_TOKEN` as **application environment variables or Code Engine secrets**, not as files in the image. After deploy, verify `GET /health` and `GET /api/ibm/status` on your application URL.

## API endpoints

- `GET /health`
- `GET /api/ibm/status`
- `GET /api/alerts/us?lat=..&lon=..`
- `GET /api/weather?lat=..&lon=..`
- `GET /api/resources?lat=..&lon=..&radius_km=10&types=shelter,clinic,hospital,food_bank,community_centre`
- `GET /api/geocode?q=New York, NY`
- `POST /api/plan` — JSON body: `lat`, `lon`, `location_display?`, `scenario`, `alerts_summary?`, `weather_summary?`, `resources_summary?`, `risk_summary?`, `archive_to_cos?`. Returns live watsonx (`source: "live"`) when configured and successful, otherwise a structured demo plan (`source: "demo"`, `demo_fallback: true`).

