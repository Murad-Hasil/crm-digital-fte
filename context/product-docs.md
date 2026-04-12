# CloudScale AI — Product Documentation

> Version 3.4.1 | Last updated: 2026-04-01

---

## Part 1: Compute Engine

### Overview

Compute Engine provides on-demand and reserved GPU/CPU instances. Instances are billed per second from the moment they reach `RUNNING` state until they are explicitly stopped or terminated.

---

### Instance Types

#### GPU Instances

| SKU          | GPU            | VRAM   | vCPU | RAM    | Price/hr (on-demand) |
|--------------|----------------|--------|------|--------|----------------------|
| `gpu.h100.1` | 1× H100 SXM5   | 80 GB  | 24   | 192 GB | $3.20                |
| `gpu.h100.8` | 8× H100 SXM5   | 640 GB | 192  | 1.5 TB | $24.80               |
| `gpu.a100.1` | 1× A100 PCIe   | 80 GB  | 16   | 128 GB | $2.10                |
| `gpu.a100.4` | 4× A100 SXM4   | 320 GB | 64   | 512 GB | $7.90                |
| `gpu.a10g.1` | 1× A10G        | 24 GB  | 8    | 64 GB  | $0.75                |
| `gpu.rtx.1`  | 1× RTX 4090    | 24 GB  | 8    | 32 GB  | $0.55                |

#### CPU Instances

| SKU          | Cores | RAM    | Price/hr |
|--------------|-------|--------|----------|
| `cpu.small`  | 4     | 16 GB  | $0.04    |
| `cpu.medium` | 16    | 64 GB  | $0.14    |
| `cpu.large`  | 64    | 256 GB | $0.52    |
| `cpu.xlarge` | 192   | 768 GB | $1.48    |

---

### Launching an Instance

```bash
# Using CloudScale CLI
cs compute launch \
  --sku gpu.a100.1 \
  --image pytorch:2.3-cuda12 \
  --region us-east-1 \
  --name my-training-run
```

```python
# Using Python SDK
import cloudscale

client = cloudscale.Client(api_key="cs_live_...")
instance = client.compute.launch(
    sku="gpu.a100.1",
    image="pytorch:2.3-cuda12",
    region="us-east-1",
    name="my-training-run",
)
print(instance.id)   # inst_abc123
print(instance.ip)   # 10.4.22.15
```

---

### Instance Lifecycle

States: `PENDING` → `RUNNING` → `STOPPING` → `STOPPED` | `TERMINATED`

- **Stop**: instance is paused; disk persists; billed for storage only
- **Terminate**: instance and ephemeral disk are destroyed permanently
- **Reboot**: soft reboot; IP address and data preserved

```bash
cs compute stop inst_abc123
cs compute terminate inst_abc123
```

---

### Auto-Scaling Groups (ASG)

ASGs allow dynamic scaling based on queue depth, GPU utilisation, or custom CloudWatch-style metrics.

```yaml
# asg-config.yaml
name: inference-fleet
min_instances: 1
max_instances: 20
sku: gpu.a10g.1
image: myrepo/inference:v2
scale_up_threshold:
  metric: gpu_utilization
  value: 80
  duration_seconds: 60
scale_down_threshold:
  metric: gpu_utilization
  value: 20
  duration_seconds: 300
```

```bash
cs asg apply -f asg-config.yaml
```

---

### Networking

- Each instance gets a private IP in your VPC automatically
- Optional public IP (static Elastic IP available)
- VPC peering: connect to AWS/GCP/Azure VPCs on Business+ plans
- Private Link endpoint: access CloudScale APIs without public internet

**Firewall rules:**
```bash
cs firewall add --instance inst_abc123 --port 22 --cidr 0.0.0.0/0 --protocol tcp
cs firewall add --instance inst_abc123 --port 8080 --cidr 10.0.0.0/8 --protocol tcp
```

---

### SSH Access

```bash
# Add SSH key to account
cs keys add --name my-key --public-key ~/.ssh/id_rsa.pub

# Launch with key
cs compute launch --sku gpu.a10g.1 --image ubuntu:22.04 --key my-key

# Connect
ssh cloudscale@<public-ip>
```

---

### Storage Volumes (Persistent)

Ephemeral NVMe is included with every instance. For persistent data:

```bash
cs volume create --size 500 --type ssd --name training-data
cs volume attach vol_xyz789 --instance inst_abc123 --mount /data
```

Volume types: `ssd` (NVMe, $0.12/GB/mo), `hdd` (spinning, $0.03/GB/mo)

---

### Spot Instances

Spot instances are excess capacity offered at up to 80% discount. They can be reclaimed with 2-minute notice.

```bash
cs compute launch --sku gpu.a100.1 --spot --spot-max-price 1.00
```

Best practice: use checkpointing every 5–10 minutes when training on spot.

---

### Common Errors

| Error Code | Meaning                        | Fix                                                    |
|------------|--------------------------------|--------------------------------------------------------|
| `ERR_QUOTA` | Instance quota exceeded        | Request quota increase via dashboard or support ticket |
| `ERR_CAPACITY` | No capacity in region       | Try another region or instance type                    |
| `ERR_IMAGE_NOT_FOUND` | Image tag invalid     | Run `cs images list` to see valid images               |
| `ERR_KEY_INVALID` | SSH key not found          | Run `cs keys list` and use correct key name            |
| `ERR_BILLING` | Payment method declined       | Update billing info in dashboard                       |

