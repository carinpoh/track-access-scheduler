# Deploying to Google Cloud Run

This app is containerised (`Dockerfile`) and runs on **Google Cloud Run** — a
scalable, pay-per-use web service that fits the NebulaX "host on Google Cloud"
requirement. You get a public HTTPS URL like `https://track-access-xxxx.run.app`.

## Prerequisites (one-time)

1. **Activate your free GCP credits** at https://console.cloud.google.com
   (redeem the NebulaX credit coupon if provided).
2. **Create / select a project**, e.g. `nebulax-track-access`. Note its
   **Project ID**.
3. Install the **gcloud CLI**: https://cloud.google.com/sdk/docs/install
   (or use **Cloud Shell** in the browser — gcloud is preinstalled there).

## Option A — Deploy straight from source (simplest)

Cloud Run can build the container for you from the repo. From the project
folder (the one with the `Dockerfile`):

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

gcloud run deploy track-access \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --port 8080
```

- `--allow-unauthenticated` makes the app publicly reachable (judges need this).
- `--region asia-southeast1` is Singapore; pick the region closest to you.
- When it finishes, gcloud prints the **Service URL** — that is your
  submission URL.

## Option B — Build image, push to Artifact Registry, then deploy

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/track-access
gcloud run deploy track-access \
  --image gcr.io/YOUR_PROJECT_ID/track-access \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --memory 1Gi --port 8080
```

## Verify

Open the printed `*.run.app` URL. Tick "Use bundled sample instance" and click
**Run scheduler** — you should see the Compare A/B/C dashboard, Gantt chart,
topology map, and explainability, all rendering.

## Cost control

Cloud Run scales to zero when idle, so it only bills while handling requests —
well within the free credits for a demo/judging workload. Set
`--max-instances 2` if you want a hard ceiling.

## Local test of the container (optional)

```bash
docker build -t track-access .
docker run -p 8080:8080 track-access
# open http://localhost:8080
```