---

## Part 2: Storage API

### Overview

Storage API is an S3-compatible object storage service. Any AWS SDK or tool that supports S3 (boto3, rclone, Terraform, etc.) works with Storage API with a simple endpoint swap.

---

### Buckets

```bash
# Create a bucket
cs storage bucket create my-dataset-bucket --region eu-west-1 --tier hot

# List buckets
cs storage bucket list

# Delete a bucket (must be empty)
cs storage bucket delete my-dataset-bucket
```

Storage tiers:
- **Hot**: instant access, $0.022/GB/mo
- **Warm**: millisecond access, $0.011/GB/mo (after 30 days auto-transition available)
- **Archive**: retrieval within 4 hours, $0.002/GB/mo

---

### Objects

```python
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url="https://storage.cloudscale.ai",
    aws_access_key_id="cs_key_...",
    aws_secret_access_key="cs_secret_...",
)

# Upload
s3.upload_file("model.pt", "my-dataset-bucket", "checkpoints/model.pt")

# Download
s3.download_file("my-dataset-bucket", "checkpoints/model.pt", "local_model.pt")

# Generate presigned URL (expires in 3600s)
url = s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": "my-dataset-bucket", "Key": "checkpoints/model.pt"},
    ExpiresIn=3600,
)
```

---

### Dataset Versioning

```bash
# Enable versioning on a bucket
cs storage versioning enable my-dataset-bucket

# List versions of an object
cs storage versions list my-dataset-bucket --key dataset.parquet

# Restore a previous version
cs storage versions restore my-dataset-bucket --key dataset.parquet --version-id v3
```

---

### Access Control

Bucket policies follow AWS IAM JSON syntax:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "CS": "user_12345" },
      "Action": ["s3:GetObject"],
      "Resource": "arn:cs:s3:::my-dataset-bucket/*"
    }
  ]
}
```

---

### CDN / Edge Delivery

Enable CDN on any public bucket to serve assets from 28 edge PoPs:

```bash
cs storage cdn enable my-dataset-bucket --custom-domain assets.mycompany.com
```

CDN pricing: $0.008/GB egress (vs $0.018 without CDN).

---

### Common Errors

| Error Code              | Meaning                              | Fix                                                 |
|-------------------------|--------------------------------------|-----------------------------------------------------|
| `NoSuchBucket`          | Bucket not found                     | Check bucket name and region                        |
| `AccessDenied`          | Missing permissions                  | Review bucket policy and API key permissions        |
| `EntityTooLarge`        | Object exceeds 5 TB limit            | Use multipart upload; split if necessary            |
| `BucketNotEmpty`        | Delete attempted on non-empty bucket | Empty bucket first with `cs storage objects purge`  |
| `InvalidStorageTier`    | Tier name typo                       | Use `hot`, `warm`, or `archive`                     |

---

## Part 3: Inference Gateway

### Deploying an Endpoint

```bash
cs inference deploy \
  --model-path s3://my-bucket/models/llm-v2/ \
  --runtime vllm:0.4 \
  --sku gpu.a10g.1 \
  --min-replicas 1 \
  --max-replicas 10 \
  --name production-llm
```

### Sending Requests

```python
import requests

resp = requests.post(
    "https://inference.cloudscale.ai/v1/endpoints/production-llm/predict",
    headers={"Authorization": "Bearer cs_live_..."},
    json={"inputs": "Summarize this document: ..."},
)
print(resp.json())
```

---

## Part 4: Billing & Cost Management

### Viewing Current Bill

```bash
cs billing current          # Current month estimate
cs billing history          # Past invoices
cs billing breakdown        # Cost by service/instance
```

### Setting Spend Alerts

```bash
cs billing alert set --threshold 500 --email alerts@mycompany.com
```

### Cost Optimisation Tips

1. Use **Spot Instances** for fault-tolerant training jobs (save up to 80%)
2. Enable **auto-stop** on dev instances to prevent overnight waste
3. Use **Warm tier** for datasets accessed < once/day
4. Downsize to `gpu.a10g.1` for inference; reserve H100 for training only
5. Enable **Reserved Instances** if monthly spend > $2,000 (saves 30–45%)

---

## Part 5: Support & SLAs

### How to Open a Support Ticket

1. Dashboard → Support → New Ticket
2. Web Form: https://support.cloudscale.ai
3. Email: support@cloudscale.ai
4. WhatsApp (Business+ only): +1-415-555-0192

### SLA Definitions

- **Availability SLA**: compensated as service credits if uptime < 99.95% in any calendar month
- **Credit tiers**: 99.0–99.95% → 10% credit | 95–99% → 25% credit | < 95% → 50% credit
- SLA credits must be requested within 30 days of the incident
- Credits apply to future invoices only; no cash refunds

### Incident Status Page

Live status and post-mortems: https://status.cloudscale.ai
Subscribe to incident updates via email or RSS.
